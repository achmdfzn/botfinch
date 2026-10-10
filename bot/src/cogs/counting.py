"""Counting channel — member berhitung berurutan.

Config `.env`: COUNTING_CHANNEL_ID=<id channel>.
Aturan: angka berikutnya = terakhir + 1, tidak boleh 2x beruntun oleh orang sama.
Pesan salah otomatis dihapus. Tiap kelipatan 100 ada perayaan 🎉.
Mod: `/counting-reset` untuk ulang dari 0.
"""

import discord
from discord.ext import commands

from src import config
from src.store import get_connection



def _state(conn, guild_id: int, channel_id: int) -> tuple[int, int | None]:
    row = conn.execute(
        "SELECT angka, user_terakhir FROM counting_state WHERE guild_id = ? AND channel_id = ?",
        (guild_id, channel_id),
    ).fetchone()
    if row:
        return row[0], row[1]
    conn.execute(
        "INSERT INTO counting_state (guild_id, channel_id, angka) VALUES (?, ?, 0)",
        (guild_id, channel_id),
    )
    conn.commit()
    return 0, None


def cek_hitungan(isi: str, angka_terakhir: int, user_terakhir: int | None, user_id: int) -> tuple[bool, str]:
    """Validasi pesan counting. Return (valid, pesan_error). Pure function."""
    teks = isi.strip()
    if not teks.isdigit():
        return False, "bukan angka"
    if int(teks) != angka_terakhir + 1:
        return False, f"harusnya {angka_terakhir + 1}"
    if user_terakhir == user_id:
        return False, "tidak boleh 2x beruntun"
    return True, ""


class Counting(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        # Channel counting bisa diatur per-server via dashboard
        # (counting_channel_id); fallback ke COUNTING_CHANNEL_ID global.
        from src.cogs.dashboard_sync import channel_setting

        channel_id = channel_setting(
            message.guild.id, "counting_channel_id", config.settings.counting_channel_id
        )
        if not channel_id or message.channel.id != channel_id:
            return
        gid = message.guild.id
        with get_connection() as conn:
            angka, user_terakhir = _state(conn, gid, channel_id)
            valid, err = cek_hitungan(message.content, angka, user_terakhir, message.author.id)
            if valid:
                # Klaim atomik: hanya satu yang menang bila dua pesan benar
                # masuk bersamaan (dulu: baca lalu UPDATE — angka bisa
                # diklaim ganda & state macet).
                cur = conn.execute(
                    "UPDATE counting_state SET angka = ?, user_terakhir = ?"
                    " WHERE guild_id = ? AND channel_id = ? AND angka = ?",
                    (angka + 1, message.author.id, gid, channel_id, angka),
                )
                conn.commit()
                if cur.rowcount == 0:
                    # Kalah race: orang lain sudah mengklaim angka ini duluan.
                    # Jangan hapus pesan (sudah benar saat dikirim), cukup lewati.
                    return
            berikutnya = angka + 1
        if not valid:
            try:
                await message.delete()
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                pass
            try:
                await message.channel.send(
                    f"❌ {message.author.mention} salah ({err})! Angka berikutnya: **{berikutnya}**",
                    delete_after=5,
                )
            except discord.HTTPException:
                pass
            return
        if berikutnya % 100 == 0:
            try:
                await message.channel.send(
                    f"🎉 **{berikutnya}**! Kompak banget! Lanjut! 🚀"
                )
            except discord.HTTPException:
                pass

    @commands.hybrid_command(name="counting-reset", description="Reset counting ke 0 (khusus mod)")
    async def counting_reset(self, ctx: commands.Context):
        """Reset counting: /counting-reset"""
        if ctx.guild is None:
            await ctx.send("❌ Hanya bisa di server.", ephemeral=True)
            return
        if not (isinstance(ctx.author, discord.Member) and ctx.author.guild_permissions.manage_messages):
            await ctx.send("❌ Khusus moderator.", ephemeral=True)
            return
        from src.cogs.dashboard_sync import channel_setting

        channel_id = channel_setting(
            ctx.guild.id, "counting_channel_id", config.settings.counting_channel_id
        )
        if not channel_id:
            await ctx.send("❌ Channel counting belum dikonfigurasi admin.", ephemeral=True)
            return
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO counting_state (guild_id, channel_id, angka, user_terakhir)"
                " VALUES (?, ?, 0, NULL)"
                " ON CONFLICT(guild_id, channel_id) DO UPDATE SET angka = 0, user_terakhir = NULL",
                (ctx.guild.id, channel_id),
            )
            conn.commit()
        await ctx.send("🔄 Counting di-reset ke 0. Mulai lagi dari **1**!")


async def setup(bot: commands.Bot):
    await bot.add_cog(Counting(bot))
