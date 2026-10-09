"""Slowmode manual ala Dyno: /slowmode dan /slowmode-info.

Berbeda dari slowmode OTOMATIS anti-spam di moderation.py::_cek_slowmode
(jangan diubah): modul ini memberi kontrol manual ke moderator untuk
mengatur atau mematikan jeda antar pesan di sebuah text channel.
"""

import discord
from discord.ext import commands

from src.utils import embeds
from src.utils.toggle import cek_toggle

SLOWMODE_MIN = 0
SLOWMODE_MAX = 21600  # 6 jam — batas maksimum Discord


def format_durasi(detik: int) -> str:
    """'30' -> '30 detik', '300' -> '5 menit', '3600' -> '1 jam'."""
    if detik >= 3600 and detik % 3600 == 0:
        return f"{detik // 3600} jam"
    if detik >= 60 and detik % 60 == 0:
        return f"{detik // 60} menit"
    return f"{detik} detik"


def validasi_detik(detik: int) -> str | None:
    """Return pesan error bila `detik` di luar 0–21600, None bila valid."""
    if detik < SLOWMODE_MIN or detik > SLOWMODE_MAX:
        return (
            f"❌ Nilai slowmode harus antara {SLOWMODE_MIN}–{SLOWMODE_MAX} detik "
            f"(0 = matikan)."
        )
    return None


def pilih_target(ctx: commands.Context, channel) -> tuple:
    """Tentukan channel target slowmode.

    Return (target, error): target adalah discord.TextChannel bila valid,
    error adalah pesan ramah bila channel tidak cocok.
    """
    if ctx.guild is None:
        return None, "❌ Slowmode hanya bisa dipakai di server."
    target = channel or ctx.channel
    if not isinstance(target, discord.TextChannel):
        return None, "❌ Slowmode hanya bisa dipasang di text channel."
    return target, None


class Slowmode(commands.Cog):
    """Kontrol slowmode manual per channel."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_check(self, ctx: commands.Context) -> bool:
        """Blokir command bila modul dimatikan per-server via dashboard."""
        return await cek_toggle(
            ctx, "slowmode_enabled", "Modul slowmode dimatikan oleh admin server ini."
        )

    async def _reply(self, ctx: commands.Context, msg: str = None, *, embed: discord.Embed = None, ephemeral: bool = False):
        """Kirim balasan (prefix/slash). Pola sama seperti cog moderation."""
        content = msg
        kw = dict(ephemeral=ephemeral)
        if embed:
            kw["embed"] = embed
        if ctx.interaction:
            if not ctx.interaction.response.is_done():
                await ctx.interaction.response.send_message(content, **kw)
                return None
            return await ctx.followup.send(content, **kw)
        return await ctx.send(content, embed=embed)

    @commands.hybrid_command(
        name="slowmode",
        description="Atur slowmode channel teks (0–21600 detik; 0 = matikan)",
    )
    @commands.has_permissions(manage_channels=True)
    @discord.app_commands.describe(
        detik="Jeda antar pesan dalam detik (0 = matikan)",
        channel="Channel teks target (default: channel ini)",
    )
    async def slowmode(
        self,
        ctx: commands.Context,
        detik: discord.app_commands.Range[int, SLOWMODE_MIN, SLOWMODE_MAX],
        channel: discord.abc.GuildChannel | None = None,
    ):
        """Atur slowmode channel teks (khusus moderator): !slowmode 30 / /slowmode 30 #umum."""
        galat = validasi_detik(detik)
        if galat:
            await self._reply(ctx, galat, ephemeral=True)
            return
        target, galat = pilih_target(ctx, channel)
        if galat:
            await self._reply(ctx, galat, ephemeral=True)
            return
        try:
            await target.edit(
                slowmode_delay=detik,
                reason=f"Slowmode manual oleh {ctx.author} ({ctx.author.id})",
            )
        except discord.Forbidden:
            await self._reply(
                ctx,
                "❌ Bot tidak punya izin mengubah channel ini. "
                "Pastikan bot punya izin *Manage Channels* dan role bot "
                "berada di atas role yang mengatur channel.",
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            await self._reply(
                ctx, "❌ Gagal mengatur slowmode. Coba lagi.", ephemeral=True
            )
            return

        if detik == 0:
            judul, deskripsi = "⏱️ Slowmode Dimatikan", (
                f"Slowmode di {target.mention} sudah dimatikan — "
                "semua orang bisa mengirim pesan lagi tanpa jeda."
            )
        else:
            judul, deskripsi = "⏱️ Slowmode Diatur", (
                f"Slowmode di {target.mention} diatur ke **{format_durasi(detik)}** "
                f"(`{detik}` detik). Anggota harus menunggu sebelum mengirim pesan lagi."
            )
        embed = embeds.base_embed(judul, deskripsi)
        embed.add_field(name="Moderator", value=ctx.author.display_name, inline=True)
        await self._reply(ctx, embed=embed)

    @commands.hybrid_command(
        name="slowmode-info",
        description="Lihat status slowmode channel teks saat ini",
    )
    @discord.app_commands.describe(
        channel="Channel teks yang dicek (default: channel ini)",
    )
    async def slowmode_info(
        self,
        ctx: commands.Context,
        channel: discord.abc.GuildChannel | None = None,
    ):
        """Tampilkan slowmode aktif channel (bisa dipakai semua user): /slowmode-info #umum."""
        target, galat = pilih_target(ctx, channel)
        if galat:
            await self._reply(ctx, galat, ephemeral=True)
            return
        jeda = target.slowmode_delay or 0
        if jeda == 0:
            deskripsi = f"Tidak ada slowmode di {target.mention} — semua orang bisa mengirim pesan tanpa jeda."
        else:
            deskripsi = (
                f"Slowmode di {target.mention} aktif: **{format_durasi(jeda)}** "
                f"(`{jeda}` detik) antar pesan."
            )
        embed = embeds.base_embed("⏱️ Status Slowmode", deskripsi)
        await self._reply(ctx, embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Slowmode(bot))
