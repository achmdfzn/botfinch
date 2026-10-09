"""Perintah umum (hybrid: `!` + `/`)."""
import logging
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from src.utils.embeds import base_embed
from src.utils.views import TimeoutSafeView, bind_view_message

log = logging.getLogger("finch")


# ---------------------------------------------------------------------------
# /bantuan — help INTERAKTIF & DINAMIS
#
# Daftar perintah dibangun LANGSUNG dari `bot.tree` (live), bukan hardcode:
# tambah/hapus command di cog mana pun otomatis tercermin di sini tanpa
# menyentuh file ini. Cache per proses, di-rebuild bila jumlah command
# berubah.
# ---------------------------------------------------------------------------

#: Metadata kategori: label tampil, 1 emoji (diet), deskripsi singkat.
KATEGORI_BANTUAN = {
    "umum": {"label": "Umum", "emoji": "🏠", "deskripsi": "Perintah dasar untuk semua member"},
    "level": {"label": "Level & XP", "emoji": "⭐", "deskripsi": "XP otomatis tiap chat & voice — naikkan levelmu"},
    "ekonomi": {"label": "Ekonomi & Game", "emoji": "🪙", "deskripsi": "Koin, dagang, game, dan quest harian"},
    "sosial": {"label": "Sosial", "emoji": "💬", "deskripsi": "Profil, komunitas, dan interaksi member"},
    "moderasi": {"label": "Moderasi", "emoji": "🛡️", "deskripsi": "Peralatan moderator server"},
    "utilitas": {"label": "Utilitas", "emoji": "🧰", "deskripsi": "Alat bantu server & voice channel"},
    "event": {"label": "Event & Giveaway", "emoji": "🎉", "deskripsi": "Giveaway, event, dan turnamen"},
    "server": {"label": "Pengaturan Server", "emoji": "⚙️", "deskripsi": "Konfigurasi perilaku bot di server"},
}

#: Urutan tampil kategori di select menu & halaman "Semua".
URUTAN_KATEGORI = ["umum", "level", "ekonomi", "sosial", "moderasi", "utilitas", "event", "server"]

#: Nama class Cog -> kunci kategori. WAJIB mencakup semua 41 cog;
#: cog yang tak terpetakan jatuh ke "lainnya" (seharusnya selalu kosong).
COG_KE_KATEGORI = {
    # Umum
    "General": "umum",
    "Afk": "umum",
    "Reminders": "umum",
    "Tickets": "umum",
    "Polls": "umum",
    "Bump": "umum",
    # Level & XP
    "Leveling": "level",
    "VoiceXP": "level",
    "Leaderboard": "level",
    "Achievement": "level",
    # Ekonomi & Game
    "Economy": "ekonomi",
    "EkonomiPlus": "ekonomi",
    "MiniGames": "ekonomi",
    "Shop": "ekonomi",
    "Quests": "ekonomi",
    "Season": "ekonomi",
    "Counting": "ekonomi",
    "Engagement": "ekonomi",
    # Sosial
    "Sosial": "sosial",
    "Profil": "sosial",
    "Birthday": "sosial",
    "Saran": "sosial",
    "Invites": "sosial",
    "Starboard": "sosial",
    # Moderasi
    "Moderation": "moderasi",
    "ModerasiPlus": "moderasi",
    "AutoMod": "moderasi",
    "Verification": "moderasi",
    "Report": "moderasi",
    # Utilitas
    "Utilitas": "utilitas",
    "TempVC": "utilitas",
    # Event & Giveaway
    "Giveaway": "event",
    "Events": "event",
    "Turnamen": "event",
    # Pengaturan Server
    "Responder": "server",
    "SelfRoles": "server",
    "Sticky": "server",
    "Twitch": "server",
    "Youtube": "server",
    "DashboardSync": "server",
    "ServerStats": "server",
}

_BATAS_FIELD = 950  # jaga-jaga di bawah limit Discord 1024 char/field
_PANJANG_DESKRIPSI = 90  # deskripsi per command dipotong di sini

_cache_bantuan: dict = {"jumlah": None, "data": None}


