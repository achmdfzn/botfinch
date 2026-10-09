"""Ulang tahun — `/ultah DD-MM` simpan tanggal lahir.

Loop harian (UTC): yang ultah hari ini & belum dirayakan tahun ini →
umumkan di system channel + bonus koin (`ULTAH_KOIN`).
"""
import datetime
import logging
import re

import discord
from discord.ext import commands, tasks

from src import config
from src.store import get_connection
from src.utils import economy as eko
from src.utils.embeds import base_embed

log = logging.getLogger("finch")

# hari maksimal per bulan (Feb boleh 29)
_MAX_HARI = [0, 31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def parse_tanggal_ultah(teks: str) -> str | None:
    """'25-12' -> '25-12' (normalisasi 2 digit) kalau tanggal valid, else None.

    Pure function — gampang dites.
    """
    m = re.fullmatch(r"\s*(\d{1,2})-(\d{1,2})\s*", teks or "")
    if not m:
        return None
    hari, bulan = int(m.group(1)), int(m.group(2))
    if not 1 <= bulan <= 12:
        return None
    if not 1 <= hari <= _MAX_HARI[bulan]:
        return None
    return f"{hari:02d}-{bulan:02d}"


class Birthday(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cek_ultah.start()

    def cog_unload(self):
        self.cek_ultah.cancel()

    @commands.hybrid_command(
        name="ultah", description="Simpan tanggal lahirmu (format DD-MM)"
    )
    @discord.app_commands.describe(tanggal="Contoh: 25-12")
    async def ultah(self, ctx: commands.Context, tanggal: str):
        """Simpan ultah: /ultah 25-12"""
        if ctx.guild is None:
            await ctx.send("❌ Hanya bisa di server.", ephemeral=True)
            return
        tgl = parse_tanggal_ultah(tanggal)
        if tgl is None:
            await ctx.send(
                "❌ Format salah. Pakai `DD-MM`, contoh: `/ultah 25-12`.",
                ephemeral=True,
            )
            return
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO birthday (user_id, guild_id, tgl) VALUES (?, ?, ?) "
                "ON CONFLICT(user_id, guild_id) DO UPDATE SET tgl = excluded.tgl",
                (ctx.author.id, ctx.guild.id, tgl),
            )
            conn.commit()
        await ctx.send(
            f"🎂 Tanggal lahirmu dicatat: **{tgl}**. Nanti bot yang rayakan! 🎉",
            ephemeral=True,
        )

    @tasks.loop(hours=24)
    async def cek_ultah(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        hari_ini = now.strftime("%d-%m")
        tahun = now.strftime("%Y")
        try:
            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT user_id, guild_id, tahun_terakhir FROM birthday WHERE tgl = ?",
                    (hari_ini,),
                ).fetchall()
        except Exception:
            # Satu DB error tidak boleh membunuh loop harian selamanya
            log.exception("Gagal baca birthday")
            return
        for user_id, guild_id, tahun_terakhir in rows:
            if tahun_terakhir == tahun:
                continue
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                continue
            koin = config.settings.ultah_koin
            try:
                # Tandai dulu, baru kredit — crash di tengah = user kehilangan
                # koin (aman), bukan dapat 2x
                with get_connection() as conn:
                    conn.execute(
                        "UPDATE birthday SET tahun_terakhir = ? "
                        "WHERE user_id = ? AND guild_id = ?",
                        (tahun, user_id, guild_id),
                    )
                    conn.commit()
                if koin > 0:
                    with get_connection() as conn:
                        eko.tambah_koin(conn, guild_id, user_id, koin)
            except Exception:
                log.exception("Gagal proses ultah %s", user_id)
                continue
            channel = guild.system_channel
            if channel is None:
                continue
            embed = base_embed(
                "🎂 Selamat Ulang Tahun!",
                f"🎉 <@{user_id}> hari ini berulang tahun!\n"
                + (
                    f"Kado: **{koin}** 🪙 koin!"
                    if koin > 0
                    else "Semoga panjang umur & sehat selalu!"
                ),
            )
            try:
                await channel.send(embed=embed)
            except discord.HTTPException:
                log.warning("Gagal kirim pengumuman ultah di %s", guild_id)

    @cek_ultah.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Birthday(bot))
