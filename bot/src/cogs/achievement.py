"""Achievement — lihat lencana yang sudah dibuka member.

`/achievement [@user]` → embed daftar badge (inline kesamping).
Dibuka otomatis oleh sistem lain (invite, dsb) via `src/utils/achievement.py`.
"""
import discord
from discord.ext import commands

from src.store import get_connection
from src.utils import achievement as ach
from src.utils.embeds import base_embed


class Achievement(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(
        name="achievement", description="Lihat lencana achievement"
    )
    @discord.app_commands.describe(member="Member yang mau dilihat (opsional)")
    async def achievement(
        self, ctx: commands.Context, member: discord.Member | None = None
    ):
        """Lihat achievement: /achievement [@user]"""
        target = member or ctx.author
        gid = ctx.guild.id if ctx.guild else 0
        with get_connection() as conn:
            daftar = ach.daftar(conn, gid, target.id)
        if not daftar:
            await ctx.send(
                embed=base_embed(
                    "🏅 Achievement",
                    f"**{target.display_name}** belum membuka achievement apa pun.\n"
                    "Aktif di server untuk mulai mengoleksi!",
                ),
                ephemeral=True,
            )
            return
        embed = base_embed(
            f"🏅 Achievement — {target.display_name}",
            f"Total dibuka: **{len(daftar)}**",
        )
        for _kode, nama, _tgl in daftar:
            embed.add_field(name=nama, value="✅", inline=True)
        # Hidden achievement yang belum dibuka tampil sebagai ???
        with get_connection() as conn:
            terkunci = ach.hidden_terkunci(conn, gid, target.id)
        for _kode in terkunci:
            embed.add_field(name="???", value="🔒", inline=True)
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Achievement(bot))
