"""Verifikasi member baru (anti-nuke / anti-raider) — pakai tombol.

Alur:
1. Member join → dapat role "Belum Verifikasi" (kalau belum punya role "Member").
2. Moderator memasang panel SEKALI via `/verifikasi` di channel verifikasi.
3. Member klik tombol "Verifikasi" → dapat role "Member", role lama dicabut.

Tombol bersifat persistent (timeout=None + custom_id) dan didaftarkan ulang
di setup() sehingga tetap berfungsi setelah bot restart.
"""
import logging

import discord
from discord.ext import commands

from src import config
from src.utils import modlog
from src.utils.embeds import base_embed

log = logging.getLogger("finch")

VERIFY_CUSTOM_ID = "finch:verify-button"


def _find_roles(guild: discord.Guild):
    verified = discord.utils.get(guild.roles, name=config.settings.verified_role_name)
    unverified = discord.utils.get(
        guild.roles, name=config.settings.unverified_role_name
    )
    return verified, unverified


def build_verify_panel(guild_name: str) -> discord.Embed:
    return base_embed(
        "🔐 Verifikasi Dulu Yuk!",
        "Biar bisa chat di server ini, klik tombol **Verifikasi** di bawah.\n\n"
        "1. Baca rules server dulu\n"
        "2. Klik tombol **Verifikasi**\n\n"
        f"Setelah itu kamu dapat role Member. Selamat bergabung di **{guild_name}**! 🎮",
    )


async def _do_verify(member: discord.Member) -> str | None:
    """Eksekusi verifikasi. Return pesan untuk user, atau None kalau sukses."""
    verified, unverified = _find_roles(member.guild)
    if verified is None:
        return (
            f"❌ Role `{config.settings.verified_role_name}` belum dibuat. "
            "Hubungi moderator ya."
        )
    if verified in member.roles:
        return "✅ Kamu sudah terverifikasi, have fun! 🎮"
    try:
        await member.add_roles(verified, reason="Verifikasi via tombol")
        if unverified is not None and unverified in member.roles:
            await member.remove_roles(unverified, reason="Verifikasi via tombol")
    except discord.Forbidden:
        log.warning(
            "Gagal verifikasi %s — role bot harus DI ATAS role verifikasi.", member
        )
        return "❌ Bot tidak punya izin (role bot harus di atas role verifikasi)."
    return None


class VerifyButtonView(discord.ui.View):
    """Persistent view — timeout=None agar tombol tetap hidup setelah restart."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Verifikasi",
        style=discord.ButtonStyle.success,
        custom_id=VERIFY_CUSTOM_ID,
    )
    async def verify_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        member = interaction.user
        if not isinstance(member, discord.Member) or member.bot:
            await interaction.response.send_message(
                "❌ Tombol ini hanya bisa dipakai member server.", ephemeral=True
            )
            return

        hasil = await _do_verify(member)
        if hasil is not None:
            await interaction.response.send_message(hasil, ephemeral=True)
            return

        await interaction.response.send_message(
            f"🎉 Selamat datang, {member.mention}! Kamu sudah terverifikasi.",
            ephemeral=True,
        )
        await modlog.log_event(
            interaction.client,
            "✅ Member terverifikasi",
            f"{member.mention} (`{member}`) lolos verifikasi.",
            discord.Color.green(),
        )


class Verification(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        verified, unverified = _find_roles(member.guild)
        if verified is None or unverified is None:
            log.warning(
                "Role verifikasi belum dibuat (butuh '%s' & '%s'). Lewati.",
                config.settings.verified_role_name,
                config.settings.unverified_role_name,
            )
            return

        # yang sudah verified (rejoin) jangan dikasih unverified lagi
        if verified in member.roles:
            return
        if unverified not in member.roles:
            try:
                await member.add_roles(unverified, reason="Menunggu verifikasi")
            except discord.Forbidden:
                log.warning(
                    "Gagal kasih role ke %s — role bot harus DI ATAS role verifikasi.",
                    member,
                )

    @commands.hybrid_command(
        name="verifikasi", description="Pasang panel verifikasi (tombol) di channel"
    )
    @commands.has_permissions(manage_guild=True)
    async def verifikasi(self, ctx: commands.Context):
        """Pasang panel verifikasi: !verifikasi / /verifikasi (khusus moderator)."""
        channel_id = config.settings.verify_channel_id
        channel = self.bot.get_channel(channel_id) if channel_id else None
        if channel is None:
            channel = ctx.channel  # fallback: pasang di channel ini
        nama_server = ctx.guild.name if ctx.guild else "server ini"
        try:
            await channel.send(
                embed=build_verify_panel(nama_server), view=VerifyButtonView()
            )
        except discord.Forbidden:
            await ctx.send(
                "❌ Bot tidak bisa kirim pesan ke channel itu (cek izin).",
                ephemeral=True,
            )
            return
        await ctx.send(
            f"✅ Panel verifikasi dipasang di {channel.mention}. "
            "Member baru tinggal klik tombolnya.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Verification(bot))
    # Daftarkan persistent view — WAJIB agar tombol tetap jalan setelah restart.
    bot.add_view(VerifyButtonView())
