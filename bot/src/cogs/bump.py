"""Bump reminder — ingatkan kapan bisa bump lagi (DISBOARD).

- `/bump` → kalau bump terakhir < 2 jam: "bisa bump lagi <t:ts:R>",
  kalau tidak: "silakan bump sekarang!"
- Otomatis catat saat bot DISBOARD (302050872383242240) mengirim
  embed berisi "bump done".
"""
import datetime
import logging
import re

import discord
from discord.ext import commands

from src import config
from src.store import get_connection
from src.utils import economy as eko

log = logging.getLogger("finch")

DISBOARD_ID = 302050872383242240
BUMP_COOLDOWN_DETIK = 2 * 3600


def ekstrak_bumper_id(deskripsi_list: list[str | None]) -> int | None:
    """Ambil user id pembump dari mention di deskripsi embed DISBOARD.

    Pure function — gampang dites.
    """
    for deskripsi in deskripsi_list:
        if not deskripsi:
            continue
        m = re.search(r"<@!?(\d+)>", deskripsi)
        if m:
            uid = int(m.group(1))
            if uid != DISBOARD_ID:
                return uid
    return None


def bump_sisa_detik(terakhir_iso: str | None, now: datetime.datetime) -> int:
    """Sisa detik sampai boleh bump lagi (0 = boleh sekarang).

    Pure function — gampang dites.
    """
    if not terakhir_iso:
        return 0
    try:
        terakhir = datetime.datetime.fromisoformat(terakhir_iso)
    except ValueError:
        return 0
    if terakhir.tzinfo is None:
        terakhir = terakhir.replace(tzinfo=datetime.timezone.utc)
    sisa = BUMP_COOLDOWN_DETIK - int((now - terakhir).total_seconds())
    return max(0, sisa)


class Bump(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(
        name="bump", description="Cek kapan bisa bump server lagi"
    )
    async def bump(self, ctx: commands.Context):
        """Cek bump: /bump"""
        if ctx.guild is None:
            await ctx.send("❌ Hanya bisa di server.", ephemeral=True)
            return
        now = datetime.datetime.now(datetime.timezone.utc)
        with get_connection() as conn:
            row = conn.execute(
                "SELECT terakhir FROM bump WHERE guild_id = ?", (ctx.guild.id,)
            ).fetchone()
        sisa = bump_sisa_detik(row[0] if row else None, now)
        if sisa > 0:
            ts = int((now + datetime.timedelta(seconds=sisa)).timestamp())
            await ctx.send(
                f"⏳ Bump terakhir tercatat. Bisa bump lagi <t:{ts}:R>.",
                ephemeral=True,
            )
        else:
            await ctx.send(
                "🚀 Silakan bump sekarang! (pakai `/bump` di bot DISBOARD)",
                ephemeral=True,
            )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.id != DISBOARD_ID or not message.guild:
            return
        bump_done = any(
            e.description and "bump done" in e.description.lower()
            for e in message.embeds
        )
        if not bump_done:
            return
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        try:
            with get_connection() as conn:
                conn.execute(
                    "INSERT INTO bump (guild_id, terakhir) VALUES (?, ?) "
                    "ON CONFLICT(guild_id) DO UPDATE SET terakhir = excluded.terakhir",
                    (message.guild.id, now_iso),
                )
                conn.commit()
        except Exception:
            log.exception("Gagal catat bump")
            return
        log.info("Bump tercatat di guild %s", message.guild.id)
        # Tahap 12: reward koin untuk yang bump (best effort, tanpa ubah deteksi)
        try:
            bumper_id = ekstrak_bumper_id([e.description for e in message.embeds])
            koin = config.settings.bump_koin
            if bumper_id and koin > 0:
                with get_connection() as conn:
                    eko.tambah_koin(conn, message.guild.id, bumper_id, koin)
                log.info(
                    "Bump koin +%d untuk user %s (guild %s)",
                    koin, bumper_id, message.guild.id,
                )
        except Exception:
            log.exception("Gagal kasih koin bump")


async def setup(bot: commands.Bot):
    await bot.add_cog(Bump(bot))
