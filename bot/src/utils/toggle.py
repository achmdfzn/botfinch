"""Helper bersama untuk `cog_check` toggle modul per-server via dashboard.

Delapan cog memakai pola identik: izinkan command bila di DM atau toggle
`*_enabled` menyala; bila modul dimatikan, kirim pesan penjelasan sekali
lalu return False. Sebelumnya blok ~18 baris ini diduplikasi di
economy.py, ekonomi_plus.py, minigames.py, quests.py, season.py, shop.py,
giveaway.py, dan leveling.py.
"""

import discord
from discord.ext import commands


async def cek_toggle(ctx: commands.Context, key: str, pesan: str) -> bool:
    """Return True bila command boleh jalan (DM atau modul `key` aktif).

    Bila modul dimatikan via dashboard, kirim `pesan` ke pemanggil
    (mendukung prefix command maupun slash) lalu return False.
    """
    if ctx.guild is None:
        return True
    # Import malas: modul cogs.dashboard_sync memuat banyak hal;
    # pola yang sama dipakai di semua cog_check sebelumnya.
    from src.cogs.dashboard_sync import modul_aktif

    if modul_aktif(ctx.guild.id, key):
        return True
    try:
        if ctx.interaction is None:
            await ctx.send(pesan)
        elif ctx.interaction.response.is_done():
            await ctx.interaction.followup.send(pesan, ephemeral=True)
        else:
            await ctx.interaction.response.send_message(pesan, ephemeral=True)
    except discord.HTTPException:
        pass
    return False