def _nama_cog_pemilik(cmd) -> str | None:
    """Nama class Cog pemilik sebuah app command.

    Urutan resolusi: `cmd.cog` -> `binding` (cog instance yang di-bind
    discord.py untuk hybrid command) -> `callback.__self__` -> `__qualname__`.
    """
    cog = getattr(cmd, "cog", None)
    if cog is not None:
        return type(cog).__name__
    binding = getattr(cmd, "binding", None)
    if binding is not None:
        return type(binding).__name__
    cb = getattr(cmd, "callback", None)
    pemilik = getattr(cb, "__self__", None) if cb is not None else None
    if pemilik is not None:
        return type(pemilik).__name__
    qual = getattr(cb, "__qualname__", "") or ""
    if "." in qual:
        return qual.rsplit(".", 1)[0]
    return None


def _kumpulkan_perintah(tree) -> dict[str, list[tuple[str, str]]]:
    """Jelajahi tree -> {kategori: [(qualified_name, deskripsi), ...]}.

    - Context menu & command hidden dilewati (bukan slash command).
    - Subcommand grup tampil sebagai `/grup sub`.
    - Cog yang tak terpetakan -> kategori "lainnya".
    """
    hasil: dict[str, list[tuple[str, str]]] = {}

    def kunjungi(cmd, prefix: str = ""):
        if getattr(cmd, "hidden", False):
            return
        if isinstance(cmd, discord.app_commands.ContextMenu):
            return  # klik-kanan pesan/user, bukan slash command
        if isinstance(cmd, discord.app_commands.Group):
            for sub in cmd.commands:
                kunjungi(sub, f"{prefix} {cmd.name}".strip())
            return
        qname = "/" + " ".join(f"{prefix} {cmd.name}".split())
        kategori = COG_KE_KATEGORI.get(_nama_cog_pemilik(cmd), "lainnya")
        hasil.setdefault(kategori, []).append((qname, (cmd.description or "").strip()))

    for cmd in tree.get_commands():
        kunjungi(cmd)
    for daftar in hasil.values():
        daftar.sort(key=lambda item: item[0].lower())
    return hasil


def bangun_data_bantuan(tree) -> dict[str, list[tuple[str, str]]]:
    """Data help per kategori, di-cache per proses.

    Cache di-rebuild otomatis bila jumlah command di tree berubah
    (mis. cog di-load/unload ulang saat bot jalan).
    """
    data = _kumpulkan_perintah(tree)
    jumlah = sum(len(v) for v in data.values())
    if _cache_bantuan["data"] is not None and _cache_bantuan["jumlah"] == jumlah:
        return _cache_bantuan["data"]
    _cache_bantuan["jumlah"] = jumlah
    _cache_bantuan["data"] = data
    return data


def _baris_perintah(qname: str, deskripsi: str) -> str:
    """Satu baris ramah HP: `/cmd` — deskripsi singkat."""
    deskripsi = " ".join(deskripsi.split())  # rapikan whitespace/newline
    if len(deskripsi) > _PANJANG_DESKRIPSI:
        deskripsi = deskripsi[:_PANJANG_DESKRIPSI].rstrip() + "…"
    return f"`{qname}` — {deskripsi}" if deskripsi else f"`{qname}`"


def _bagi_ke_field(baris: list[str]) -> list[list[str]]:
    """Pecah daftar baris jadi beberapa field, masing-masing < 950 char."""
    fields: list[list[str]] = []
    saat_ini: list[str] = []
    panjang = 0
    for b in baris:
        tambahan = len(b) + (1 if saat_ini else 0)
        if saat_ini and panjang + tambahan > _BATAS_FIELD:
            fields.append(saat_ini)
            saat_ini = []
            panjang = 0
        saat_ini.append(b)
        panjang += len(b) + (1 if len(saat_ini) > 1 else 0)
    if saat_ini:
        fields.append(saat_ini)
    return fields


def _embed_kategori(kunci: str, data: dict, author) -> discord.Embed:
    """Embed daftar perintah satu kategori (ramah HP)."""
    meta = KATEGORI_BANTUAN.get(
        kunci, {"label": "Lainnya", "emoji": "📦", "deskripsi": "Perintah lain"}
    )
    daftar = data.get(kunci, [])
    embed = base_embed(f"{meta['emoji']} Finch — {meta['label']}", meta["deskripsi"])
    grup_field = _bagi_ke_field([_baris_perintah(q, d) for q, d in daftar])
    for i, grup in enumerate(grup_field):
        nama = "Perintah" if len(grup_field) == 1 else f"Perintah {i + 1}/{len(grup_field)}"
        embed.add_field(name=nama, value="\n".join(grup), inline=False)
    if kunci == "moderasi":
        embed.add_field(
            name="Izin",
            value="Sebagian perintah butuh izin Manage Messages / Kelola Server.",
            inline=False,
        )
        perms = getattr(author, "guild_permissions", None)
        if not bool(getattr(perms, "manage_messages", False)):
            embed.add_field(
                name="Perhatian",
                value="Kamu bukan moderator — perintah moderasi akan ditolak.",
                inline=False,
            )
    return embed


