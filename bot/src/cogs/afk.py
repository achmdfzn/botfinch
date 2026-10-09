"""AFK — tandai diri sedang pergi.

`/afk [alasan]` → status tersimpan di DB.
- Kirim pesan apa pun → AFK otomatis mati ("selamat datang kembali").
- Orang yang mention kamu → bot membalas status AFK-mu.
"""
import datetime
import discord
from discord.ext import commands

from src import config
from src.store import get_connection

def format_balas_afk(nama: str, alasan: str | None, since_iso: str) -> str:
    """Teks balasan saat user AFK di-mention. Pure function — gampang dites."""
    try:
        ts = int(datetime.datetime.fromisoformat(since_iso).timestamp())
        kapan = f"<t:{ts}:R>"
    except ValueError:
        kapan = "tadi"
    teks = f"💤 **{nama}** sedang AFK ({kapan})"
    if alasan:
        teks += f": {alasan}"
    return teks


class Afk(commands.Cog):
    def __init__(self, bot: commands.Bot):
        pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        gid = message.guild.id

        # 1. pengirim yang sedang AFK → matikan AFK-nya (kecuali lagi update via !afk)
        lagi_update_afk = message.content.strip().lower().startswith(
            f"{config.settings.prefix}afk"
        )
        if not lagi_update_afk:
            with get_connection() as conn:
                ada = conn.execute(
                    "SELECT 1 FROM afk WHERE user_id = ? AND guild_id = ?",
                    (message.author.id, gid),
                ).fetchone()
                if ada:
                    conn.execute(
                        "DELETE FROM afk WHERE user_id = ? AND guild_id = ?",
                        (message.author.id, gid),
                    )
                    conn.commit()
                    try:
                        await message.channel.send(
                            f"👋 Selamat datang kembali, {message.author.mention}!",
                            delete_after=10,
                        )
                    except discord.Forbidden:
                        pass

        # 2. mention ke user AFK → balas statusnya (satu balasan biar tidak spam)
        for member in message.mentions:
            if member.id == message.author.id or member.bot:
                continue
            with get_connection() as conn:
                row = conn.execute(
                    "SELECT reason, since FROM afk WHERE user_id = ? AND guild_id = ?",
                    (member.id, gid),
                ).fetchone()
            if row:
                try:
                    await message.channel.send(
                        format_balas_afk(member.display_name, row[0], row[1]),
                        delete_after=15,
                    )
                except discord.Forbidden:
                    pass
                break

    @commands.hybrid_command(name="afk", description="Tandai diri sedang AFK")
    @discord.app_commands.describe(alasan="Opsional: kenapa AFK (maks 100 karakter)")
    async def afk(self, ctx: commands.Context, *, alasan: str | None = None):
        """Tandai AFK: !afk makan dulu / /afk [alasan]"""
        if ctx.guild is None:
            await ctx.send("❌ Hanya bisa di server.", ephemeral=True)
            return
        if alasan and len(alasan) > 100:
            alasan = alasan[:100]
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO afk (user_id, guild_id, reason, since) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(user_id, guild_id) DO UPDATE SET "
                "reason=excluded.reason, since=excluded.since",
                (
                    ctx.author.id,
                    ctx.guild.id,
                    alasan,
                    discord.utils.utcnow().isoformat(),
                ),
            )
            conn.commit()
        await ctx.send(
            f"💤 {ctx.author.mention} sekarang AFK"
            + (f": {alasan}" if alasan else ".")
            + " Kirim pesan apa pun untuk kembali.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Afk(bot))
