"""Starboard — pesan dengan ⭐ N otomatis dipajang di channel khusus.

- Member kasih reaksi ⭐ ke pesan → saat mencapai STARBOARD_MIN (default 3),
  pesan dipajang di channel starboard.
- Jumlah ⭐ di-update otomatis; kalau turun di bawah ambang, postingan dihapus.
- Config: STARBOARD_CHANNEL_ID, STARBOARD_MIN (fallback env global bila
  dashboard belum mengatur per-server).
- Bisa dimatikan per-server via dashboard: toggle `starboard_enabled` ("1"/"0",
  default "1" = ON selaras dashboard SETTING_DEFAULTS; tanpa channel
  terkonfigurasi starboard tetap tidak beraksi). Channel & ambang
  per-server via key `starboard_channel_id` / `starboard_threshold`.
"""
import logging

import discord
from discord.ext import commands

from src import config
from src.store import get_connection
from src.utils import economy as eko
from src.utils.embeds import finch_embed

log = logging.getLogger("finch")

BINTANG = "⭐"


def _embed_bintang(msg: discord.Message, count: int) -> discord.Embed:
    embed = finch_embed(
        "",
        (msg.content[:2000] if msg.content else "*(tanpa teks)*")
        + f"\n\n[Lihat pesan asli]({msg.jump_url})",
    )
    embed.timestamp = msg.created_at
    embed.set_author(
        name=str(msg.author),
        icon_url=msg.author.display_avatar.url if msg.author.display_avatar else None,
    )
    for att in msg.attachments:
        if att.content_type and att.content_type.startswith("image/"):
            embed.set_image(url=att.url)
            break
    return embed


class Starboard(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_raw_reaction_add(
        self, payload: discord.RawReactionActionEvent
    ):
        if str(payload.emoji) != BINTANG:
            return
        await self._sync(payload)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(
        self, payload: discord.RawReactionActionEvent
    ):
        if str(payload.emoji) != BINTANG:
            return
        await self._sync(payload)

    async def _sync(self, payload: discord.RawReactionActionEvent) -> None:
        from src.cogs.dashboard_sync import get_guild_setting, get_guild_setting_int

        if payload.guild_id is None:
            return
        gid = payload.guild_id
        # Starboard default ON selaras dashboard (SETTING_DEFAULTS starboard=true):
        # modul default aktif; tanpa channel terkonfigurasi tetap tidak beraksi
        # (sb_id = 0 -> return di bawah).
        # modul_aktif() tidak dipakai karena default "1"-nya tidak eksplisit
        # untuk key non-"*_enabled" lama — di sini eksplisit "1".
        if get_guild_setting(gid, "starboard_enabled", "1") != "1":
            return
        # Channel & ambang: utamakan per-server dari dashboard, fallback env global.
        sb_id = get_guild_setting_int(
            gid, "starboard_channel_id", 0
        ) or config.settings.starboard_channel_id
        if not sb_id:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        channel = guild.get_channel(payload.channel_id)
        sb_channel = guild.get_channel(sb_id)
        if (
            not isinstance(channel, discord.TextChannel)
            or not isinstance(sb_channel, discord.TextChannel)
            or channel.id == sb_id
        ):
            return
        try:
            msg = await channel.fetch_message(payload.message_id)
        except (discord.NotFound, discord.Forbidden):
            return
        if msg.author.bot:
            return

        count = sum(r.count for r in msg.reactions if str(r.emoji) == BINTANG)
        ambang = get_guild_setting_int(gid, "starboard_threshold", 0)
        if ambang < 1:
            ambang = config.settings.starboard_min
        ambang = max(1, ambang)

        # Klaim atomik SEBELUM kirim — dua reaksi ⭐ nyaris bersamaan tidak
        # akan membuat dua postingan (yang kalah race skip).
        with get_connection() as conn:
            row = conn.execute(
                "SELECT starboard_msg_id FROM starboard WHERE message_id = ?",
                (msg.id,),
            ).fetchone()
            claimed = False
            if row is None:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO starboard (message_id, starboard_msg_id, channel_id)"
                    " VALUES (?, 0, ?)",
                    (msg.id, channel.id),
                )
                claimed = cur.rowcount == 1
                conn.commit()

        if count >= ambang:
            embed = _embed_bintang(msg, count)
            if row and row[0]:
                try:
                    sb_msg = await sb_channel.fetch_message(row[0])
                    await sb_msg.edit(
                        content=f"⭐ **{count}** | {channel.mention}", embed=embed
                    )
                    return
                except discord.NotFound:
                    # Pesan starboard dihapus manual -> posting ulang & klaim ulang.
                    # (Dulu: jatuh ke `if not claimed: return` -> entri basi,
                    # update count berhenti selamanya.)
                    claimed = True
                except discord.Forbidden:
                    log.warning("Tidak bisa edit pesan starboard (cek permission).")
                    return
            if not claimed:
                return  # handler lain sedang memposting pesan ini
            try:
                sb_msg = await sb_channel.send(
                    f"⭐ **{count}** | {channel.mention}", embed=embed
                )
            except discord.Forbidden:
                # Lepaskan klaim biar reaksi berikutnya bisa coba lagi
                with get_connection() as conn:
                    conn.execute(
                        "DELETE FROM starboard WHERE message_id = ? AND starboard_msg_id = 0",
                        (msg.id,),
                    )
                    conn.commit()
                log.warning("Tidak bisa kirim ke starboard (cek permission).")
                return
            with get_connection() as conn:
                conn.execute(
                    "UPDATE starboard SET starboard_msg_id = ? WHERE message_id = ?",
                    (sb_msg.id, msg.id),
                )
                conn.commit()
            log.info("Starboard: pesan %s dipajang (%d ⭐).", msg.id, count)
            # reward koin untuk author — SEKALI per pesan (anti farm lepas/pasang ⭐)
            try:
                koin = config.settings.starboard_koin
                if koin > 0 and payload.guild_id:
                    with get_connection() as conn:
                        sudah = conn.execute(
                            "SELECT 1 FROM starboard_rewarded WHERE message_id = ?",
                            (msg.id,),
                        ).fetchone()
                        if not sudah:
                            conn.execute(
                                "INSERT INTO starboard_rewarded (message_id) VALUES (?)",
                                (msg.id,),
                            )
                            conn.commit()
                            eko.tambah_koin(conn, payload.guild_id, msg.author.id, koin)
            except Exception:
                log.exception("Gagal kasih koin starboard ke %s", msg.author.id)
        elif row and row[0]:
            # turun di bawah ambang → cabut dari starboard
            try:
                sb_msg = await sb_channel.fetch_message(row[0])
                await sb_msg.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
            with get_connection() as conn:
                conn.execute("DELETE FROM starboard WHERE message_id = ?", (msg.id,))
                conn.commit()


async def setup(bot: commands.Bot):
    await bot.add_cog(Starboard(bot))