def _embed_semua(data: dict, author) -> discord.Embed:
    """Halaman ringkasan: daftar kategori + jumlah command + tips."""
    total = sum(len(v) for v in data.values())
    embed = base_embed(
        "📚 Finch — Daftar Perintah",
        f"Prefix `!` atau `/` — contoh: `!status` = `/status`\n"
        f"Total **{total}** perintah. Pilih kategori di bawah untuk detail.",
    )
    for kunci in URUTAN_KATEGORI:
        daftar = data.get(kunci, [])
        if not daftar:
            continue
        meta = KATEGORI_BANTUAN[kunci]
        embed.add_field(name=meta["label"], value=f"{len(daftar)} perintah", inline=True)
    if data.get("lainnya"):
        embed.add_field(name="Lainnya", value=f"{len(data['lainnya'])} perintah", inline=True)
    embed.add_field(
        name="Tips",
        value="Ketik `/` di chat untuk melihat semua slash command + deskripsinya.",
        inline=False,
    )
    return embed


class HelpView(TimeoutSafeView):
    """Help interaktif: select kategori, hanya author yang bisa ganti.

    Timeout 120 detik — `TimeoutSafeView.on_timeout` menonaktifkan select
    di pesan aslinya.
    """

    def __init__(self, author: discord.Member, bot: commands.Bot):
        super().__init__(timeout=120)
        self.author = author
        self.bot = bot
        self.add_item(self._buat_select())

    def _buat_select(self) -> discord.ui.Select:
        data = bangun_data_bantuan(self.bot.tree)
        total = sum(len(v) for v in data.values())
        options = [
            discord.SelectOption(
                label="Semua",
                description=f"Ringkasan {total} perintah",
                emoji="📚",
                value="semua",
            )
        ]
        for kunci in URUTAN_KATEGORI:
            daftar = data.get(kunci, [])
            if not daftar:
                continue
            meta = KATEGORI_BANTUAN[kunci]
            options.append(
                discord.SelectOption(
                    label=meta["label"],
                    description=f"{len(daftar)} perintah",
                    emoji=meta["emoji"],
                    value=kunci,
                )
            )
        if data.get("lainnya"):
            options.append(
                discord.SelectOption(
                    label="Lainnya",
                    description=f"{len(data['lainnya'])} perintah",
                    emoji="📦",
                    value="lainnya",
                )
            )
        select = discord.ui.Select(
            placeholder="Pilih kategori...", min_values=1, max_values=1, options=options
        )

        async def _callback(interaction: discord.Interaction):
            await self._ganti_kategori(interaction, select)

        select.callback = _callback
        return select

    async def _ganti_kategori(self, interaction: discord.Interaction, select: discord.ui.Select):
        """Callback select — dibungkus try/except agar interaction
        kedaluwarsa (10062/40060) tidak meledakkan bot."""
        try:
            if interaction.user.id != self.author.id:
                await interaction.response.send_message(
                    "Hanya yang memanggil bantuan yang bisa ganti kategori.",
                    ephemeral=True,
                )
                return
            data = bangun_data_bantuan(self.bot.tree)
            kunci = select.values[0]
            if kunci == "semua":
                embed = _embed_semua(data, self.author)
            else:
                embed = _embed_kategori(kunci, data, self.author)
            await interaction.response.edit_message(embed=embed, view=self)
        except (discord.NotFound, discord.HTTPException):
            # Interaction mati/kedaluwarsa — tidak ada yang bisa dilakukan.
            log.warning("bantuan: interaction kedaluwarsa saat ganti kategori.")


