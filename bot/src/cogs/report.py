"""Context menu: klik kanan pesan -> Apps -> Laporkan ke Mod.

- Cari tiket terbuka pelapor; kalau belum ada buat baru (reuse tickets.buat_tiket).
- Kirim embed laporan ke channel tiket.
- Balas ephemeral ke pelapor.
"""
import discord
from discord import app_commands
from discord.ext import commands

from src.store import get_connection
from src.cogs.tickets import buat_tiket
from src.utils.embeds import base_embed


def _get_or_create_tiket(guild, member):
    """Helper sync: cek DB tiket terbuka, return channel_id atau None."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT channel_id FROM tickets WHERE guild_id = ? AND owner_id = ? AND closed = 0",
            (guild.id, member.id),
        ).fetchone()
    if row:
        return row[0]
    return None


class Report(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.ctx_menu = app_commands.ContextMenu(
            name="Laporkan ke Mod",
            callback=self.laporkan,
        )
        self.bot.tree.add_command(self.ctx_menu)

    async def cog_unload(self) -> None:
        try:
            self.bot.tree.remove_command(self.ctx_menu.name, type=self.ctx_menu.type)
        except Exception:
            pass

    async def laporkan(self, interaction: discord.Interaction, message: discord.Message):
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "❌ Fitur ini hanya bisa dipakai di server.", ephemeral=True
            )
            return

        guild = interaction.guild
        member = interaction.user

        # Cari tiket terbuka atau buat baru
        channel_id = _get_or_create_tiket(guild, member)
        channel = None
        if channel_id:
            channel = guild.get_channel(channel_id)
        if channel is None or not isinstance(channel, discord.TextChannel):
            try:
                channel = await buat_tiket(self.bot, guild, member, laporan=message)
            except discord.Forbidden:
                await interaction.response.send_message(
                    "❌ Bot butuh izin Manage Channels untuk membuat tiket.", ephemeral=True
                )
                return
            except discord.HTTPException as e:
                await interaction.response.send_message(
                    f"❌ Gagal membuat tiket: {e}", ephemeral=True
                )
                return

        # Build embed laporan
        isi = message.content or "(tidak ada teks — mungkin embed/lampiran)"
        if len(isi) > 1000:
            isi = isi[:997] + "..."

        embed = base_embed("🚨 Laporan Baru", isi)
        embed.color = discord.Color.red()
        embed.add_field(name="Pengirim pesan", value=f"{message.author.mention} (`{message.author}`)", inline=False)
        embed.add_field(name="Channel asal", value=f"{message.channel.mention if hasattr(message.channel, 'mention') else message.channel}", inline=True)
        embed.add_field(name="Pelapor", value=member.mention, inline=True)
        embed.add_field(name="Jump link", value=f"[Klik untuk lihat pesan]({message.jump_url})", inline=False)
        if message.attachments:
            embed.add_field(name="Lampiran", value=f"{len(message.attachments)} file", inline=False)

        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            await interaction.response.send_message(
                "❌ Gagal mengirim laporan ke tiket.", ephemeral=True
            )
            return

        # Balas ephemeral ke pelapor
        if interaction.response.is_done():
            await interaction.followup.send(f"✅ Laporan dikirim ke {channel.mention}.", ephemeral=True)
        else:
            await interaction.response.send_message(f"✅ Laporan dikirim ke {channel.mention}.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Report(bot))
