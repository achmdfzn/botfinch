"""Quest harian — misi reset tiap hari, hadiah koin.

- `/quest` — lihat progres hari ini (3 kolom kesamping + progress bar)
- Tombol "Klaim" muncul kalau ada quest selesai yang belum diklaim.
Progres diisi otomatis: pesan (leveling), voice (voicexp), /daily (economy).
"""
import discord
from discord.ext import commands

from src.store import get_connection
from src.utils import economy as eko
from src.utils import quests as q
from src.utils.toggle import cek_toggle
from src.utils.embeds import base_embed, get_progress_bar
from src.utils.views import TimeoutSafeView, bind_view_message


class KlaimView(TimeoutSafeView):
    def __init__(self, author_id: int):
        super().__init__(timeout=60)
        self.author_id = author_id
        self.selesai = False

    @discord.ui.button(label="Klaim Hadiah", style=discord.ButtonStyle.success)
    async def klaim(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "❌ Ini quest orang lain.", ephemeral=True
            )
            return
        if self.selesai:
            return
        self.selesai = True  # kunci dulu (anti double-click)
        gid = interaction.guild.id if interaction.guild else 0
        from src.cogs.dashboard_sync import modul_aktif

        if interaction.guild and not modul_aktif(gid, "economy_enabled"):
            await interaction.response.send_message(
                "Modul ekonomi dimatikan oleh admin server ini.", ephemeral=True
            )
            return
        with get_connection() as conn:
            total, nama_quest = q.klaim_quest(conn, gid, self.author_id)
            if total > 0:
                eko.tambah_koin(conn, gid, self.author_id, total)
        button.disabled = True
        if total > 0:
            teks = f"🎉 +**{total}** 🪙 dari: {', '.join(nama_quest)}!"
        else:
            teks = "😅 Belum ada quest selesai yang bisa diklaim."
        try:
            await interaction.response.edit_message(content=teks, view=self)
        except discord.HTTPException:
            pass
        self.stop()


class Quests(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_check(self, ctx: commands.Context) -> bool:
        """Quest berhadiah koin — bagian modul Ekonomi, ikut `economy_enabled`."""
        return await cek_toggle(
            ctx, "economy_enabled", "Modul ekonomi dimatikan oleh admin server ini."
        )

    @commands.hybrid_command(name="quest", description="Lihat quest harianmu")
    async def quest(self, ctx: commands.Context):
        """Quest harian: /quest"""
        gid = ctx.guild.id if ctx.guild else 0
        with get_connection() as conn:
            status = q.status_quest(conn, gid, ctx.author.id)
        embed = base_embed("🗺️ Quest Harian", "*Reset tiap hari (UTC). Selesaikan & klaim!*")
        ada_diklaim = False
        # UI horizontal: 3 quest kesamping
        for s in status:
            bar = get_progress_bar(s["progress"], s["target"])
            if s["diklaim"]:
                ket = "✅ Diklaim"
            elif s["selesai"]:
                ket = "🎁 Siap diklaim!"
                ada_diklaim = True
            else:
                ket = f"{bar} `{s['progress']}/{s['target']}` {s['satuan']}"
            embed.add_field(
                name=f"{s['nama']}",
                value=f"{ket}\nHadiah: **{s['hadiah']}** 🪙",
                inline=True,
            )
        view = KlaimView(ctx.author.id) if ada_diklaim else None
        msg = await ctx.send(embed=embed, view=view)
        if view:
            await bind_view_message(ctx, view, msg)


async def setup(bot: commands.Bot):
    await bot.add_cog(Quests(bot))
