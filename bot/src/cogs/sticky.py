"""Sticky message — pesan yang selalu nempel di bawah channel.

- `/sticky-set <teks>` (mod): pasang di channel ini
- `/sticky-hapus` (mod): cabut
Tiap ada pesan baru, sticky lama dihapus & dikirim ulang paling bawah.
"""
import asyncio
import logging

import discord
from discord.ext import commands

from src.bot import MENTIONS_PENGUMUMAN
from src.store import get_connection

log = logging.getLogger("finch")


class Sticky(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._lock: dict[int, asyncio.Lock] = {}

    def _kunci(self, channel_id: int) -> asyncio.Lock:
        lock = self._lock.get(channel_id)
        if lock is None:
            lock = asyncio.Lock()
            self._lock[channel_id] = lock
            if len(self._lock) > 200:  # evict tertua
                self._lock.pop(next(iter(self._lock)))
        return lock

    @commands.hybrid_command(
        name="sticky-set", description="Pasang sticky message di channel ini (mod)"
    )
    @commands.has_permissions(manage_messages=True)
    @discord.app_commands.describe(teks="Isi sticky message")
    async def sticky_set(self, ctx: commands.Context, *, teks: str):
        """Pasang sticky: /sticky-set <teks>"""
        if ctx.guild is None:
            await ctx.send("❌ Hanya bisa di server.", ephemeral=True)
            return
        teks = teks.strip()
        if not teks:
            await ctx.send("❌ Teks tidak boleh kosong.", ephemeral=True)
            return
        if len(teks) > 2000:
            await ctx.send("❌ Teks kepanjangan (maks 2000 karakter).", ephemeral=True)
            return
        with get_connection() as conn:
            row = conn.execute(
                "SELECT message_id FROM sticky WHERE channel_id = ?",
                (ctx.channel.id,),
            ).fetchone()
            if row and row[0]:
                try:
                    lama = await ctx.channel.fetch_message(row[0])
                    await lama.delete()
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    pass
        try:
            # Sticky ditulis mod -> boleh @everyone.
            msg = await ctx.channel.send(teks, allowed_mentions=MENTIONS_PENGUMUMAN)
        except discord.HTTPException:
            await ctx.send("❌ Gagal kirim sticky (cek permission).", ephemeral=True)
            return
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO sticky (channel_id, guild_id, teks, message_id) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(channel_id) DO UPDATE SET teks = excluded.teks, message_id = excluded.message_id",
                (ctx.channel.id, ctx.guild.id, teks, msg.id),
            )
            conn.commit()
        await ctx.send("📌 Sticky dipasang di channel ini.", ephemeral=True)

    @commands.hybrid_command(
        name="sticky-hapus", description="Cabut sticky message (mod)"
    )
    @commands.has_permissions(manage_messages=True)
    async def sticky_hapus(self, ctx: commands.Context):
        """Cabut sticky: /sticky-hapus"""
        if ctx.guild is None:
            await ctx.send("❌ Hanya bisa di server.", ephemeral=True)
            return
        with get_connection() as conn:
            row = conn.execute(
                "SELECT message_id FROM sticky WHERE channel_id = ?",
                (ctx.channel.id,),
            ).fetchone()
            if row is None:
                await ctx.send("❌ Tidak ada sticky di channel ini.", ephemeral=True)
                return
            if row[0]:
                try:
                    lama = await ctx.channel.fetch_message(row[0])
                    await lama.delete()
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    pass
            conn.execute("DELETE FROM sticky WHERE channel_id = ?", (ctx.channel.id,))
            conn.commit()
        await ctx.send("📌 Sticky dicabut.", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        with get_connection() as conn:
            row = conn.execute(
                "SELECT teks, message_id FROM sticky WHERE channel_id = ?",
                (message.channel.id,),
            ).fetchone()
        if row is None:
            return
        teks, msg_id = row
        if message.id == msg_id:
            return
        # Lock per-channel: 2 pesan berdekatan tidak boleh repost sticky 2x
        async with self._kunci(message.channel.id):
            # Baca ulang — pesan lain mungkin sudah merepost duluan
            with get_connection() as conn:
                row2 = conn.execute(
                    "SELECT teks, message_id FROM sticky WHERE channel_id = ?",
                    (message.channel.id,),
                ).fetchone()
            if row2 is None:
                return
            teks, msg_id = row2
            if msg_id:
                try:
                    lama = await message.channel.fetch_message(msg_id)
                    await lama.delete()
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    pass
            try:
                # Sticky ditulis mod -> boleh @everyone.
                baru = await message.channel.send(teks, allowed_mentions=MENTIONS_PENGUMUMAN)
            except discord.HTTPException:
                log.warning("Gagal kirim ulang sticky di %s", message.channel.id)
                return
            with get_connection() as conn:
                conn.execute(
                    "UPDATE sticky SET message_id = ? WHERE channel_id = ?",
                    (baru.id, message.channel.id),
                )
                conn.commit()


async def setup(bot: commands.Bot):
    await bot.add_cog(Sticky(bot))
