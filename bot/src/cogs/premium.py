"""Premium — status tier Free/VIP per server + manajemen entitlement owner.

- `/premium`: status server ini (tier efektif, expiry, pemakaian vs limit,
  perbandingan Free vs VIP, info upgrade). Publik, hanya di server.
- `/vip grant|extend|revoke|status|list`: KHUSUS owner bot (cek
  `premium.is_bot_owner` — Administrator Discord TIDAK cukup). Semua respon
  ephemeral. Mutasi dikirim ke endpoint internal dashboard
  (`POST {dashboard_url}/api/internal/entitlements`); dashboard adalah
  sumber kebenaran, bot hanya menyimpan cache lokal hasil sinkronisasi
  (`guild_entitlement_cache` via `src.utils.premium`).

Tier & limit SELALU dari `src.utils.premium` (kontrak bersama dashboard) —
cog ini tidak mendefinisikan angka limit sendiri selain membaca
FEATURE_LIMITS dari modul itu.
"""
import datetime
import logging
import os

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from src import config
from src.store import get_connection
from src.utils import premium
from src.utils.embeds import BRAND
from src.utils.waktu import parse_iso

log = logging.getLogger("finch")

#: Label tampil per feature_code (urutan = urutan FEATURE_LIMITS).
LABEL_FITUR = {
    "custom_commands": "Custom command",
    "autoresponders": "Auto-responder",
    "giveaways_active": "Giveaway aktif",
    "selfrole_panels": "Panel self-role",
    "announcements_active": "Pengumuman aktif",
}

#: Salinan darurat FEATURE_LIMITS sesuai kontrak — hanya dipakai bila modul
#: premium tidak mengeksposnya (seharusnya tidak terjadi).
_FEATURE_LIMITS_CADANGAN = {
    "custom_commands": {"free": 10, "vip": 100},
    "autoresponders": {"free": 10, "vip": 100},
    "giveaways_active": {"free": 3, "vip": 25},
    "selfrole_panels": {"free": 3, "vip": 25},
    "announcements_active": {"free": 3, "vip": 25},
}


def _feature_limits() -> dict:
    return getattr(premium, "FEATURE_LIMITS", None) or _FEATURE_LIMITS_CADANGAN


def validasi_guild_id(teks) -> int | None:
    """Snowflake Discord valid: digit semua, panjang 5..25. None bila invalid."""
    s = str(teks or "").strip()
    if not s.isdigit() or not (5 <= len(s) <= 25):
        return None
    return int(s)


def validasi_durasi(duration_days, *, wajib: bool) -> str | None:
    """Return pesan error, atau None bila durasi bisa diterima."""
    if duration_days is None:
        return "❌ Durasi wajib diisi untuk aksi ini (1–3650 hari)." if wajib else None
    if not (1 <= int(duration_days) <= 3650):
        return "❌ Durasi harus antara 1 dan 3650 hari."
    return None


def format_kedaluwarsa(expires_at, sekarang: datetime.datetime | None = None) -> str:
    """'Permanen' bila kosong; selain itu absolut + relatif.

    Contoh: 'berakhir 12 Nov 2026 (30 hari lagi)'.
    """
    if not expires_at:
        return "Permanen"
    dt = parse_iso(str(expires_at))
    if dt is None:
        return str(expires_at)
    now = sekarang or datetime.datetime.now(datetime.timezone.utc)
    tgl = dt.strftime("%d %b %Y")
    if dt <= now:
        return f"berakhir {tgl} (sudah lewat)"
    sisa = (dt - now).days
    if sisa <= 0:
        return f"berakhir {tgl} (hari ini)"
    return f"berakhir {tgl} ({sisa} hari lagi)"


def _normalisasi_ent(ent) -> dict:
    """Samakan bentuk entitlement dari cache/endpoint ke kunci standar.

    Mengembalikan dict dengan kunci: tier, status, expires_at (+ kunci asli
    lain dipertahankan). Alias yang ditoleransi: plan->tier,
    expired_at/expiry->expires_at.
    """
    if not isinstance(ent, dict):
        return {}
    hasil = dict(ent)
    hasil["tier"] = ent.get("tier") or ent.get("plan") or ""
    hasil["status"] = ent.get("status") or ""
    hasil["expires_at"] = (
        ent.get("expires_at") or ent.get("expired_at") or ent.get("expiry")
    )
    return hasil