class General(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="status", description="Status & kesehatan bot Finch")
    async def status(self, ctx: commands.Context):
        """Status bot: !status / /status"""
        latency = round(self.bot.latency * 1000)
        start = getattr(self.bot, "start_time", None)
        if start is not None:
            delta = datetime.now(timezone.utc) - start
            total = int(delta.total_seconds())
            hari, sisa = divmod(total, 86400)
            jam, sisa = divmod(sisa, 3600)
            menit, _ = divmod(sisa, 60)
            bagian = []
            if hari:
                bagian.append(f"{hari}h")
            if jam:
                bagian.append(f"{jam}j")
            bagian.append(f"{menit}m")
            uptime = " ".join(bagian)
        else:
            uptime = "-"
        embed = base_embed("Finch — Status", "Online — semua sistem berjalan normal")
        embed.add_field(name="Latency", value=f"{latency} ms", inline=True)
        embed.add_field(name="Uptime", value=uptime, inline=True)
        embed.add_field(name="Server", value=str(len(self.bot.guilds)), inline=True)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="serverinfo", description="Info server ini")
    async def serverinfo(self, ctx: commands.Context):
        """Info server: !serverinfo / /serverinfo"""
        if ctx.guild is None:
            await ctx.send("❌ Hanya bisa di server.", ephemeral=True)
            return
        await ctx.send(embed=build_serverinfo_embed(ctx.guild))

    @commands.hybrid_command(name="userinfo", description="Lihat info seorang member")
    @app_commands.describe(user="Member yang mau dilihat (default: kamu sendiri)")
    async def userinfo(self, ctx: commands.Context, user: discord.Member | None = None):
        """Info member: !userinfo [@user] / /userinfo"""
        target = user or ctx.author
        embed = base_embed(f"👤 {target.display_name}")
        if target.display_avatar:
            embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Username", value=str(target), inline=True)
        embed.add_field(name="ID", value=str(target.id), inline=True)
        embed.add_field(name="Akun dibuat", value=target.created_at.strftime("%d %b %Y"), inline=True)
        if isinstance(target, discord.Member):
            if target.joined_at:
                embed.add_field(name="Gabung server", value=target.joined_at.strftime("%d %b %Y"), inline=True)
            roles = [r.mention for r in target.roles if r.name != "@everyone"][:5]
            embed.add_field(
                name=f"Roles ({len(target.roles) - 1})",
                value=" ".join(roles) if roles else "-",
                inline=True,
            )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="bantuan", description="Daftar perintah Finch")
    async def bantuan(self, ctx: commands.Context):
        """Daftar perintah: !bantuan / /bantuan"""
        view = HelpView(ctx.author, ctx.bot)
        try:
            sent = await ctx.send(
                embed=_embed_semua(bangun_data_bantuan(ctx.bot.tree), ctx.author),
                view=view,
            )
        except discord.HTTPException:
            # Interaction mati (mis. 10062 Unknown interaction) sebelum sempat
            # dibalas — tidak ada yang bisa dilakukan selain catat.
            log.warning("bantuan: gagal kirim respon awal (interaction mati).")
            return
        await bind_view_message(ctx, view, sent)


def build_serverinfo_embed(guild: discord.Guild) -> discord.Embed:
    """Embed info server yang kaya: ID, owner, tanggal, boost, channel, role,
    emoji, dan breakdown member manusia/bot (kalau cache member tersedia)."""
    embed = base_embed(f"🏠 {guild.name}")
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    # ID & tanggal dibuat (monospace = data tabular)
    embed.add_field(name="ID Server", value=f"`{guild.id}`", inline=True)
    embed.add_field(
        name="Dibuat", value=guild.created_at.strftime("%d %b %Y"), inline=True
    )
    embed.add_field(
        name="Owner", value=guild.owner.mention if guild.owner else "-", inline=True
    )
    # Member: total + breakdown manusia/bot bila cache tersedia
    total = guild.member_count if guild.member_count else len(guild.members or [])
    if guild.members:
        bot_n = sum(1 for m in guild.members if getattr(m, "bot", False))
        manusia_n = len(guild.members) - bot_n
        member_v = f"`{total}` (`{manusia_n}` manusia / `{bot_n}` bot)"
    else:
        member_v = f"`{total}`"
    embed.add_field(name="Member", value=member_v, inline=True)
    embed.add_field(name="Role", value=f"`{len(guild.roles)}`", inline=True)
    embed.add_field(name="Emoji", value=f"`{len(guild.emojis)}`", inline=True)
    # Channel: teks / suara
    embed.add_field(
        name="Channel",
        value=(
            f"`{len(guild.text_channels)}` teks / "
            f"`{len(guild.voice_channels)}` suara"
        ),
        inline=True,
    )
    embed.add_field(
        name="Boost",
        value=f"Level `{guild.premium_tier}` (`{guild.premium_subscription_count or 0}` boost)",
        inline=True,
    )
    embed.add_field(name="File", value=f"Limit `{guild.filesize_limit // 1048576} MB`", inline=True)
    return embed


async def setup(bot: commands.Bot):
    await bot.add_cog(General(bot))
