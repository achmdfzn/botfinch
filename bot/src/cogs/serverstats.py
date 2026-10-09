"""Server stats — voice channel yang namanya update otomatis.

Buat 3 voice channel (atau pakai yang ada), isi ID-nya di .env:
  STATS_TOTAL_ID=...  → "👥 Semua: 123"
  STATS_HUMAN_ID=...  → "🧑 Manusia: 120"
  STATS_BOT_ID=...    → "🤖 Bot: 3"

Di-update tiap 10 menit + setiap ada member join/keluar.
Pakai voice channel (namanya boleh ada spasi & emoji) — jangan text channel.
"""
import logging

import discord
from discord.ext import commands, tasks

from src import config

log = logging.getLogger("finch")


def nama_stat(prefix: str, jumlah: int) -> str:
    """Format nama channel statistik. Pure function — gampang dites."""
    return f"{prefix}: {jumlah}"


class ServerStats(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.update_stats.start()

    def cog_unload(self):
        self.update_stats.cancel()

    @tasks.loop(minutes=10)
    async def update_stats(self):
        for guild in self.bot.guilds:
            try:
                await self._update_guild(guild)
            except Exception:  # satu guild error tidak boleh membunuh loop
                log.exception("update_stats gagal untuk guild %s", guild.id)

    @update_stats.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        await self._update_guild(member.guild)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        await self._update_guild(member.guild)

    async def _update_guild(self, guild: discord.Guild) -> None:
        s = config.settings
        if not (s.stats_total_id or s.stats_human_id or s.stats_bot_id):
            return
        total = guild.member_count or 0
        bots = sum(1 for m in guild.members if m.bot)
        humans = max(0, total - bots)
        target = {
            s.stats_total_id: nama_stat("👥 Semua", total),
            s.stats_human_id: nama_stat("🧑 Manusia", humans),
            s.stats_bot_id: nama_stat("🤖 Bot", bots),
        }
        for ch_id, nama in target.items():
            if not ch_id:
                continue
            channel = guild.get_channel(ch_id)
            if channel is None:
                continue
            if channel.name == nama:
                continue
            try:
                await channel.edit(name=nama, reason="Update server stats")
            except (discord.Forbidden, discord.HTTPException):
                log.warning("Gagal rename channel stat %s (cek izin).", ch_id)


async def setup(bot: commands.Bot):
    await bot.add_cog(ServerStats(bot))