def baca_cache_entitlement(guild_id: int) -> dict | None:
    """Entitlement dari cache lokal bot (dict ternormalisasi) atau None.

    Pakai `premium.ambil_entitlement_cache` bila modul menyediakannya;
    fallback query langsung ke tabel `guild_entitlement_cache`.
    """
    ambil = getattr(premium, "ambil_entitlement_cache", None)
    if callable(ambil):
        try:
            hasil = ambil(guild_id)
        except Exception:
            hasil = None
        if isinstance(hasil, dict):
            return _normalisasi_ent(hasil)
        if hasil is not None:
            try:
                return _normalisasi_ent(dict(hasil))
            except (TypeError, ValueError):
                pass
    try:
        with get_connection() as conn:
            ada = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
                " AND name = 'guild_entitlement_cache'"
            ).fetchone()
            if not ada:
                return None
            kolom = [
                r[1]
                for r in conn.execute(
                    "PRAGMA table_info(guild_entitlement_cache)"
                ).fetchall()
            ]
            row = conn.execute(
                "SELECT * FROM guild_entitlement_cache WHERE guild_id = ?",
                (guild_id,),
            ).fetchone()
        if row is None:
            return None
        return _normalisasi_ent(dict(zip(kolom, row)))
    except Exception:
        log.warning("premium: gagal baca cache entitlement %s", guild_id, exc_info=True)
        return None


def _teks_perbandingan() -> str:
    """Ringkasan batas Free vs VIP dari FEATURE_LIMITS."""
    baris = []
    for kode, batas in _feature_limits().items():
        label = LABEL_FITUR.get(kode, kode)
        baris.append(f"{label}: Free **{batas.get('free')}** • VIP **{batas.get('vip')}**")
    return "\n".join(baris)


def _url_upgrade() -> str:
    """URL upgrade dari config (bila field-nya ada) atau env langsung."""
    url = getattr(config.settings, "premium_upgrade_url", None)
    if not url:
        url = os.getenv("PREMIUM_UPGRADE_URL", "")
    return (url or "").strip()


