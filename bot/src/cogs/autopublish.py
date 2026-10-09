"""Auto-publish pesan di channel pengumuman (announcement/news) ala Dyno.

Setiap pesan non-bot yang masuk ke channel news otomatis di-publish
(`message.publish()`) supaya muncul di server yang follow. Bisa dimatikan
per-server via dashboard dengan toggle `autopublish_enabled`.
"""
import logging

import discord
from discord.ext import commands

log = logging.getLogger("finch")


class AutoPublish(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        guild = message.guild
        if guild is None or message.author.bot:
            return
        # Import malas: pola yang sama dipakai listener lain di repo ini.
        from src.cogs.dashboard_sync import modul_aktif

        if not modul_aktif(guild.id, "autopublish_enabled"):
            return
        channel = message.channel
        if not isinstance(channel, discord.TextChannel) or not channel.is_news():
            return
        # Publish butuh izin Manage Messages di channel itu; lewati diam-diam
        # bila bot tidak punya (hindari panggilan API yang pasti gagal).
        me = guild.me
        if me is not None and not channel.permissions_for(me).manage_messages:
            return
        try:
            await message.publish()
        except (discord.Forbidden, discord.HTTPException) as e:
            log.debug("Auto-publish gagal di %s: %s", channel, e)


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoPublish(bot))
