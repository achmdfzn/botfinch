"""Sinkronisasi bot <-> dashboard web (Next.js).

- Tiap 5 menit: push snapshot (server, member, channel, role, leaderboard,
  giveaway aktif, modlog 25 aksi moderasi terbaru) ke /api/ingest.
- Push SEKALI saat startup (on_ready) + SEGERA saat bot join server baru
  (on_guild_join) — selalu snapshot PENUH semua guild karena /api/ingest
  mengganti seluruh snapshot, bukan merge per-guild.
- Tiap 5 menit: pull dari /api/guilds/{id}/sync -> pengaturan, self-roles,
  auto-responder, pengumuman terjadwal, permintaan giveaway pending, dan
  permintaan embed pending ke tabel lokal.
- Permintaan giveaway pending langsung dieksekusi via cog Giveaway lalu di-ack
  (dihormati toggle `giveaway_enabled`).
- Permintaan embed pending langsung dikirim ke channel lalu di-ack
  (dihormati toggle `embed_enabled`).
- Pengumuman: loop tiap 60 detik mengirim yang sekali (run_at lewat) maupun
  berulang (interval_minutes), lalu menandai last_sent_at
  (dihormati toggle `announcements_enabled`).
- Helper `get_guild_setting(guild_id, key, default)` dipakai fitur lain
  agar pengaturan dasbor benar-benar berlaku.

Mati total kalau DASHBOARD_URL / DASHBOARD_SECRET kosong di .env.
"""
import asyncio
import logging

import aiohttp
import discord
from discord.ext import commands, tasks

from src import config
from src.bot import MENTIONS_PENGUMUMAN
from src.store import get_connection
from src.utils import premium
from src.utils.embeds import BRAND
from src.utils.waktu import parse_iso

log = logging.getLogger("finch")

TABEL_SETTINGS = """
CREATE TABLE IF NOT EXISTS dashboard_settings (
    guild_id INTEGER NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    PRIMARY KEY (guild_id, key)
)
"""

TABEL_SELFROLES = """
CREATE TABLE IF NOT EXISTS dashboard_selfroles (
    guild_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    emoji TEXT NOT NULL,
    role_id INTEGER NOT NULL,
    PRIMARY KEY (guild_id, message_id, emoji)
)
"""

# Registri baris self-role "yatim": pesannya tidak ditemukan di semua channel
# saat seed reaksi. Dipisah dari dashboard_selfroles karena _simpan_selfroles
# me-mirror ulang (DELETE + INSERT) tiap pull — flag di tabel utama akan
# terhapus, sementara tabel ini persisten antar-restart. Dibersihkan saat
# barisnya sudah tidak dikirim dashboard lagi (panel dihapus/diubah).
TABEL_SELFROLE_ORPHAN = """
CREATE TABLE IF NOT EXISTS selfrole_orphan (
    guild_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    emoji TEXT NOT NULL,
    PRIMARY KEY (guild_id, message_id, emoji)
)
"""

TABEL_ANNOUNCEMENTS = """
CREATE TABLE IF NOT EXISTS dashboard_announcements (
    id INTEGER PRIMARY KEY,
    guild_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    message TEXT NOT NULL,
    run_at TEXT,
    interval_minutes INTEGER,
    enabled INTEGER NOT NULL DEFAULT 1,
    last_sent_at TEXT
)
"""


def substitusi_pengumuman(
    pesan: str, nama_server: str, now=None, member_count: int | None = None
) -> str:
    """Substitusi placeholder di pesan pengumuman terjadwal.

    Didukung: {server} (nama server), {date} (tanggal hari ini, format DD Mon YYYY),
    {member_count} (jumlah member server).
    """
    if now is None:
        now = discord.utils.utcnow()
    hasil = pesan.replace("{server}", nama_server).replace(
        "{date}", now.strftime("%d %b %Y")
    )
    if member_count is not None:
        hasil = hasil.replace("{member_count}", str(member_count))
    return hasil


def _int_aman(nilai, default: int = 0) -> int:
    """int() yang tidak pernah raise — untuk id dari payload dashboard."""
    try:
        return int(nilai)
    except (ValueError, TypeError):
        return default


# Tipe channel Discord yang bisa menerima pesan: teks (0), news/announcement
# (5), dan thread (10/11/12). Kategori (4), voice (2), stage (13), dan forum
# (15) TIDAK bisa dikirimi pesan langsung oleh bot.
TIPE_CHANNEL_TEKS = frozenset({0, 5, 10, 11, 12})


