"""Voice XP — dapat XP dari nongkrong di voice channel."""
import time
import logging
import discord
from discord.ext import commands

from src import config
from src.store import get_connection
from src.utils.embeds import base_embed
from src.utils.toggle import cek_toggle
from src.utils.xp import hitung_menit, tambah_xp

log = logging.getLogger("finch")

# (guild_id, user_id) -> start_timestamp
_voice_start: dict[tuple[int, int], float] = {}


def format_menit(menit: int) -> str:
    """120 -> '2 jam', 90 -> '1 jam 30 mnt', 45 -> '45 mnt'. Pure function."""
    menit = max(0, int(menit))
    if menit >= 60:
        jam, sisa = divmod(menit, 60)
        return f"{jam} jam {sisa} mnt" if sisa else f"{jam} jam"
    return f"{menit} mnt"


def sendiri_di_voice(channel, user_id: int) -> bool:
    """True bila tidak ada member non-bot lain di channel voice.

    Dipakai sebagai anti-farm: user yang idle sendirian di voice (atau
    deaf) tidak dapat XP/koin. Pure-ish — gampang dites.
    """
    try:
        members = channel.members
    except AttributeError:
        return True
    for m in members:
        if getattr(m, "id", None) != user_id and not getattr(m, "bot", False):
            return False
    return True


class VoiceXP(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot:
            return
        gid = member.guild.id
        uid = member.id
        key = (gid, uid)

        # join voice
        if before.channel is None and after.channel is not None:
            _voice_start[key] = time.time()
            return

        # leave voice
        if before.channel is not None and after.channel is None:
            start = _voice_start.pop(key, None)
            if start is None:
                # Sesi mungkin hilang karena restart bot
                log.info("User %s leave voice tapi tidak ada sesi (mungkin bot baru restart)", member.name)
                return
            durasi = time.time() - start
            menit = hitung_menit(durasi)
            if menit <= 0:
                return
            # Anti-farm: idle sendirian di voice, atau deaf (tidak
            # berpartisipasi) -> tidak dapat XP/koin/voice_total sama sekali.
            if sendiri_di_voice(before.channel, uid) or before.self_deaf or before.deaf:
                log.info(
                    "Voice XP dilewati untuk %s (sendirian/deaf)", member.name
                )
                return
            from src.cogs.dashboard_sync import modul_aktif

            leveling_on = modul_aktif(gid, "leveling_enabled")
            ekonomi_on = modul_aktif(gid, "economy_enabled")
            lvl, naik = 0, False
            if leveling_on:
                xp = menit * config.settings.voice_xp_per_min
                try:
                    with get_connection() as conn:
                        lvl, naik = tambah_xp(conn, gid, uid, xp)
                except Exception:
                    log.exception("Gagal tambah voice XP")
            # Quest harian: hitung menit voice
            try:
                from src.utils import quests as quest_utils

                with get_connection() as conn:
                    quest_utils.tambah_voice(conn, gid, uid, menit)
            except Exception:
                pass
            # Total menit voice + koin voice
            try:
                from src.utils import economy as eko

                with get_connection() as conn:
                    conn.execute(
                        "INSERT INTO voice_total (user_id, guild_id, menit)"
                        " VALUES (?, ?, ?)"
                        " ON CONFLICT(user_id, guild_id)"
                        " DO UPDATE SET menit = menit + ?",
                        (uid, gid, menit, menit),
                    )
                    conn.commit()
                    koin_voice = menit * config.settings.voice_koin_per_min
                    if ekonomi_on and koin_voice > 0:
                        eko.tambah_koin(conn, gid, uid, koin_voice)
            except Exception:
                log.exception("Gagal catat voice_total/koin voice")
            if naik:
                ch = member.guild.system_channel
                if ch is not None:
                    try:
                        await ch.send(f"🎉 Selamat {member.mention}, kamu naik ke **Level {lvl}** dari voice! 🚀", delete_after=10)
                    except discord.Forbidden:
                        pass
            # role reward coba kasih (reuse logic dari leveling)
            if leveling_on:
                try:
                    from src.utils.xp import beri_role_reward
                    await beri_role_reward(member, lvl)
                except Exception:
                    pass

        # move antar channel voice -> jangan reset, tetap hitung durasi
        # tidak perlu handle

    async def cog_check(self, ctx: commands.Context) -> bool:
        """Statistik voice milik modul Leveling (+Ekonomi untuk koin voice).

        Lolos bila salah satu dari keduanya aktif; diblokir hanya bila
        keduanya dimatikan — selaras /level & /rank yang ikut leveling_enabled.
        """
        if ctx.guild is None:
            return True
        from src.cogs.dashboard_sync import modul_aktif

        if modul_aktif(ctx.guild.id, "leveling_enabled") or modul_aktif(
            ctx.guild.id, "economy_enabled"
        ):
            return True
        return await cek_toggle(
            ctx,
            "leveling_enabled",
            "Modul leveling & ekonomi dimatikan oleh admin server ini.",
        )

    @commands.hybrid_command(name="top-voice", description="10 member paling lama di voice")
    async def top_voice(self, ctx: commands.Context):
        """Top voice: /top-voice"""
        gid = ctx.guild.id if ctx.guild else 0
        with get_connection() as conn:
            top = conn.execute(
                "SELECT user_id, menit FROM voice_total WHERE guild_id = ?"
                " ORDER BY menit DESC LIMIT 10",
                (gid,),
            ).fetchall()
        if not top:
            await ctx.send("Belum ada data voice.", ephemeral=True)
            return
        medals = ["🥇", "🥈", "🥉"]
        baris = []
        for i, (uid, menit) in enumerate(top):
            medal = medals[i] if i < 3 else f"`{i + 1}.`"
            baris.append(f"{medal} <@{uid}> — **{format_menit(menit)}**")
        embed = base_embed("🎙️ Top Voice")
        # UI horizontal: 2 kolom kesamping (1–5 | 6–10)
        embed.add_field(name="Peringkat 1–5", value="\n".join(baris[:5]) or "-", inline=True)
        embed.add_field(name="Peringkat 6–10", value="\n".join(baris[5:]) or "-", inline=True)
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(VoiceXP(bot))
