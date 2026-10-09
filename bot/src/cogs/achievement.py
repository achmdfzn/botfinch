"""Achievement — lihat lencana yang sudah dibuka member.

`/achievement [@user]` → embed daftar badge (inline kesamping).
Dibuka otomatis oleh sistem lain (invite, dsb) via `src/utils/achievement.py`.
"""
import discord
from discord.ext import commands

from src.store import get_connection
from src.utils import achievement as ach
from src.utils.embeds import base_embed


def field_achievement(
    daftar: list[tuple[str, str, str]], terkunci: list[str]
) -> list[tuple[str, str]]:
    """[(nama_field, nilai)] untuk embed /achievement, maks 25 field.

    Pure — gampang dites. Batas field Discord 25: cap defensif agar daftar
    achievement yang tumbuh di masa depan tidak memicu API 400.
    """
    field_dibuka = [(nama, "✅") for _kode, nama, _tgl in daftar[:20]]
    if len(daftar) > 20:
        field_dibuka.append((f"+{len(daftar) - 20} lainnya", "🏅"))
    sisa = max(0, 25 - len(field_dibuka))
    field_kunci = [("???", "🔒") for _kode in terkunci[:sisa]]
    return (field_dibuka + field_kunci)[:25]


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
        # Hidden achievement yang belum dibuka tampil sebagai ???
        with get_connection() as conn:
            terkunci = ach.hidden_terkunci(conn, gid, target.id)
        for nama, nilai in field_achievement(daftar, terkunci):
            embed.add_field(name=nama, value=nilai, inline=True)
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Achievement(bot))
