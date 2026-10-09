"""Papan peringkat member berdasarkan Level/XP — paginated (tabel)."""
import discord
from discord.ext import commands

from src.store import get_connection
from src.utils.embeds import base_embed, tabel
from src.utils.views import TimeoutSafeView, bind_view_message

PER_PAGE = 10


def _nama(bot: commands.Bot, guild: discord.Guild | None, user_id: int) -> str:
    member = guild.get_member(user_id) if guild else None
    user = member or bot.get_user(user_id)
    return (user.display_name if user else f"ID {user_id}")[:18]


def _leaderboard_embed(bot: commands.Bot, guild: discord.Guild, rows: list, page: int, total_pages: int) -> discord.Embed:
    embed = base_embed(f"Papan Peringkat — Halaman {page + 1}/{total_pages}")
    if guild and guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    start_rank = page * PER_PAGE + 1
    baris = [
        [str(start_rank + i), _nama(bot, guild, uid), f"Lv.{lv}", f"{xp} XP"]
        for i, (uid, lv, xp) in enumerate(rows)
    ]
    embed.description = tabel(["#", "Member", "Level", "XP"], baris) if baris else "Belum ada data di halaman ini."
    embed.set_footer(text=f"Finch • Halaman {page + 1}/{total_pages}")
    return embed


class LeaderboardView(TimeoutSafeView):
    def __init__(self, bot: commands.Bot, guild: discord.Guild, all_rows: list):
        super().__init__(timeout=60)
        self.bot = bot
        self.guild = guild
        self.all_rows = all_rows
        self.page = 0
        self.total_pages = max(1, (len(all_rows) + PER_PAGE - 1) // PER_PAGE)
        self._refresh_buttons()

    def _page_rows(self):
        start = self.page * PER_PAGE
        return self.all_rows[start : start + PER_PAGE]

    def _refresh_buttons(self):
        self.prev_btn.disabled = self.page <= 0
        self.next_btn.disabled = self.page >= self.total_pages - 1

    def current_embed(self):
        return _leaderboard_embed(self.bot, self.guild, self._page_rows(), self.page, self.total_pages)

    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = max(0, self.page - 1)
        self._refresh_buttons()
        await interaction.response.edit_message(embed=self.current_embed(), view=self)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = min(self.total_pages - 1, self.page + 1)
        self._refresh_buttons()
        await interaction.response.edit_message(embed=self.current_embed(), view=self)

class Leaderboard(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="leaderboard", description="Tampilkan ranking member teratas")
    async def leaderboard(self, ctx: commands.Context):
        """Tampilkan leaderboard: !leaderboard / /leaderboard"""
        gid = ctx.guild.id if ctx.guild else 0
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT user_id, level, xp FROM users WHERE guild_id = ? ORDER BY level DESC, xp DESC",
                (gid,),
            )
            rows = cursor.fetchall()

        if not rows:
            await ctx.send(embed=base_embed("📊 Leaderboard Kosong", "Belum ada member yang punya XP. Chat dulu yuk! 🎮"))
            return

        view = LeaderboardView(self.bot, ctx.guild, rows)
        sent = await ctx.send(embed=view.current_embed(), view=view)
        await bind_view_message(ctx, view, sent)


async def setup(bot: commands.Bot):
    await bot.add_cog(Leaderboard(bot))