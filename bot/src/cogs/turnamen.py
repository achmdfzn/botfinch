"""Turnamen & game sosial — Tahap 12b.

- Turnamen susun-kata: /lomba buat (mod), /lomba ikut, /lomba main,
  /lomba jawab, /lomba info + loop penutupan tiap menit.
- /lomba kuis — kuis multiplayer real-time (state di memory per channel).
- /lomba aducepat — lomba ketik cepat via listener on_message.
- /lomba ship — skor kecocokan deterministik dua user.
"""
import asyncio
import datetime
import hashlib
import logging
import random
import time

import discord
from discord.ext import commands, tasks

from src import config
from src.store import get_connection
from src.utils.teks import acak_huruf
from src.utils import economy as eko
from src.utils.embeds import (
    finch_embed,
    koin_text,
    get_progress_bar,
    error_embed,
    sukses_embed,
)

log = logging.getLogger("finch")

# ---------------------------------------------------------------------------
# Fungsi murni (ada unit test di tests/test_tahap12b.py)
# ---------------------------------------------------------------------------

KATA_SUSUN = [
    "pioneer", "outpost", "nusa", "finch", "discord", "server", "mabar",
    "turnamen", "hadiah", "petualang", "misteri", "juara", "tantangan",
    "kemenangan", "semangat", "komunitas", "kreator", "konten", "strategi",
    "kompas", "tenda", "unggul", "harta", "karun", "samudra", "cahaya",
    "badai", "pelangi", "kawah", "rimba",
]

BANK_KUIS: list[tuple[str, str]] = [
    ("Ibukota Indonesia?", "jakarta"),
    ("Tahun kemerdekaan Indonesia?", "1945"),
    ("Presiden pertama Indonesia?", "soekarno"),
    ("Pulau terbesar di Indonesia?", "kalimantan"),
    ("7 + 8 = ?", "15"),
    ("12 × 12 = ?", "144"),
    ("100 − 37 = ?", "63"),
    ("5² + 3² = ?", "34"),
    ("Planet terdekat dari Matahari?", "merkurius"),
    ("Rumus kimia air?", "h2o"),
    ("Lambang sila pertama Pancasila?", "bintang"),
    ("Candi terbesar di Indonesia?", "borobudur"),
    ("Mata uang Indonesia?", "rupiah"),
    ("Benua terbesar di dunia?", "asia"),
    ("Organ tubuh yang memompa darah?", "jantung"),
]

KUIS_DURASI_SOAL = 20  # detik per soal
SKOR_TURNAMEN_BENAR = 100
JAWAB_COOLDOWN = 10  # detik setelah jawaban salah
HADIAH_ADUCEPAT = 200
ADUCEPAT_DURASI = 60  # detik


def acak_kata(rng) -> tuple[str, str]:
    """Pilih kata acak lalu acak hurufnya. Return (kata_asli, kata_acak)."""
    kata = rng.choice(KATA_SUSUN)
    return kata, acak_huruf(kata, rng)


def normalisasi_jawaban(teks: str) -> str:
    """Samakan format jawaban: lowercase + whitespace tunggal."""
    return " ".join(teks.strip().lower().split())


def skor_kuis_benar(pertama: bool, sisa_detik: float, durasi: float = KUIS_DURASI_SOAL) -> int:
    """Poin jawaban benar: pertama = 100 + bonus kecepatan (maks 50), sisanya = 50."""
    if not pertama:
        return 50
    bonus = int(50 * max(0.0, min(1.0, sisa_detik / durasi)))
    return 100 + bonus


def skor_ship(id_a: int, id_b: int) -> int:
    """Skor kecocokan 0–100 yang deterministik (urutan id tidak berpengaruh)."""
    seed = f"{min(id_a, id_b)}-{max(id_a, id_b)}-finch"
    h = hashlib.sha256(seed.encode()).hexdigest()
    return int(h[:2], 16) % 101


def pesan_ship(skor: int) -> str:
    """Komentar fun sesuai skor ship."""
    if skor >= 90:
        return "💖 JODOH SEJATI! Kapan nikahnya?"
    if skor >= 70:
        return "💕 Cocok banget, gas kenalan!"
    if skor >= 50:
        return "😊 Lumayan cocok, bisa dijajaki."
    if skor >= 30:
        return "🤔 Butuh usaha dikit biar klop."
    return "😅 Mending temenan aja dulu."


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------