def _tipe_channel_numerik(channel) -> int | None:
    """Kode tipe numerik channel; None bila tidak dapat ditentukan.

    Objek channel discord.py selalu punya `.type` berupa enum ChannelType
    (punya `.value` int). Nilai mentah int (test double) juga diterima.
    """
    tipe = getattr(channel, "type", None)
    mentah = getattr(tipe, "value", tipe)
    if isinstance(mentah, bool) or not isinstance(mentah, int):
        return None
    return mentah


def _channel_milik_guild(channel, guild_id: int) -> bool:
    """Fail-closed: channel tujuan harus benar-benar milik guild yang diproses
    DAN bertipe yang bisa menerima pesan (teks/news/thread).

    Cek guild saja tidak cukup: channel voice/kategori di guild yang sama
    tetap tidak bisa dikirimi pesan, jadi ditolak di sini sebelum ada side
    effect apa pun. Tipe yang tidak dapat ditentukan juga ditolak.
    """
    guild = getattr(channel, "guild", None)
    if guild is None or getattr(guild, "id", None) != guild_id:
        return False
    return _tipe_channel_numerik(channel) in TIPE_CHANNEL_TEKS


def get_guild_setting(guild_id: int, key: str, default: str = "1") -> str:
    """Baca pengaturan per-server dari cache lokal (disimpan oleh pull loop)."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT value FROM dashboard_settings WHERE guild_id = ? AND key = ?",
            (guild_id, key),
        ).fetchone()
    return row[0] if row else default


def get_guild_setting_int(guild_id: int, key: str, default: int) -> int:
    """Versi int dari get_guild_setting; fallback ke default bila tak valid."""
    try:
        return int(get_guild_setting(guild_id, key, str(default)))
    except (ValueError, TypeError):
        return default


def modul_aktif(guild_id: int, key: str) -> bool:
    """True bila toggle modul TIDAK dimatikan via dashboard.

    Konvensi: key "*_enabled" bernilai "1"/"0", default "1" (perilaku lama
    tetap jalan bila dashboard belum pernah mengirim key tersebut).
    """
    return get_guild_setting(guild_id, key, "1") == "1"


def channel_setting(guild_id: int, key: str, fallback: int) -> int:
    """ID channel/kategori per-server dari dashboard; fallback ke config global.

    Dipakai fitur yang dulunya hanya baca ID global dari .env (verifikasi,
    tiket, saran, counting, tempvc, confess, dailyq). Return 0 bila keduanya
    kosong = fitur belum dikonfigurasi di server ini.
    """
    return get_guild_setting_int(guild_id, key, 0) or int(fallback or 0)


def parse_id_list(teks: str | None) -> list[int]:
    """'123, 456' -> [123, 456]. Entri bukan angka dilewati diam-diam."""
    hasil: list[int] = []
    for bagian in (teks or "").split(","):
        bagian = bagian.strip()
        if bagian.isdigit():
            hasil.append(int(bagian))
    return hasil


def _nama_member(guild: discord.Guild, user_id: int) -> str:
    m = guild.get_member(user_id)
    return m.display_name if m else str(user_id)


def _nama_member_teks(guild: discord.Guild, user_id: str) -> str:
    """Versi _nama_member untuk id yang tersimpan sebagai teks di DB."""
    return _nama_member(guild, _int_aman(user_id))


class DashboardSync(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        with get_connection() as conn:
            conn.execute(TABEL_SETTINGS)
            conn.execute(TABEL_SELFROLES)
            conn.execute(TABEL_ANNOUNCEMENTS)
            conn.execute(TABEL_SELFROLE_ORPHAN)
            conn.commit()
        self._jalan = bool(config.settings.dashboard_url and config.settings.dashboard_secret)
        # (message_id, emoji) yang sudah diberi reaksi seed agar tak diulang tiap loop
        self._seeded: set[tuple[int, str]] = set()
        # on_ready bisa tembak berkali-kali saat reconnect; push awal hanya sekali
        self._push_awal_done = False
        if self._jalan:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                pass
            else:
                self.push_snapshot.start()
                self.pull_settings.start()
                self.kirim_pengumuman.start()

    def cog_unload(self):
        for loop in (self.push_snapshot, self.pull_settings, self.kirim_pengumuman):
            try:
                loop.cancel()
            except Exception:
                pass

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {config.settings.dashboard_secret}"}

    def _snapshot_guild(self, g: discord.Guild) -> dict:
        with get_connection() as conn:
            top_level = conn.execute(
                "SELECT user_id, level, xp FROM users WHERE guild_id = ?"
                " ORDER BY level DESC, xp DESC LIMIT 10",
                (g.id,),
            ).fetchall()
            top_koin = conn.execute(
                "SELECT user_id, balance FROM economy WHERE guild_id = ?"
                " ORDER BY balance DESC LIMIT 10",
                (g.id,),
            ).fetchall()
            gw_rows = conn.execute(
                "SELECT message_id, channel_id, prize, winners_count, ends_at"
                " FROM giveaways WHERE guild_id = ? AND ended = 0",
                (g.id,),
            ).fetchall()
            # hitung peserta per giveaway satu per satu (jumlah giveaway aktif kecil)
            gw_peserta = {}
            for row in gw_rows:
                c = conn.execute(
                    "SELECT COUNT(*) FROM giveaway_entries WHERE message_id = ?",
                    (row[0],),
                ).fetchone()
                gw_peserta[row[0]] = c[0] if c else 0
        return {
            "id": str(g.id),
            "name": g.name,
            "icon": str(g.icon.key) if g.icon else None,
            "member_count": g.member_count or 0,
            # text + voice + kategori: dropdown channel di dashboard
            # butuh semuanya (mis. lobby tempvc = voice, tiket = kategori).
            "channels": [
                {"id": str(c.id), "name": c.name, "type": int(c.type.value)}
                for c in g.text_channels
            ]
            + [
                {"id": str(c.id), "name": c.name, "type": int(c.type.value)}
                for c in g.voice_channels
            ]
            + [
                {"id": str(c.id), "name": c.name, "type": int(c.type.value)}
                for c in g.categories
            ],
            "roles": [
                {"id": str(r.id), "name": r.name}
                for r in g.roles
                if not r.is_default()
            ][:200],
            "leaderboards": {
                "levels": [
                    {
                        "user_id": str(uid),
                        "name": _nama_member(g, uid),
                        "level": lvl,
                        "xp": xp,
                    }
                    for uid, lvl, xp in top_level
                ],
                "coins": [
                    {
                        "user_id": str(uid),
                        "name": _nama_member(g, uid),
                        "coins": koin,
                    }
                    for uid, koin in top_koin
                ],
            },
            "giveaways": [
                {
                    "id": mid,
                    "channel_id": str(cid),
                    "prize": prize,
                    "winners": wcount,
                    "ends_at": ends,
                    "participants": gw_peserta.get(mid, 0),
                }
                for mid, cid, prize, wcount, ends in gw_rows
            ],
            "modlog": self._modlog_guild(g),
        }

    def _modlog_guild(self, g: discord.Guild) -> list:
        """25 aksi moderasi terbaru server ini + nama user/mod (fallback: ID)."""
        try:
            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT user_id, mod_id, aksi, alasan, waktu FROM mod_actions"
                    " WHERE guild_id = ? ORDER BY id DESC LIMIT 25",
                    (str(g.id),),
                ).fetchall()
        except Exception:
            log.warning("dashboard: gagal baca mod_actions guild %s", g.id, exc_info=True)
            return []
        return [
            {
                "user_id": uid,
                "user_name": _nama_member_teks(g, uid),
                "mod_id": mid,
                "mod_name": _nama_member_teks(g, mid),
                "aksi": aksi,
                "alasan": alasan,
                "waktu": waktu,
            }
            for uid, mid, aksi, alasan, waktu in rows
        ]

    async def _kirim_snapshot(self, guilds: list[discord.Guild], alasan: str = "rutin") -> None:
        """Push snapshot ke /api/ingest; no-op bila integrasi dashboard mati.

        Selalu kirim SEMUA guild: endpoint ingest mengganti seluruh snapshot,
        bukan merge per-guild.
        """
        if not self._jalan:
            return
        data = []
        for g in guilds:
            try:
                data.append(self._snapshot_guild(g))
            except Exception:
                # Satu guild gagal (DB error, dst.) tidak boleh membunuh
                # loop push 5-menit selamanya — lewati guild itu saja.
                log.warning("dashboard: gagal snapshot guild %s", g.id, exc_info=True)
        payload = {"bot_name": self.bot.user.name if self.bot.user else "Finch", "guilds": data}
        try:
            async with aiohttp.ClientSession() as sesi:
                async with sesi.post(
                    f"{config.settings.dashboard_url}/api/ingest",
                    json=payload,
                    headers=self._headers(),
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status == 200:
                        log.info("dashboard: snapshot terkirim (%d server, %s)", len(data), alasan)
                    else:
                        log.warning("dashboard: ingest ditolak (HTTP %d)", resp.status)
        except Exception:
            log.warning("dashboard: gagal push snapshot", exc_info=True)

    @tasks.loop(minutes=5)
    async def push_snapshot(self):
        await self._kirim_snapshot(list(self.bot.guilds), "rutin")

    @push_snapshot.before_loop
    async def _before_push(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_ready(self):
        # Loop 5-menit tidak jalan langsung di awal; push sekali saat startup
        # agar dashboard langsung punya data (flag: on_ready bisa repeat).
        if self._jalan and not self._push_awal_done:
            self._push_awal_done = True
            await self._kirim_snapshot(list(self.bot.guilds), "startup")

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        # Bot baru diundang -> snapshot langsung, tanpa tunggu loop 5 menit.
        if not self._jalan:
            return
        await asyncio.sleep(2)  # beri waktu cache guild settle
        await self._kirim_snapshot(list(self.bot.guilds), f"guild_join {guild.id}")

    @tasks.loop(minutes=5)
    async def pull_settings(self):
        for g in self.bot.guilds:
            try:
                async with aiohttp.ClientSession() as sesi:
                    async with sesi.get(
                        f"{config.settings.dashboard_url}/api/guilds/{g.id}/sync",
                        headers=self._headers(),
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as resp:
                        if resp.status != 200:
                            continue
                        data = await resp.json()
                self._simpan_settings(g.id, data.get("settings") or {})
                self._simpan_entitlement(g.id, data)
                self._simpan_selfroles(g.id, data.get("selfroles") or [])
                self._simpan_responder(g.id, data.get("autoresponses") or [])
                pengumuman = data.get("announcements") or []
                await self._rekonsiliasi_pengumuman(g.id, pengumuman)
                self._simpan_pengumuman(g.id, pengumuman)
                await self._proses_giveaway(g, data.get("giveaway_requests") or [])
                await self._proses_embed(g, data.get("embed_requests") or [])
                await self._seed_reaksi(g)
            except Exception:
                log.warning("dashboard: gagal pull guild %s", g.id, exc_info=True)

    @pull_settings.before_loop
    async def _before_pull(self):
        await self.bot.wait_until_ready()

    def _simpan_settings(self, guild_id: int, settings: dict) -> None:
        with get_connection() as conn:
            for k, v in settings.items():
                conn.execute(
                    "INSERT OR REPLACE INTO dashboard_settings (guild_id, key, value)"
                    " VALUES (?, ?, ?)",
                    (guild_id, str(k), _nilai(v)),
                )
            conn.commit()

    def _simpan_entitlement(self, guild_id: int, data: dict) -> None:
        """Simpan entitlement VIP dari payload sync ke cache lokal.

        Dashboard lama tidak mengirim `entitlement` (None) -> helper
        `simpan_entitlement_cache` no-op, cache lama dipertahankan.
        """
        try:
            premium.simpan_entitlement_cache(guild_id, (data or {}).get("entitlement"))
        except Exception:
            log.warning(
                "dashboard: gagal simpan entitlement guild %s", guild_id, exc_info=True
            )

    def _simpan_selfroles(self, guild_id: int, rows: list) -> None:
        with get_connection() as conn:
            conn.execute("DELETE FROM dashboard_selfroles WHERE guild_id = ?", (guild_id,))
            segar: set[int] = set()
            for r in rows:
                try:
                    mid = int(r["message_id"])
                    conn.execute(
                        "INSERT INTO dashboard_selfroles (guild_id, message_id, emoji, role_id)"
                        " VALUES (?, ?, ?, ?)",
                        (guild_id, mid, str(r["emoji"])[:64], int(r["role_id"])),
                    )
                    segar.add(mid)
                except (KeyError, ValueError, TypeError):
                    continue
            # Bersihkan flag yatim untuk pesan yang sudah tidak dikirim
            # dashboard lagi (panel dihapus/diubah) agar registri tak tumbuh.
            # SQL statis per-baris (tanpa f-string): tabel yatim kecil.
            yatim_lama = [
                r[0]
                for r in conn.execute(
                    "SELECT message_id FROM selfrole_orphan WHERE guild_id = ?",
                    (guild_id,),
                ).fetchall()
            ]
            for mid in yatim_lama:
                if mid not in segar:
                    conn.execute(
                        "DELETE FROM selfrole_orphan WHERE guild_id = ? AND message_id = ?",
                        (guild_id, mid),
                    )
            conn.commit()

    def _simpan_responder(self, guild_id: int, rows: list) -> None:
        # Dashboard = sumber utama; ganti total agar hapus via web ikut berlaku.
        # /respon-add dan /respon-del di Discord ikut mirror ke dashboard bila aktif.
        with get_connection() as conn:
            conn.execute("DELETE FROM autoresponder WHERE guild_id = ?", (guild_id,))
            for r in rows:
                try:
                    trigger = str(r["trigger"]).strip().lower()[:100]
                    respons = str(r["response"]).strip()[:500]
                    if not trigger or not respons:
                        continue
                    conn.execute(
                        "INSERT INTO autoresponder (guild_id, trigger, respons) VALUES (?, ?, ?)",
                        (guild_id, trigger, respons),
                    )
                except (KeyError, TypeError):
                    continue
            conn.commit()

    def _simpan_pengumuman(self, guild_id: int, rows: list) -> None:
        """Mirror pengumuman dashboard tanpa menimpa timestamp lokal yang lebih baru.

        Dashboard adalah sumber konfigurasi. Timestamp lokal yang lebih baru
        dipertahankan sampai acknowledgment sukses diselaraskan kembali.
        """
        with get_connection() as conn:
            status_lokal = {
                int(r[0]): r[1]
                for r in conn.execute(
                    "SELECT id, last_sent_at FROM dashboard_announcements WHERE guild_id = ?",
                    (str(guild_id),),
                ).fetchall()
            }
            conn.execute("DELETE FROM dashboard_announcements WHERE guild_id = ?", (str(guild_id),))
            for r in (rows or [])[:50]:
                try:
                    pesan = str(r["message"]).strip()
                    if not pesan:
                        continue
                    run_at = parse_iso(str(r.get("run_at") or "") or None)
                    terakhir_remote = parse_iso(str(r.get("last_sent_at") or "") or None)
                    terakhir_lokal = parse_iso(status_lokal.get(_int_aman(r.get("id"))))
                    terakhir = terakhir_remote
                    if terakhir_lokal is not None and (
                        terakhir_remote is None or terakhir_lokal > terakhir_remote
                    ):
                        terakhir = terakhir_lokal
                    interval = r.get("interval_minutes")
                    interval = _int_aman(interval) if interval is not None else None
                    conn.execute(
                        "INSERT INTO dashboard_announcements"
                        " (id, guild_id, channel_id, message, run_at, interval_minutes, enabled, last_sent_at)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            _int_aman(r["id"]),
                            str(guild_id),
                            str(r["channel_id"]),
                            pesan[:2000],
                            run_at.isoformat() if run_at else None,
                            interval,
                            1 if r.get("enabled", True) else 0,
                            terakhir.isoformat() if terakhir else None,
                        ),
                    )
                except (KeyError, TypeError):
                    continue
            conn.commit()

    async def _ack_announcement(
        self, guild_id: int, ann_id: int, last_sent_at: str
    ) -> bool:
        """Simpan waktu kirim di dashboard; False berarti perlu direkonsiliasi lagi."""
        try:
            async with aiohttp.ClientSession() as sesi:
                async with sesi.post(
                    f"{config.settings.dashboard_url}/api/guilds/{guild_id}/announcements/{ann_id}",
                    json={"last_sent_at": last_sent_at},
                    headers=self._headers(),
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as resp:
                    if resp.status == 200:
                        return True
                    log.warning(
                        "dashboard: acknowledgment pengumuman %s ditolak (HTTP %d)",
                        ann_id, resp.status,
                    )
        except Exception:
            log.warning(
                "dashboard: gagal ack pengumuman %s", ann_id, exc_info=True
            )
        return False

    async def _rekonsiliasi_pengumuman(self, guild_id: int, rows: list) -> None:
        """Kirim ulang acknowledgment lokal yang lebih baru daripada snapshot server."""
        with get_connection() as conn:
            lokal = {
                int(r[0]): r[1]
                for r in conn.execute(
                    "SELECT id, last_sent_at FROM dashboard_announcements WHERE guild_id = ?",
                    (str(guild_id),),
                ).fetchall()
            }
        for row in (rows or [])[:50]:
            ann_id = _int_aman(row.get("id"))
            waktu_lokal = parse_iso(lokal.get(ann_id))
            waktu_remote = parse_iso(str(row.get("last_sent_at") or "") or None)
            if waktu_lokal is not None and (
                waktu_remote is None or waktu_lokal > waktu_remote
            ):
                await self._ack_announcement(guild_id, ann_id, waktu_lokal.isoformat())

    async def _proses_giveaway(self, guild: discord.Guild, requests: list) -> None:
        if not requests:
            return
        if not modul_aktif(guild.id, "giveaway_enabled"):
            # Modul dimatikan via dashboard: tolak semua permintaan agar antrean
            # tidak menumpuk, dengan catatan yang jelas.
            for r in requests:
                await self._ack_giveaway(
                    guild.id, r.get("id"), "failed", "modul giveaway dimatikan di server ini"
                )
            return
        cog = self.bot.get_cog("Giveaway")
        if cog is None:
            # Tanpa ack, permintaan pending menumpuk & di-retry tiap 5 menit
            # selamanya — tolak eksplisit agar antrean dashboard bersih.
            log.warning("dashboard: cog Giveaway tidak ada, %d permintaan ditolak", len(requests))
            for r in requests:
                await self._ack_giveaway(guild.id, r.get("id"), "failed", "cog giveaway tidak aktif")
            return
        # Kuota premium: giveaway aktif (ended=0) guild ini tidak boleh
        # melewati limit tier-nya. Dihitung sekali, lalu dinaikkan lokal
        # tiap posting sukses agar request berikutnya dalam batch yang
        # sama ikut terhitung.
        with get_connection() as conn:
            _row = conn.execute(
                "SELECT COUNT(*) FROM giveaways WHERE guild_id = ? AND ended = 0",
                (guild.id,),
            ).fetchone()
        count_aktif = _row[0] if _row else 0
        for r in requests:
            req_id = r.get("id")
            if not premium.check_resource_quota(guild.id, "giveaways_active", count_aktif):
                await self._ack_giveaway(
                    guild.id,
                    req_id,
                    "failed",
                    premium.pesan_kuota_penuh(
                        "giveaways_active",
                        premium.get_feature_limit(guild.id, "giveaways_active"),
                    ),
                )
                continue
            try:
                channel = guild.get_channel(int(r["channel_id"])) or await self.bot.fetch_channel(int(r["channel_id"]))
                if not _channel_milik_guild(channel, guild.id):
                    await self._ack_giveaway(
                        guild.id, req_id, "failed", "channel bukan milik server ini"
                    )
                    continue
                detik = max(60, int(r["duration_minutes"]) * 60)
                msg_id = await cog.posting_giveaway(
                    channel,
                    guild.id,
                    self.bot.user.id if self.bot.user else 0,
                    detik,
                    max(1, int(r.get("winners", 1))),
                    str(r.get("prize", ""))[:100],
                )
                if msg_id:
                    count_aktif += 1
                await self._ack_giveaway(guild.id, req_id, "done" if msg_id else "failed",
                                         "" if msg_id else "gagal posting ke channel")
            except Exception as e:
                log.warning("dashboard: gagal eksekusi giveaway req %s (%s)", req_id, e)
                await self._ack_giveaway(guild.id, req_id, "failed", str(e)[:200])

    async def _ack_giveaway(self, guild_id: int, req_id, status: str, note: str) -> None:
        if req_id is None:
            return
        try:
            async with aiohttp.ClientSession() as sesi:
                async with sesi.post(
                    f"{config.settings.dashboard_url}/api/guilds/{guild_id}/giveaway-requests/{req_id}",
                    json={"status": status, "note": note},
                    headers=self._headers(),
                    timeout=aiohttp.ClientTimeout(total=20),
                ):
                    pass
        except Exception:
            log.warning("dashboard: gagal ack giveaway req %s", req_id, exc_info=True)

    async def _proses_embed(self, guild: discord.Guild, requests: list) -> None:
        """Kirim permintaan embed pending dari dashboard, lalu ack done/failed.

        Dihormati toggle `embed_enabled` ("1"/"0", default "1").
        """
        daftar = list((requests or [])[:10])
        if daftar and not modul_aktif(guild.id, "embed_enabled"):
            for r in daftar:
                await self._ack_embed(
                    guild.id, r.get("id"), "failed", "modul embed dimatikan di server ini"
                )
            return
        for r in daftar:
            req_id = r.get("id")
            ch_id = _int_aman(r.get("channel_id"))
            if not ch_id:
                await self._ack_embed(guild.id, req_id, "failed", "channel_id tidak valid")
                continue
            channel = guild.get_channel(ch_id)
            if channel is None:
                try:
                    channel = await self.bot.fetch_channel(ch_id)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    channel = None
                except Exception:
                    channel = None
            if channel is None:
                await self._ack_embed(guild.id, req_id, "failed", "channel tidak ditemukan")
                continue
            if not _channel_milik_guild(channel, guild.id):
                await self._ack_embed(
                    guild.id, req_id, "failed", "channel bukan milik server ini"
                )
                continue
            try:
                embed = _bangun_embed(r)
            except Exception as e:
                log.warning("dashboard: embed req %s invalid (%s)", req_id, e)
                embed = None
            if embed is None:
                await self._ack_embed(guild.id, req_id, "failed", "embed kosong/invalid")
                continue
            try:
                # Embed ditulis admin via dashboard -> boleh @everyone.
                await channel.send(embed=embed, allowed_mentions=MENTIONS_PENGUMUMAN)
            except discord.Forbidden:
                await self._ack_embed(guild.id, req_id, "failed", "bot tidak punya izin kirim ke channel")
                continue
            except discord.HTTPException as e:
                await self._ack_embed(guild.id, req_id, "failed", f"gagal kirim (HTTP {e.status})")
                continue
            except Exception as e:
                log.warning("dashboard: gagal kirim embed req %s (%s)", req_id, e)
                await self._ack_embed(guild.id, req_id, "failed", str(e)[:200])
                continue
            await self._ack_embed(guild.id, req_id, "done", "")

    async def _ack_embed(self, guild_id: int, req_id, status: str, note: str) -> None:
        if req_id is None:
            return
        try:
            async with aiohttp.ClientSession() as sesi:
                async with sesi.post(
                    f"{config.settings.dashboard_url}/api/guilds/{guild_id}/embed-requests/{req_id}",
                    json={"status": status, "note": note},
                    headers=self._headers(),
                    timeout=aiohttp.ClientTimeout(total=20),
                ):
                    pass
        except Exception:
            log.warning("dashboard: gagal ack embed req %s", req_id, exc_info=True)

    @tasks.loop(seconds=60)
    async def kirim_pengumuman(self):
        """Kirim pengumuman terjadwal dari dashboard (sekali & berulang).

        Sekali: enabled, run_at sudah lewat, belum terkirim -> kirim, tandai.
        Berulang: enabled, interval_minutes > 0, belum pernah atau interval
        sudah lewat -> kirim, update last_sent_at. Gagal kirim dilewati
        diam-diam (dicoba lagi loop berikut); loop tidak boleh crash.
        Toggle `announcements_enabled` ("1"/"0", default "1") mematikan
        pengumuman per-server.
        """
        try:
            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT id, guild_id, channel_id, message, run_at,"
                    " interval_minutes, last_sent_at"
                    " FROM dashboard_announcements WHERE enabled = 1"
                ).fetchall()
        except Exception:
            log.warning("dashboard: gagal baca pengumuman", exc_info=True)
            return
        now = discord.utils.utcnow()
        for ann_id, gid_s, ch_s, pesan, run_at_s, interval, last_s in rows:
            try:
                await self._kirim_satu_pengumuman(now, ann_id, gid_s, ch_s, pesan, run_at_s, interval, last_s)
            except Exception:
                # Satu pengumuman rusak (DB/setting/channel aneh) tidak boleh
                # membunuh loop 60-detik selamanya.
                log.exception("dashboard: gagal kirim pengumuman %s", ann_id)

    async def _kirim_satu_pengumuman(
        self, now, ann_id: int, gid_s: str, ch_s: str, pesan: str,
        run_at_s: str | None, interval, last_s: str | None,
    ) -> None:
        """Satu pengumuman terjadwal: putuskan waktunya, kirim, tandai."""
        interval_menit = _int_aman(interval)
        run_at = parse_iso(run_at_s)
        terakhir = parse_iso(last_s)
        if interval_menit > 0:
            # berulang: lewati bila interval belum lewat
            if terakhir is not None and (now - terakhir).total_seconds() < interval_menit * 60:
                return
        elif run_at is None or terakhir is not None or run_at > now:
            # sekali: butuh run_at valid yang sudah lewat & belum terkirim
            return
        guild = self.bot.get_guild(_int_aman(gid_s))
        if guild is None:
            return
        if not modul_aktif(guild.id, "announcements_enabled"):
            return  # modul pengumuman dimatikan via dashboard
        channel = guild.get_channel(_int_aman(ch_s))
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(_int_aman(ch_s))
            except Exception:
                return
        if not _channel_milik_guild(channel, guild.id):
            log.warning(
                "dashboard: pengumuman %s ditolak karena channel bukan milik guild %s",
                ann_id, guild.id,
            )
            return
        try:
            # Substitusi placeholder {server} / {date} / {member_count}
            teks = substitusi_pengumuman(
                pesan, guild.name, now, guild.member_count or 0
            )
            # Pengumuman ditulis admin via dashboard -> boleh @everyone.
            await channel.send(teks, allowed_mentions=MENTIONS_PENGUMUMAN)
        except Exception:
            return  # gagal -> lewati diam-diam
        waktu_kirim = discord.utils.utcnow().isoformat()
        try:
            with get_connection() as conn:
                conn.execute(
                    "UPDATE dashboard_announcements SET last_sent_at = ? WHERE id = ?",
                    (waktu_kirim, ann_id),
                )
                conn.commit()
        except Exception:
            log.warning("dashboard: gagal update last_sent_at pengumuman %s", ann_id, exc_info=True)
        await self._ack_announcement(_int_aman(gid_s), ann_id, waktu_kirim)

    @kirim_pengumuman.before_loop
    async def _before_kirim(self):
        await self.bot.wait_until_ready()

    async def _seed_reaksi(self, guild: discord.Guild) -> None:
        """Pastikan pesan self-role sudah punya reaksi emojinya (sekali per restart).

        Baris "yatim" (pesan tak ditemukan di semua channel) ditandai di tabel
        selfrole_orphan agar pemindaian mahal semua-channel tidak diulang
        tiap loop/restart. Flag dibersihkan saat dashboard berhenti mengirim
        baris tersebut; panel yang dibuat ulang (message_id baru) otomatis
        di-seed lagi karena flag terikat message_id.
        """
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT message_id, emoji FROM dashboard_selfroles WHERE guild_id = ?",
                (guild.id,),
            ).fetchall()
            yatim = {
                (mid, emo)
                for mid, emo in conn.execute(
                    "SELECT message_id, emoji FROM selfrole_orphan WHERE guild_id = ?",
                    (guild.id,),
                ).fetchall()
            }
        for message_id, emoji_txt in rows:
            if (message_id, emoji_txt) in self._seeded or (message_id, emoji_txt) in yatim:
                continue
            emoji = _parse_emoji(emoji_txt)
            if emoji is None:
                self._seeded.add((message_id, emoji_txt))
                continue
            try:
                msg = None
                for ch in guild.text_channels:
                    try:
                        msg = await ch.fetch_message(message_id)
                        break
                    except (discord.NotFound, discord.Forbidden):
                        continue
                if msg is None:
                    # Yatim: tandai persisten, jangan pindai ulang tiap loop.
                    with get_connection() as conn:
                        conn.execute(
                            "INSERT OR IGNORE INTO selfrole_orphan (guild_id, message_id, emoji)"
                            " VALUES (?, ?, ?)",
                            (guild.id, message_id, emoji_txt),
                        )
                        conn.commit()
                    log.warning(
                        "dashboard: pesan self-role %s tak ditemukan di semua channel "
                        "(guild %s) — ditandai yatim, lewati seed berikutnya.",
                        message_id, guild.id,
                    )
                    yatim.add((message_id, emoji_txt))
                    continue
                await msg.add_reaction(emoji)
            except (discord.Forbidden, discord.HTTPException):
                pass
            except Exception:
                log.warning("dashboard: gagal seed reaksi %s", message_id, exc_info=True)
            self._seeded.add((message_id, emoji_txt))


def _parse_emoji(tersimpan: str):
    """Ubah teks emoji simpanan jadi sesuatu yang dimengerti add_reaction."""
    s = (tersimpan or "").strip()
    if not s:
        return None
    return s  # discord.py menerima unicode maupun "<:nama:id>" langsung


def _nilai(v: object) -> str:
    if isinstance(v, bool):
        return "1" if v else "0"
    return str(v)


def _parse_warna(nilai) -> discord.Color | None:
    """Parse warna hex dashboard ('ff0000' / '#ff0000') -> discord.Color.

    Return None bila kosong/invalid — embed tetap dikirim tanpa warna.
    """
    if nilai is None:
        return None
    s = str(nilai).strip().lstrip("#")
    if not s:
        return None
    try:
        n = int(s, 16)
    except ValueError:
        return None
    if not 0 <= n <= 0xFFFFFF:
        return None
    return discord.Color(n)


def _bangun_embed(r: dict) -> discord.Embed | None:
    """Bangun discord.Embed dari payload embed_request dashboard.

    Field kosong/invalid diabaikan dengan aman; return None bila tidak ada
    konten sama sekali (embed seperti itu ditolak Discord).
    """
    title = str(r.get("title") or "").strip()[:256] or None
    desc = str(r.get("description") or "").strip()[:4096] or None
    fields = r.get("fields") or []
    footer = str(r.get("footer") or "").strip()[:2048] or None
    image_url = str(r.get("image_url") or "").strip() or None
    thumb_url = str(r.get("thumbnail_url") or "").strip() or None
    if not any([title, desc, fields, footer, image_url, thumb_url]):
        return None
    # Warna brand Finch sebagai default bila user tidak menentukan warna;
    # footer custom milik user tetap dipertahankan apa adanya.
    embed = discord.Embed(title=title, description=desc, color=_parse_warna(r.get("color")) or BRAND)
    for f in fields[:25]:  # batas field Discord
        try:
            nama = str(f["name"]).strip()[:256]
            nilai = str(f["value"]).strip()[:1024]
            if not nama or not nilai:
                continue
            embed.add_field(name=nama, value=nilai, inline=bool(f.get("inline", False)))
        except (KeyError, TypeError, AttributeError):
            continue
    if footer:
        embed.set_footer(text=footer)
    if image_url:
        embed.set_image(url=image_url)
    if thumb_url:
        embed.set_thumbnail(url=thumb_url)
    return embed


def emoji_cocok(tersimpan: str, emoji: discord.PartialEmoji) -> bool:
    """Cocokkan emoji simpanan dashboard dengan reaksi yang masuk."""
    s = (tersimpan or "").strip()
    if not s:
        return False
    if emoji.id:  # custom emoji
        return (
            s == str(emoji.id)
            or s.strip("<>: ").split(":")[-1] == str(emoji.id)
            or s == emoji.name
        )
    return s == str(emoji)


async def setup(bot: commands.Bot):
    await bot.add_cog(DashboardSync(bot))