class Premium(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ------------------------------------------------------------------
    # Penjaga owner (dipakai SEMUA subcommand /vip)
    # ------------------------------------------------------------------
    async def _tolak_bukan_owner(self, interaction: discord.Interaction) -> bool:
        """True bila pemanggil BUKAN owner bot (penolakan sudah dikirim).

        Tidak ada pengecualian permission Discord: Administrator server pun
        ditolak — entitlement adalah wewenang owner bot, bukan admin guild.
        """
        try:
            pemilik = bool(premium.is_bot_owner(interaction.user.id))
        except Exception:
            pemilik = False
        if pemilik:
            return False
        await interaction.response.send_message(
            "❌ Perintah ini khusus owner bot.", ephemeral=True
        )
        return True

    # ------------------------------------------------------------------
    # /premium — status server (publik)
    # ------------------------------------------------------------------
    @app_commands.command(
        name="premium", description="Lihat status Free/VIP & pemakaian server ini"
    )
    async def premium_cmd(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ Perintah ini hanya untuk di dalam server.", ephemeral=True
            )
            return
        gid = interaction.guild.id
        actor_id = interaction.user.id
        tier_guild = premium.get_effective_tier(gid)
        tier_efektif = premium.get_effective_tier(gid, actor_id=actor_id)
        cache = baca_cache_entitlement(gid)
        pemakaian = premium.hitung_pemakaian(gid)

        embed = discord.Embed(
            title=f"Status Premium — {interaction.guild.name}",
            color=BRAND,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text="Finch")
        label_tier = "VIP" if tier_guild == "vip" else "Free"
        embed.add_field(name="Tier server", value=f"**{label_tier}**", inline=True)
        if cache:
            status_teks = str(cache.get("status") or "-")
            embed.add_field(name="Status", value=status_teks, inline=True)
            embed.add_field(
                name="Berlaku sampai",
                value=format_kedaluwarsa(cache.get("expires_at")),
                inline=True,
            )
        else:
            embed.add_field(
                name="Status",
                value="Belum ada data sinkron dari dashboard",
                inline=True,
            )
        if tier_efektif != tier_guild:
            # Tier efektif beda dari tier guild murni hanya lewat bypass
            # personal owner bot — jelaskan agar tidak menyesatkan member.
            embed.add_field(
                name="Catatan untukmu",
                value=(
                    "Kamu adalah **owner bot**: batas VIP berlaku untukmu "
                    "secara personal (bypass owner), tetapi tier server ini "
                    f"tetap **{label_tier}** untuk semua member lain."
                ),
                inline=False,
            )
        baris_pakai = []
        for kode in _feature_limits():
            label = LABEL_FITUR.get(kode, kode)
            limit = premium.get_feature_limit(gid, kode)
            baris_pakai.append(f"{label}: **{pemakaian.get(kode, 0)} / {limit}**")
        embed.add_field(
            name="Pemakaian", value="\n".join(baris_pakai), inline=False
        )
        embed.add_field(
            name="Perbandingan Free vs VIP", value=_teks_perbandingan(), inline=False
        )
        url = _url_upgrade()
        if url:
            embed.add_field(
                name="Upgrade ke VIP",
                value=f"Aktifkan VIP untuk server ini di sini: {url}",
                inline=False,
            )
        else:
            embed.add_field(
                name="Upgrade ke VIP",
                value=(
                    "Aktivasi VIP saat ini dilakukan manual melalui owner bot. "
                    "Hubungi owner bot untuk mengaktifkan VIP di server ini."
                ),
                inline=False,
            )
        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # Grup /vip — owner-only
    # ------------------------------------------------------------------
    vip = app_commands.Group(
        name="vip", description="Kelola entitlement VIP (khusus owner bot)"
    )

    async def _post_entitlement(
        self,
        guild_id: int,
        action: str,
        duration_days: int | None,
        reason: str,
        actor_id: int,
    ) -> tuple[int | None, object, str | None]:
        """POST mutasi ke endpoint internal dashboard.

        Return (http_status, json_body, pesan_error). pesan_error None hanya
        bila HTTP 200 — selain itu pemanggil WAJIB melapor gagal dengan jujur.
        """
        url = (config.settings.dashboard_url or "").rstrip("/")
        secret = config.settings.dashboard_secret or ""
        if not url or not secret:
            return None, None, "integrasi dashboard tidak terkonfigurasi"
        payload = {
            "guild_id": str(guild_id),
            "action": action,
            "duration_days": duration_days,
            "reason": reason,
            "actor_id": str(actor_id),
        }
        try:
            async with aiohttp.ClientSession() as sesi:
                async with sesi.post(
                    f"{url}/api/internal/entitlements",
                    json=payload,
                    headers={"Authorization": f"Bearer {secret}"},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    try:
                        data = await resp.json()
                    except Exception:
                        data = None
                    if resp.status != 200:
                        return resp.status, data, f"dashboard menolak (HTTP {resp.status})"
                    return resp.status, data, None
        except Exception as e:  # koneksi gagal/timeout — jangan mengaku sukses
            return None, None, f"gagal menghubungi dashboard: {e}"

    async def _mutasi(
        self,
        interaction: discord.Interaction,
        guild_id_teks: str,
        action: str,
        duration_days: int | None,
        reason: str | None,
    ) -> None:
        """Alur bersama grant/extend/revoke (owner sudah dicek pemanggil)."""
        gid = validasi_guild_id(guild_id_teks)
        if gid is None:
            await interaction.response.send_message(
                "❌ `guild_id` tidak valid — harus snowflake Discord (digit, 5–25 karakter).",
                ephemeral=True,
            )
            return
        err = validasi_durasi(duration_days, wajib=(action == "extend"))
        if err:
            await interaction.response.send_message(err, ephemeral=True)
            return
        alasan = (reason or "").strip()[:200]
        await interaction.response.defer(ephemeral=True)
        status, data, pesan_err = await self._post_entitlement(
            gid, action, duration_days, alasan, interaction.user.id
        )
        if pesan_err is not None:
            detail = f" (HTTP {status})" if status is not None else ""
            await interaction.followup.send(
                f"❌ Gagal {action} VIP untuk guild `{gid}`: {pesan_err}{detail}. "
                "Tidak ada perubahan yang dilakukan.",
                ephemeral=True,
            )
            return
        ent = None
        if isinstance(data, dict):
            calon = data.get("entitlement")
            ent = calon if isinstance(calon, dict) else data
        if isinstance(ent, dict) and ent:
            try:
                premium.simpan_entitlement_cache(gid, ent)
            except Exception:
                log.warning(
                    "premium: gagal simpan cache entitlement %s", gid, exc_info=True
                )
            ent = _normalisasi_ent(ent)
        else:
            ent = {}
        tier = ent.get("tier") or premium.get_effective_tier(gid)
        status_teks = ent.get("status") or "-"
        await interaction.followup.send(
            f"✅ VIP **{action}** untuk guild `{gid}` berhasil.\n"
            f"Tier: **{tier}** • Status: {status_teks} • "
            f"Kedaluwarsa: {format_kedaluwarsa(ent.get('expires_at'))}",
            ephemeral=True,
        )

    @vip.command(name="grant", description="Aktifkan VIP untuk sebuah server (owner bot)")
    @app_commands.describe(
        guild_id="ID server (snowflake)",
        duration_days="Durasi hari (1–3650); kosongkan = permanen",
        reason="Alasan (opsional, maks 200 karakter)",
    )
    async def vip_grant(
        self,
        interaction: discord.Interaction,
        guild_id: str,
        duration_days: int | None = None,
        reason: str | None = None,
    ):
        if await self._tolak_bukan_owner(interaction):
            return
        await self._mutasi(interaction, guild_id, "grant", duration_days, reason)

    @vip.command(name="extend", description="Perpanjang VIP sebuah server (owner bot)")
    @app_commands.describe(
        guild_id="ID server (snowflake)",
        duration_days="Tambahan hari (1–3650, wajib)",
        reason="Alasan (opsional, maks 200 karakter)",
    )
    async def vip_extend(
        self,
        interaction: discord.Interaction,
        guild_id: str,
        duration_days: int | None = None,
        reason: str | None = None,
    ):
        if await self._tolak_bukan_owner(interaction):
            return
        await self._mutasi(interaction, guild_id, "extend", duration_days, reason)

    @vip.command(name="revoke", description="Cabut VIP sebuah server (owner bot)")
    @app_commands.describe(
        guild_id="ID server (snowflake)",
        reason="Alasan (opsional, maks 200 karakter)",
    )
    async def vip_revoke(
        self,
        interaction: discord.Interaction,
        guild_id: str,
        reason: str | None = None,
    ):
        if await self._tolak_bukan_owner(interaction):
            return
        await self._mutasi(interaction, guild_id, "revoke", None, reason)

    @vip.command(name="status", description="Status entitlement sebuah server (owner bot)")
    @app_commands.describe(guild_id="ID server (snowflake)")
    async def vip_status(self, interaction: discord.Interaction, guild_id: str):
        if await self._tolak_bukan_owner(interaction):
            return
        gid = validasi_guild_id(guild_id)
        if gid is None:
            await interaction.response.send_message(
                "❌ `guild_id` tidak valid — harus snowflake Discord (digit, 5–25 karakter).",
                ephemeral=True,
            )
            return
        cache = baca_cache_entitlement(gid)
        tier = premium.get_effective_tier(gid)
        if cache is None:
            await interaction.response.send_message(
                f"Guild `{gid}` — tier efektif: **{tier}**. "
                "Belum ada data entitlement di cache bot (dashboard adalah "
                "sumber kebenaran; cache terisi saat sinkronisasi berikutnya).",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            f"Guild `{gid}` — tier efektif: **{tier}**\n"
            f"Cache bot: tier **{cache.get('tier') or '-'}** • "
            f"status **{cache.get('status') or '-'}** • "
            f"kedaluwarsa: {format_kedaluwarsa(cache.get('expires_at'))}\n"
            "(Data cache lokal bot terakhir tersinkron; dashboard adalah "
            "sumber kebenaran.)",
            ephemeral=True,
        )

    @vip.command(name="list", description="Daftar entitlement dari cache bot (owner bot)")
    @app_commands.describe(page="Halaman (10 per halaman)")
    async def vip_list(self, interaction: discord.Interaction, page: int = 1):
        if await self._tolak_bukan_owner(interaction):
            return
        rows: list[dict] = []
        try:
            with get_connection() as conn:
                ada = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                    " AND name = 'guild_entitlement_cache'"
                ).fetchone()
                if ada:
                    kolom = [
                        r[1]
                        for r in conn.execute(
                            "PRAGMA table_info(guild_entitlement_cache)"
                        ).fetchall()
                    ]
                    mentah = conn.execute(
                        "SELECT * FROM guild_entitlement_cache ORDER BY guild_id"
                    ).fetchall()
                    rows = [
                        _normalisasi_ent(dict(zip(kolom, r))) for r in mentah
                    ]
        except Exception:
            log.warning("premium: gagal baca daftar entitlement", exc_info=True)
            rows = []
        if not rows:
            await interaction.response.send_message(
                "Belum ada data entitlement di cache bot "
                "(data terisi dari sinkronisasi dashboard).",
                ephemeral=True,
            )
            return
        per_halaman = 10
        halaman_maks = max(1, (len(rows) + per_halaman - 1) // per_halaman)
        halaman = min(max(1, page), halaman_maks)
        potong = rows[(halaman - 1) * per_halaman: halaman * per_halaman]
        baris = [
            f"`{r.get('guild_id')}` — **{r.get('tier') or '-'}** / "
            f"{r.get('status') or '-'} • {format_kedaluwarsa(r.get('expires_at'))}"
            for r in potong
        ]
        await interaction.response.send_message(
            f"**Entitlement (cache bot)** — halaman {halaman}/{halaman_maks}, "
            f"total {len(rows)} server:\n"
            + "\n".join(baris)
            + "\n(Data cache bot terakhir tersinkron; dashboard adalah sumber kebenaran.)",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Premium(bot))
