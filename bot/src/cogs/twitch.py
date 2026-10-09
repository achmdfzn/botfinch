"""Notifikasi Twitch live — pola mirip youtube.py.

Butuh di .env: TWITCH_CLIENT_ID, TWITCH_CLIENT_SECRET, TWITCH_CHANNEL
(login channel), TWITCH_NOTIFY_CHANNEL_ID, TWITCH_CHECK_MINUTES (default 15).
Kalau belum dikonfigurasi, loop dilewati (log info sekali).
Token aplikasi di-cache di memori sampai kedaluwarsa.
"""
import datetime
import logging
import time

import discord
from discord.ext import commands, tasks

from src import config
from src.store import get_connection
from src.utils.embeds import base_embed

log = logging.getLogger("finch")


class Twitch(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._token: str | None = None
        self._token_exp: float = 0
        self._sudah_log_mati = False
        self.cek_twitch.start()

    def cog_unload(self):
        self.cek_twitch.cancel()

    async def _get_token(self) -> str | None:
        """App access token Twitch (client credentials), di-cache di memori."""
        if self._token and time.time() < self._token_exp - 60:
            return self._token
        cid = config.settings.twitch_client_id
        secret = config.settings.twitch_client_secret
        try:
            import aiohttp

            async with aiohttp.ClientSession() as sess:
                async with sess.post(
                    "https://id.twitch.tv/oauth2/token",
                    params={
                        "client_id": cid,
                        "client_secret": secret,
                        "grant_type": "client_credentials",
                    },
                    timeout=15,
                ) as resp:
                    if resp.status != 200:
                        log.warning("Twitch token status %s", resp.status)
                        return None
                    data = await resp.json()
        except Exception as e:
            log.warning("Twitch token error: %s", e)
            return None
        self._token = data.get("access_token")
        self._token_exp = time.time() + int(data.get("expires_in", 3600))
        return self._token

    @tasks.loop(minutes=15)
    async def cek_twitch(self):
        await self.bot.wait_until_ready()
        try:
            self.cek_twitch.change_interval(
                minutes=max(1, config.settings.twitch_check_minutes)
            )
        except Exception:
            pass
        cid = config.settings.twitch_client_id
        secret = config.settings.twitch_client_secret
        login = (config.settings.twitch_channel or "").lower().strip()
        notify_id = config.settings.twitch_notify_channel_id
        if not cid or not secret or not login:
            if not self._sudah_log_mati:
                log.info("Twitch belum dikonfigurasi — notifikasi live dilewati.")
                self._sudah_log_mati = True
            return
        token = await self._get_token()
        if not token:
            return
        headers = {"Client-ID": cid, "Authorization": f"Bearer {token}"}
        try:
            import aiohttp

            async with aiohttp.ClientSession() as sess:
                async with sess.get(
                    "https://api.twitch.tv/helix/streams",
                    params={"user_login": login},
                    headers=headers,
                    timeout=15,
                ) as resp:
                    if resp.status != 200:
                        log.warning("Twitch API streams status %s", resp.status)
                        return
                    data = await resp.json()
        except Exception as e:
            log.warning("Twitch API error: %s", e)
            return
        streams = data.get("data") or []
        with get_connection() as conn:
            row = conn.execute(
                "SELECT stream_id FROM twitch_live WHERE login = ?", (login,)
            ).fetchone()
        old_id = row[0] if row else None
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        if streams:
            s = streams[0]
            sid = str(s.get("id") or "")
            if sid and sid != old_id:
                channel = self.bot.get_channel(notify_id) if notify_id else None
                if isinstance(channel, discord.TextChannel):
                    title = s.get("title") or "(tanpa judul)"
                    game = s.get("game_name") or "-"
                    thumb = (s.get("thumbnail_url") or "").replace(
                        "{width}x{height}", "1280x720"
                    )
                    embed = base_embed(
                        "🔴 LIVE di Twitch!",
                        f"**{title}**\n🎮 {game}\nhttps://twitch.tv/{login}",
                    )
                    if thumb:
                        embed.set_image(url=thumb)
                    try:
                        await channel.send(
                            f"🔴 **{login}** lagi live!", embed=embed
                        )
                    except discord.Forbidden:
                        log.warning("Tidak bisa kirim notif Twitch (cek permission).")
                with get_connection() as conn:
                    conn.execute(
                        "INSERT INTO twitch_live (login, stream_id, notified_at) VALUES (?, ?, ?) "
                        "ON CONFLICT(login) DO UPDATE SET stream_id = excluded.stream_id, "
                        "notified_at = excluded.notified_at",
                        (login, sid, now_iso),
                    )
                    conn.commit()
                log.info("Twitch: %s live (stream %s).", login, sid)
        else:
            # offline → clear stream_id biar live berikutnya ketahuan
            if old_id is not None:
                with get_connection() as conn:
                    conn.execute(
                        "UPDATE twitch_live SET stream_id = NULL WHERE login = ?",
                        (login,),
                    )
                    conn.commit()

    @cek_twitch.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Twitch(bot))
