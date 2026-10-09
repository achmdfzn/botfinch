"""Profil member — gabungan level, koin, rep, prestise, achievement.

`/profil [@user]` → embed horizontal (field kesamping) + thumbnail avatar.
"""
import discord
from discord.ext import commands

from src.store import get_connection
from src.utils import achievement as ach
from src.utils.embeds import base_embed


class Profil(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="profil", description="Lihat profil member")
    @discord.app_commands.describe(member="Member yang mau dilihat (opsional)")
    async def profil(
        self, ctx: commands.Context, member: discord.Member | None = None
    ):
        """Lihat profil: /profil [@user]"""
        target = member or ctx.author
        gid = ctx.guild.id if ctx.guild else 0
        with get_connection() as conn:
            row = conn.execute(
                "SELECT level, COALESCE(prestige, 0) FROM users WHERE user_id = ? AND guild_id = ?",
                (target.id, gid),
            ).fetchone()
            level, prestige = (row[0], row[1]) if row else (1, 0)
            row2 = conn.execute(
                "SELECT balance, COALESCE(rep, 0) FROM economy WHERE user_id = ? AND guild_id = ?",
                (target.id, gid),
            ).fetchone()
            balance, rep = (row2[0], row2[1]) if row2 else (0, 0)
            badges = ach.daftar(conn, gid, target.id)
        embed = base_embed(f"👤 Profil — {target.display_name}")
        # UI horizontal: stat kesamping
        embed.add_field(name="Level", value=f"**{level}**", inline=True)
        embed.add_field(name="Koin", value=f"**{balance}**", inline=True)
        embed.add_field(name="Rep", value=f"**{rep}**", inline=True)
        embed.add_field(
            name="Prestise", value=f"**{prestige}**" if prestige else "-", inline=True
        )
        # Info sosial Tahap 12: job, pasangan, clan, gelar (horizontal)
        from src.utils import job as jobmod
        from src.cogs.sosial import gelar_nama

        with get_connection() as conn:
            job_id = jobmod.get_job(conn, gid, target.id)
            pas = conn.execute(
                "SELECT pasangan_id FROM nikah WHERE user_id = ? AND guild_id = ?",
                (target.id, gid),
            ).fetchone()
            clan = conn.execute(
                "SELECT c.nama FROM clan c JOIN clan_member m ON m.clan_id = c.id "
                "WHERE m.user_id = ? AND c.guild_id = ?",
                (target.id, gid),
            ).fetchone()
            gelar = gelar_nama(conn, gid, target.id)
        job_txt = jobmod.JOBS[job_id]["nama"] if job_id else "-"
        embed.add_field(name="Job", value=job_txt, inline=True)
        embed.add_field(
            name="Pasangan", value=f"<@{pas[0]}>" if pas else "-", inline=True
        )
        embed.add_field(name="Clan", value=f"**{clan[0]}**" if clan else "-", inline=True)
        embed.add_field(name="Gelar", value=gelar or "-", inline=True)
        if badges:
            nama_badge = [nama for _k, nama, _t in badges[:5]]
            teks = "\n".join(f"🏅 {n}" for n in nama_badge)
            if len(badges) > 5:
                teks += f"\n*+{len(badges) - 5} lagi — lihat `/achievement`*"
            embed.add_field(name=f"Achievement ({len(badges)})", value=teks, inline=False)
        else:
            embed.add_field(
                name="Achievement", value="Belum ada — aktif di server yuk!", inline=False
            )
        try:
            embed.set_thumbnail(url=target.display_avatar.url)
        except Exception:
            pass
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Profil(bot))
