"""Notifikasi YouTube otomatis via RSS tanpa API key."""
import asyncio
import logging
import xml.etree.ElementTree as ET
import discord
from discord.ext import commands, tasks

from src import config
from src.store import get_connection
from src.utils.embeds import base_embed

log = logging.getLogger("finch")

NS = {"atom": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}

def parse_rss(xml_text: str) -> list[dict]:
    """Parse RSS YouTube -> list {videoId, title, published}."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    out = []
    for entry in root.findall("atom:entry", NS):
        vid_el = entry.find("yt:videoId", NS)
        title_el = entry.find("atom:title", NS)
        pub_el = entry.find("atom:published", NS)
        if vid_el is None or title_el is None:
            continue
        out.append({
            "videoId": vid_el.text or "",
            "title": title_el.text or "",
            "published": pub_el.text if pub_el is not None else "",
        })
    return out


class Youtube(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.seeded = False
        self.cek_youtube.start()

    def cog_unload(self):
        self.cek_youtube.cancel()

    @tasks.loop(minutes=15)
    async def cek_youtube(self):
        await self.bot.wait_until_ready()
        
        # Seed logic: Jangan post video saat baru jalan.
        if not self.seeded:
            with get_connection() as conn:
                # Ambil video terbaru dari RSS biar tahu latest
                yt_id = config.settings.yt_channel_id
                url = f"https://www.youtube.com/feeds/videos.xml?channel_id={yt_id}"
                try:
                    import aiohttp
                    async with aiohttp.ClientSession() as sess:
                        async with sess.get(url, timeout=15) as resp:
                            if resp.status == 200:
                                xml_text = await resp.text()
                                videos = parse_rss(xml_text)
                                for v in videos:
                                    conn.execute("INSERT OR IGNORE INTO yt_posts (video_id, posted_at) VALUES (?, datetime('now'))", (v["videoId"],))
                                conn.commit()
                except Exception:
                    pass
            self.seeded = True
            return

        # Retensi: hapus data lebih dari 90 hari
        with get_connection() as conn:
            conn.execute("DELETE FROM yt_posts WHERE posted_at < date('now','-90 days')")
            conn.commit()

        # update interval dinamis
        try:
            self.cek_youtube.change_interval(minutes=max(1, config.settings.yt_check_minutes))
        except Exception:
            pass
        yt_id = config.settings.yt_channel_id
        notify_id = config.settings.yt_notify_channel_id
        if not yt_id or not notify_id:
            return
        url = f"https://www.youtube.com/feeds/videos.xml?channel_id={yt_id}"
        try:
            import aiohttp
            async with aiohttp.ClientSession() as sess:
                async with sess.get(url, timeout=15) as resp:
                    if resp.status != 200:
                        log.warning("YouTube RSS status %s", resp.status)
                        return
                    xml_text = await resp.text()
        except Exception as e:
            log.warning("YouTube RSS fetch error: %s", e)
            return

        videos = parse_rss(xml_text)
        if not videos:
            return
        with get_connection() as conn:
            existing = {r[0] for r in conn.execute("SELECT video_id FROM yt_posts").fetchall()}

        channel = self.bot.get_channel(notify_id)
        if channel is None or not isinstance(channel, discord.TextChannel):
            return

        # post yang belum ada, urut dari lama -> baru biar urutan benar
        to_post = [v for v in reversed(videos) if v["videoId"] not in existing]
        for v in to_post:
            vid = v["videoId"]
            title = v["title"]
            link = f"https://youtu.be/{vid}"
            thumb = f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
            tanggal = v.get("published", "")[:10]
            deskripsi = f"**{title}**\n{link}"
            if tanggal:
                deskripsi += f"\nRilis: {tanggal}"
            embed = base_embed("📺 Video Baru!", deskripsi)
            embed.set_image(url=thumb)
            ping = ""
            role_id = config.settings.yt_ping_role_id
            if role_id:
                ping = f"<@&{role_id}> "
            try:
                await channel.send(content=ping + link, embed=embed)
            except discord.Forbidden:
                log.warning("Tidak bisa kirim notif YouTube")
            with get_connection() as conn:
                conn.execute("INSERT OR IGNORE INTO yt_posts (video_id, posted_at) VALUES (?, datetime('now'))", (vid,))
                conn.commit()
            await asyncio.sleep(1)

    @cek_youtube.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Youtube(bot))
