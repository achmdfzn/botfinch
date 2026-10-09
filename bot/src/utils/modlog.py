"""Catat kejadian penting ke channel mod-log (kalau dikonfigurasi).

Pakai helper ini dari cog mana pun — jangan kirim ke channel log secara manual.
"""
import logging

import discord
from discord.ext import commands

from src import config

log = logging.getLogger("finch")

# Kebijakan mention eksplisit untuk mod-log (cermin src.bot.MENTIONS_AMAN):
# konten user yang di-log (isi pesan yang diedit/dihapus, transkrip, dsb.)
# TIDAK BOLEH memicu mass-ping @everyone/@here. Didefinisikan di sini (bukan
# import dari src.bot) karena src/bot.py mengimpor modul ini di level modul —
# import balik akan circular. Kalau MENTIONS_AMAN di src/bot.py berubah,
# samakan juga konstanta ini.
MENTIONS_LOG_AMAN = discord.AllowedMentions(
    everyone=False, users=True, roles=True, replied_user=True
)


async def log_event(
    bot: commands.Bot,
    title: str,
    description: str,
    color: discord.Color = discord.Color.blurple(),
    file: discord.File | None = None,
    channel_id: int | None = None,
) -> None:
    """Kirim satu embed ke channel mod-log. Diam-diam skip kalau belum di-set.

    `file` opsional — mis. transcript tiket (.txt).
    `channel_id` opsional — override per-guild (mis. dari dashboard); kalau None
    pakai MOD_LOG_CHANNEL_ID global.
    """
    channel_id = channel_id or config.settings.mod_log_channel_id
    if not channel_id:
        return
    channel = bot.get_channel(channel_id)
    if channel is None:
        log.warning("MOD_LOG_CHANNEL_ID %s tidak ketemu.", channel_id)
        return
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=discord.utils.utcnow(),
    )
    try:
        await channel.send(
            embed=embed, file=file, allowed_mentions=MENTIONS_LOG_AMAN
        )
    except (discord.Forbidden, discord.HTTPException):
        log.warning("Tidak bisa kirim ke mod-log (cek permission/ID channel).")