class Turnamen(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._kata: dict[tuple[int, int], tuple[str, str]] = {}  # (gid, uid) -> (asli, acak)
        self._cd_jawab: dict[tuple[int, int], float] = {}
        self._channel_turnamen: dict[int, int] = {}  # turnamen_id -> channel_id
        self._kuis: dict[int, dict] = {}  # channel_id -> state kuis
        self._aducepat: dict[int, dict] = {}  # channel_id -> state adu-cepat
        self.cek_turnamen.start()
        self.cek_aducepat.start()

    def cog_unload(self):
        self.cek_turnamen.cancel()
        self.cek_aducepat.cancel()
        for st in self._kuis.values():
            t = st.get("task")
            if t is not None:
                t.cancel()

    # ---------------- turnamen susun-kata ----------------

    def _turnamen_aktif(self, guild_id: int, status_buka_saja: bool = False) -> int | None:
        """Return turnamen_id aktif di guild, atau None."""
        q = "SELECT id FROM turnamen WHERE guild_id = ? AND status IN ('buka','jalan')"
        if status_buka_saja:
            q = "SELECT id FROM turnamen WHERE guild_id = ? AND status = 'buka'"
        with get_connection() as conn:
            row = conn.execute(q, (guild_id,)).fetchone()
        return row[0] if row else None

    @commands.hybrid_group(name="lomba", description="🏆 Lomba Finch")
    async def lomba(self, ctx: commands.Context):
        """Bantuan grup lomba."""
        await ctx.send(
            embed=finch_embed(
                "🏆 Lomba",
                "`/lomba buat` — buat turnamen (mod)\n`/lomba ikut` — ikut turnamen\n`/lomba main` — ambil kata turnamen\n`/lomba jawab` — jawab kata turnamen\n`/lomba info` — leaderboard turnamen\n`/lomba kuis` — kuis multiplayer\n`/lomba kuis-jawab` — jawab soal kuis\n`/lomba aducepat` — lomba ketik cepat\n`/lomba ship` — cek kecocokan 💕",
                warna="game",
            ),
            ephemeral=True,
        )
    @lomba.command(name="buat", description="Buat turnamen susun-kata (khusus mod)")
    @commands.has_permissions(manage_messages=True)
    @discord.app_commands.describe(durasi_menit="Durasi turnamen dalam menit (1-120)")
    async def turnamen_buat(self, ctx: commands.Context, durasi_menit: int):
        """Buat turnamen: /lomba buat 30"""
        if ctx.guild is None:
            await ctx.send(embed=error_embed("Hanya bisa di server."), ephemeral=True)
            return
        if not 1 <= durasi_menit <= 120:
            await ctx.send(
                embed=error_embed("Durasi harus 1–120 menit."), ephemeral=True
            )
            return
        if self._turnamen_aktif(ctx.guild.id) is not None:
            await ctx.send(
                embed=error_embed("Sudah ada turnamen aktif di server ini."),
                ephemeral=True,
            )
            return
        now = discord.utils.utcnow()
        berakhir = (now + datetime.timedelta(minutes=durasi_menit)).isoformat()
        with get_connection() as conn:
            # Atomik: dua /lomba buat konkuren tidak bisa membuat dua
            # turnamen aktif sekaligus (dulu: cek SELECT dulu lalu INSERT).
            cur = conn.execute(
                "INSERT INTO turnamen (guild_id, jenis, status, dibuat, berakhir)"
                " SELECT ?, 'susunkata', 'buka', ?, ?"
                " WHERE NOT EXISTS (SELECT 1 FROM turnamen"
                " WHERE guild_id = ? AND status IN ('buka', 'jalan'))",
                (ctx.guild.id, now.isoformat(), berakhir, ctx.guild.id),
            )
            if cur.rowcount == 0:
                await ctx.send(
                    embed=error_embed("Sudah ada turnamen aktif di server ini."),
                    ephemeral=True,
                )
                return
            tid = cur.lastrowid
            conn.commit()
        self._channel_turnamen[tid] = ctx.channel.id
        hadiah = config.settings.turnamen_hadiah
        embed = finch_embed(
            "🏆 Turnamen Susun-Kata Dibuka!",
            f"Ketik `/lomba ikut` untuk join, lalu `/lomba main` untuk mulai!\n"
            f"Setiap jawaban benar = **+{SKOR_TURNAMEN_BENAR}** skor.",
            warna="game",
        )
        embed.add_field(name="Durasi", value=f"**{durasi_menit}** menit", inline=True)
        embed.add_field(name="Hadiah Juara", value=koin_text(hadiah), inline=True)
        embed.add_field(name="Peserta", value="**0**", inline=True)
        await ctx.send(embed=embed)
        log.info("Turnamen #%s dibuat di guild %s (%d mnt).", tid, ctx.guild.id, durasi_menit)

    @lomba.command(name="ikut", description="Ikut turnamen yang sedang dibuka")
    async def turnamen_ikut(self, ctx: commands.Context):
        """Ikut turnamen: /lomba ikut"""
        if ctx.guild is None:
            await ctx.send(embed=error_embed("Hanya bisa di server."), ephemeral=True)
            return
        tid = self._turnamen_aktif(ctx.guild.id, status_buka_saja=True)
        if tid is None:
            await ctx.send(
                embed=error_embed("Tidak ada turnamen yang sedang dibuka."),
                ephemeral=True,
            )
            return
        with get_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO turnamen_peserta (turnamen_id, user_id, skor)"
                " VALUES (?, ?, 0)",
                (tid, ctx.author.id),
            )
            # Peserta pertama masuk → status jalan
            conn.execute(
                "UPDATE turnamen SET status = 'jalan' WHERE id = ? AND status = 'buka'",
                (tid,),
            )
            conn.commit()
        await ctx.send(
            embed=sukses_embed(
                "Kamu terdaftar!",
                "Ketik `/lomba main` untuk dapat kata pertamamu. Semangat! 🚀",
            ),
            ephemeral=True,
        )

    @lomba.command(name="main", description="Ambil kata acak turnamen")
    async def turnamen_main(self, ctx: commands.Context):
        """Ambil kata: /lomba main"""
        if ctx.guild is None:
            await ctx.send(embed=error_embed("Hanya bisa di server."), ephemeral=True)
            return
        tid = self._turnamen_aktif(ctx.guild.id)
        if tid is None:
            await ctx.send(
                embed=error_embed("Tidak ada turnamen aktif."), ephemeral=True
            )
            return
        with get_connection() as conn:
            ok = conn.execute(
                "SELECT 1 FROM turnamen_peserta WHERE turnamen_id = ? AND user_id = ?",
                (tid, ctx.author.id),
            ).fetchone()
        if not ok:
            await ctx.send(
                embed=error_embed("Kamu belum ikut. Ketik `/lomba ikut` dulu!"),
                ephemeral=True,
            )
            return
        asli, acak = acak_kata(random)
        self._kata[(ctx.guild.id, ctx.author.id)] = (asli, acak)
        embed = finch_embed(
            "🔤 Susun Kata Ini!",
            f"## `{acak}`\n\nJawab dengan `/lomba jawab <jawaban>`",
            warna="game",
        )
        await ctx.send(embed=embed, ephemeral=True)

    @lomba.command(name="jawab", description="Jawab kata turnamen")
    @discord.app_commands.describe(jawaban="Tebakan kata yang sudah disusun")
    async def turnamen_jawab(self, ctx: commands.Context, *, jawaban: str):
        """Jawab: /lomba jawab <jawaban>"""
        if ctx.guild is None:
            await ctx.send(embed=error_embed("Hanya bisa di server."), ephemeral=True)
            return
        key = (ctx.guild.id, ctx.author.id)
        if key not in self._kata:
            await ctx.send(
                embed=error_embed("Ambil kata dulu dengan `/lomba main`!"),
                ephemeral=True,
            )
            return
        tid = self._turnamen_aktif(ctx.guild.id)
        if tid is None:
            self._kata.pop(key, None)
            await ctx.send(
                embed=error_embed("Turnamen sudah berakhir."), ephemeral=True
            )
            return
        now = time.time()
        sisa_cd = JAWAB_COOLDOWN - (now - self._cd_jawab.get(key, 0))
        if sisa_cd > 0:
            await ctx.send(
                embed=error_embed(f"Tunggu **{sisa_cd:.0f}** detik sebelum coba lagi."),
                ephemeral=True,
            )
            return
        asli, _acak = self._kata[key]
        if normalisasi_jawaban(jawaban) == normalisasi_jawaban(asli):
            with get_connection() as conn:
                conn.execute(
                    "UPDATE turnamen_peserta SET skor = skor + ?"
                    " WHERE turnamen_id = ? AND user_id = ?",
                    (SKOR_TURNAMEN_BENAR, tid, ctx.author.id),
                )
                conn.commit()
            asli2, acak2 = acak_kata(random)
            self._kata[key] = (asli2, acak2)
            await ctx.send(
                embed=sukses_embed(
                    f"Benar! +{SKOR_TURNAMEN_BENAR} skor",
                    f"Kata berikutnya: ## `{acak2}`\nJawab dengan `/lomba jawab <jawaban>`",
                ),
                ephemeral=True,
            )
        else:
            self._cd_jawab[key] = now
            await ctx.send(
                embed=error_embed(
                    f"Salah! Coba lagi ya. (cooldown {JAWAB_COOLDOWN} detik)"
                ),
                ephemeral=True,
            )

    @lomba.command(name="info", description="Lihat leaderboard turnamen")
    async def turnamen_info(self, ctx: commands.Context):
        """Info turnamen: /lomba info"""
        if ctx.guild is None:
            await ctx.send(embed=error_embed("Hanya bisa di server."), ephemeral=True)
            return
        tid = self._turnamen_aktif(ctx.guild.id)
        if tid is None:
            await ctx.send(
                embed=error_embed("Tidak ada turnamen aktif."), ephemeral=True
            )
            return
        with get_connection() as conn:
            row = conn.execute(
                "SELECT berakhir FROM turnamen WHERE id = ?", (tid,)
            ).fetchone()
            if row is None:
                # Turnamen baru saja ditutup loop di tengah command — jangan crash
                await ctx.send(
                    embed=error_embed("Tidak ada turnamen aktif."), ephemeral=True
                )
                return
            berakhir = row[0]
            top = conn.execute(
                "SELECT user_id, skor FROM turnamen_peserta WHERE turnamen_id = ?"
                " ORDER BY skor DESC LIMIT 9",
                (tid,),
            ).fetchall()
        try:
            sisa = int(
                (
                    datetime.datetime.fromisoformat(berakhir).replace(
                        tzinfo=datetime.timezone.utc
                    )
                    - discord.utils.utcnow()
                ).total_seconds()
                // 60
            )
            sisa_txt = f"**{max(sisa, 0)}** menit"
        except (ValueError, TypeError):
            sisa_txt = "-"
        embed = finch_embed(
            "🏆 Turnamen Susun-Kata",
            f"Berakhir dalam: {sisa_txt} • Hadiah juara: {koin_text(config.settings.turnamen_hadiah)}",
            warna="game",
        )
        if top:
            medals = ["🥇", "🥈", "🥉"]
            for i, (uid, skor) in enumerate(top):
                nama = f"{medals[i]} #{i + 1}" if i < 3 else f"#{i + 1}"
                embed.add_field(
                    name=nama, value=f"<@{uid}>\n**{skor}**", inline=True
                )
        else:
            embed.add_field(name="Peserta", value="Belum ada.", inline=True)
        await ctx.send(embed=embed)

    @tasks.loop(minutes=1)
    async def cek_turnamen(self):
        now = discord.utils.utcnow().isoformat()
        try:
            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT id, guild_id FROM turnamen"
                    " WHERE status IN ('buka','jalan') AND berakhir <= ?",
                    (now,),
                ).fetchall()
        except Exception:
            log.exception("Gagal baca turnamen")
            return
        for tid, gid in rows:
            try:
                await self._selesaikan_turnamen(tid, gid)
            except Exception:
                log.exception("Gagal selesaikan turnamen %s", tid)

    @cek_turnamen.before_loop
    async def _before_turnamen(self):
        await self.bot.wait_until_ready()

    async def _selesaikan_turnamen(self, tid: int, gid: int) -> None:
        # Tandai selesai DULU baru kasih hadiah (crash di tengah = hadiah hilang,
        # bukan dibayar 2x — pola aman seperti lotre). Guard status: pemanggilan
        # ganda untuk turnamen yang sama tidak payout ulang.
        with get_connection() as conn:
            cur = conn.execute(
                "UPDATE turnamen SET status = 'selesai' WHERE id = ?"
                " AND status IN ('buka', 'jalan')",
                (tid,),
            )
            if cur.rowcount == 0:
                return  # sudah diselesaikan (panggilan ganda)
            top = conn.execute(
                "SELECT user_id, skor FROM turnamen_peserta WHERE turnamen_id = ?"
                " ORDER BY skor DESC LIMIT 1",
                (tid,),
            ).fetchone()
            conn.commit()
        for key in [k for k in self._kata if k[0] == gid]:
            self._kata.pop(key, None)
            self._cd_jawab.pop(key, None)
        channel = None
        cid = self._channel_turnamen.pop(tid, None)
        if cid:
            channel = self.bot.get_channel(cid)
        if channel is None:
            guild = self.bot.get_guild(gid)
            channel = guild.system_channel if guild else None
        if top and top[1] > 0:
            uid, skor = top
            hadiah = config.settings.turnamen_hadiah
            try:
                with get_connection() as conn:
                    eko.tambah_koin(conn, gid, uid, hadiah)
            except Exception:
                log.exception("Gagal kasih hadiah turnamen %s", tid)
                return
            embed = finch_embed(
                "🏆 Turnamen Berakhir!",
                f"## 🥇 <@{uid}>\nSkor: **{skor}** • Hadiah: {koin_text(hadiah)}",
                warna="game",
            )
        else:
            embed = finch_embed(
                "🏆 Turnamen Berakhir!",
                "Tidak ada peserta yang mencetak skor. 😢",
                warna="game",
            )
        if channel is not None:
            try:
                await channel.send(embed=embed)
            except (discord.Forbidden, discord.HTTPException):
                pass
        log.info("Turnamen #%s guild %s selesai.", tid, gid)

    # ---------------- kuis multiplayer ----------------

    @lomba.command(name="kuis", description="Mulai kuis multiplayer di channel ini")
    async def kuis(self, ctx: commands.Context):
        """Mulai kuis: /lomba kuis"""
        if ctx.guild is None:
            await ctx.send(embed=error_embed("Hanya bisa di server."), ephemeral=True)
            return
        if ctx.channel.id in self._kuis:
            await ctx.send(
                embed=error_embed("Kuis sedang berjalan di channel ini!"),
                ephemeral=True,
            )
            return
        n = max(1, min(config.settings.kuis_jumlah_soal, len(BANK_KUIS)))
        soal = random.sample(BANK_KUIS, n)
        self._kuis[ctx.channel.id] = {
            "guild_id": ctx.guild.id,
            "host_id": ctx.author.id,
            "soal": soal,
            "idx": -1,
            "skor": {},
            "benar": set(),
            "terbuka": False,
            "mulai_ts": 0.0,
            "task": None,
        }
        await ctx.send(
            embed=finch_embed(
                "🎯 Kuis Dimulai!",
                f"**{n}** soal • **{KUIS_DURASI_SOAL}** detik per soal\n"
                f"Jawab dengan `/lomba kuis-jawab <teks>` — yang tercepat dapat bonus! ⚡",
                warna="game",
            )
        )
        self._kuis[ctx.channel.id]["task"] = asyncio.create_task(
            self._jalan_kuis(ctx.channel.id)
        )

    async def _jalan_kuis(self, channel_id: int) -> None:
        await self.bot.wait_until_ready()
        try:
            for i in range(99):  # dibatasi jumlah soal aktual di dalam
                st = self._kuis.get(channel_id)
                if st is None:
                    return
                if i >= len(st["soal"]):
                    break
                q, _a = st["soal"][i]
                st["idx"] = i
                st["benar"] = set()
                st["terbuka"] = True
                st["mulai_ts"] = time.time()
                channel = self.bot.get_channel(channel_id)
                if channel is None:
                    self._kuis.pop(channel_id, None)
                    return
                try:
                    await channel.send(
                        embed=finch_embed(
                            f"❓ Soal {i + 1}/{len(st['soal'])}",
                            f"## {q}\n\n⏱️ **{KUIS_DURASI_SOAL}** detik! Jawab dengan `/lomba kuis-jawab <teks>`",
                            warna="game",
                        )
                    )
                except (discord.Forbidden, discord.HTTPException):
                    self._kuis.pop(channel_id, None)
                    return
                await asyncio.sleep(KUIS_DURASI_SOAL)
                st["terbuka"] = False
                await self._rekap_soal(channel_id)
                await asyncio.sleep(3)
            await self._kuis_selesai(channel_id)
        except asyncio.CancelledError:
            # Bersihkan state juga — reload cog saat kuis berjalan tidak boleh
            # membuat /lomba kuis berikutnya selalu ditolak "sedang berjalan".
            self._kuis.pop(channel_id, None)
            raise
        except Exception:
            log.exception("Kuis error di channel %s", channel_id)
            self._kuis.pop(channel_id, None)

    async def _rekap_soal(self, channel_id: int) -> None:
        st = self._kuis.get(channel_id)
        channel = self.bot.get_channel(channel_id)
        if st is None or channel is None:
            return
        _q, a = st["soal"][st["idx"]]
        top = sorted(st["skor"].items(), key=lambda x: x[1], reverse=True)[:3]
        embed = finch_embed(
            "⏰ Waktu Habis!",
            f"Jawaban: **{a}**",
            warna="game",
        )
        if top:
            for i, (uid, skor) in enumerate(top):
                embed.add_field(
                    name=f"#{i + 1}", value=f"<@{uid}>\n**{skor}**", inline=True
                )
        else:
            embed.add_field(
                name="Perhatian", value="Belum ada yang benar.", inline=True
            )
        try:
            await channel.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

    @lomba.command(name="kuis-jawab", description="Jawab soal kuis yang berjalan")
    @discord.app_commands.describe(teks="Jawabanmu")
    async def jawab(self, ctx: commands.Context, *, teks: str):
        """Jawab kuis: /lomba kuis-jawab <teks>"""
        st = self._kuis.get(ctx.channel.id) if ctx.guild else None
        if not st or not st.get("terbuka"):
            await ctx.send(
                embed=error_embed("Tidak ada soal kuis yang sedang dibuka."),
                ephemeral=True,
            )
            return
        if ctx.author.id in st["benar"]:
            await ctx.send(
                embed=error_embed("Kamu sudah menjawab benar soal ini!"),
                ephemeral=True,
            )
            return
        _q, a = st["soal"][st["idx"]]
        if normalisasi_jawaban(teks) == normalisasi_jawaban(a):
            pertama = len(st["benar"]) == 0
            sisa = max(0.0, KUIS_DURASI_SOAL - (time.time() - st["mulai_ts"]))
            poin = skor_kuis_benar(pertama, sisa)
            st["skor"][ctx.author.id] = st["skor"].get(ctx.author.id, 0) + poin
            st["benar"].add(ctx.author.id)
            bonus = " ⚡ **Tercepat!**" if pertama else ""
            await ctx.send(f"✅ {ctx.author.mention} benar! **+{poin}**{bonus}")
        else:
            await ctx.send(
                embed=error_embed("Kurang tepat, coba lagi!"), ephemeral=True
            )

    async def _kuis_selesai(self, channel_id: int) -> None:
        st = self._kuis.pop(channel_id, None)
        if not st:
            return
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            return
        top = sorted(st["skor"].items(), key=lambda x: x[1], reverse=True)
        if not top:
            embed = finch_embed(
                "🎯 Kuis Selesai!",
                "Tidak ada yang menjawab benar satupun. 😢",
                warna="game",
            )
        else:
            from src.cogs.dashboard_sync import modul_aktif

            uid, poin = top[0]
            hadiah = config.settings.kuis_reward * 10
            dibayar = False
            if modul_aktif(st["guild_id"], "economy_enabled"):
                try:
                    with get_connection() as conn:
                        eko.tambah_koin(conn, st["guild_id"], uid, hadiah)
                    dibayar = True
                except Exception:
                    log.exception("Gagal kasih hadiah kuis")
                    return
            hadiah_txt = (
                koin_text(hadiah)
                if dibayar
                else "_tanpa hadiah (modul ekonomi dimatikan)_"
            )
            embed = finch_embed(
                "🎯 Kuis Selesai!",
                f"## 🥇 <@{uid}>\n**{poin}** poin • Hadiah: {hadiah_txt}",
                warna="game",
            )
            for i, (u2, p2) in enumerate(top[1:4], start=2):
                embed.add_field(
                    name=f"#{i}", value=f"<@{u2}>\n**{p2}**", inline=True
                )
        try:
            await channel.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

    # ---------------- adu cepat ----------------

    @lomba.command(name="aducepat", description="Lomba ketik cepat — yang pertama menang!")
    async def aducepat(self, ctx: commands.Context):
        """Mulai adu cepat: /lomba aducepat"""
        if ctx.guild is None:
            await ctx.send(embed=error_embed("Hanya bisa di server."), ephemeral=True)
            return
        ses = self._aducepat.get(ctx.channel.id)
        if ses and time.time() < ses["berakhir"]:
            await ctx.send(
                embed=error_embed("Sesi adu-cepat sedang berjalan di channel ini!"),
                ephemeral=True,
            )
            return
        kata = random.choice(KATA_SUSUN)
        self._aducepat[ctx.channel.id] = {
            "kata": kata,
            "berakhir": time.time() + ADUCEPAT_DURASI,
            "guild_id": ctx.guild.id,
        }
        await ctx.send(
            embed=finch_embed(
                "⚡ ADU CEPAT!",
                f"Ketik **persis** seperti ini:\n## `{kata}`\n\n"
                f"⏱️ {ADUCEPAT_DURASI} detik! Pemenang: {koin_text(HADIAH_ADUCEPAT)}",
                warna="game",
            )
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        ses = self._aducepat.get(message.channel.id)
        if not ses:
            return
        if time.time() >= ses["berakhir"]:
            return  # biar loop cek_aducepat yang umumkan habis
        from src.cogs.dashboard_sync import modul_aktif

        if not modul_aktif(message.guild.id, "economy_enabled"):
            # Modul ekonomi dimatikan di tengah sesi: hentikan tanpa hadiah
            # (pola sama seperti susun-kata di minigames).
            self._aducepat.pop(message.channel.id, None)
            try:
                await message.channel.send(
                    "⚡ Adu cepat dihentikan: modul ekonomi dimatikan oleh admin server ini."
                )
            except (discord.Forbidden, discord.HTTPException):
                pass
            return
        if message.content.strip().lower() != ses["kata"].lower():
            return
        # Pemenang!
        del self._aducepat[message.channel.id]
        try:
            with get_connection() as conn:
                eko.tambah_koin(conn, ses["guild_id"], message.author.id, HADIAH_ADUCEPAT)
        except Exception:
            log.exception("Gagal kasih hadiah adu-cepat")
            return
        try:
            await message.channel.send(
                embed=sukses_embed(
                    "Pemenang Adu Cepat!",
                    f"{message.author.mention} tercepat mengetik `{ses['kata']}`!\n"
                    f"Hadiah: {koin_text(HADIAH_ADUCEPAT)}",
                )
            )
        except (discord.Forbidden, discord.HTTPException):
            pass

    @tasks.loop(seconds=30)
    async def cek_aducepat(self):
        now = time.time()
        habis = [
            cid for cid, ses in self._aducepat.items() if now >= ses["berakhir"]
        ]
        for cid in habis:
            ses = self._aducepat.pop(cid, None)
            if not ses:
                continue
            channel = self.bot.get_channel(cid)
            if channel is None:
                continue
            try:
                await channel.send(
                    embed=finch_embed(
                        "⏰ Waktu Habis",
                        f"Tidak ada yang berhasil mengetik `{ses['kata']}` tepat waktu.",
                        warna="game",
                    )
                )
            except (discord.Forbidden, discord.HTTPException):
                pass

    @cek_aducepat.before_loop
    async def _before_aducepat(self):
        await self.bot.wait_until_ready()

    # ---------------- ship ----------------

    @lomba.command(name="ship", description="Cek kecocokan dua orang 💕")
    @discord.app_commands.describe(a="Orang pertama", b="Orang kedua")
    async def ship(
        self, ctx: commands.Context, a: discord.Member, b: discord.Member
    ):
        """Ship: /lomba ship @a @b"""
        if a.bot or b.bot:
            await ctx.send(
                embed=error_embed("Bot tidak bisa di-ship 😅"), ephemeral=True
            )
            return
        if a.id == b.id:
            await ctx.send(
                embed=error_embed("Ship dengan diri sendiri? Cinta diri itu baik sih."),
                ephemeral=True,
            )
            return
        skor = skor_ship(a.id, b.id)
        bar = get_progress_bar(skor, 100)
        embed = finch_embed(
            f"💕 {a.display_name} × {b.display_name}",
            f"## {skor}%\n`{bar}`\n\n{pesan_ship(skor)}",
            warna="sosial",
        )
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Turnamen(bot))
