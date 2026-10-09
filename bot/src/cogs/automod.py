"""Auto-mod kata kasar — filter + sistem warning.

- Pesan mengandung kata di BAD_WORDS (.env) → dihapus + warning tercatat di DB.
- Warning mencapai WARN_MAX (default 3) → auto-mute MUTE_DURATION_MINUTES
  (pakai Discord timeout, persisten seperti auto-mute spam).
- Moderator (Manage Messages) bypass filter.
- `/warnings [@user]` cek warning, `/reset-warn @user` reset (khusus mod).
"""
import datetime
import logging

import discord
from discord.ext import commands

from src import config
from src.store import get_connection
from src.utils import filters, modactions, modlog
from src.utils.embeds import base_embed

log = logging.getLogger("finch")


async def _mute(
    member: discord.Member, alasan: str, durasi_menit: int | None = None
) -> str:
    """Timeout member + catat ke tabel mutes. Return teks info (kosong kalau gagal)."""
    duration = durasi_menit or config.settings.mute_duration_minutes
    until = discord.utils.utcnow() + datetime.timedelta(minutes=duration)
    try:
        await member.timeout(until, reason=alasan)
    except discord.Forbidden:
        log.warning("Gagal mute %s (izin kurang).", member)
        return ""
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO mutes (user_id, guild_id, ends_at) VALUES (?, ?, ?)",
            (member.id, member.guild.id, until.isoformat()),
        )
        conn.commit()
    return f" 🔇 Di-mute {duration} menit."


class AutoMod(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        if message.author.guild_permissions.manage_messages:
            return  # moderator bypass
        # Kill switch + toggle filter kata kasar per-server via dashboard
        from src.cogs.dashboard_sync import get_guild_setting, get_guild_setting_int

        gid = message.guild.id
        if get_guild_setting(gid, "automod_enabled", "1") != "1":
            return
        if get_guild_setting(gid, "automod_badwords", "1") != "1":
            return

        words = config.settings.bad_words_list()
        if not words or not filters.contains_bad_word(message.content, words):
            return

        kata = filters.find_bad_word(message.content, words)
        try:
            await message.delete()
        except discord.Forbidden:
            pass

        with get_connection() as conn:
            conn.execute(
                "INSERT INTO warnings (user_id, guild_id, count) VALUES (?, ?, 1) "
                "ON CONFLICT(user_id, guild_id) DO UPDATE SET "
                "count = count + 1, updated_at = CURRENT_TIMESTAMP",
                (message.author.id, message.guild.id),
            )
            conn.commit()
            row = conn.execute(
                "SELECT count FROM warnings WHERE user_id = ? AND guild_id = ?",
                (message.author.id, message.guild.id),
            ).fetchone()
        count = row[0] if row else 1
        maks = max(1, config.settings.warn_max)
        # Override per-server via dashboard (batas aman 1–10080 menit)
        durasi = max(1, min(10080, get_guild_setting_int(gid, "automod_mute_minutes", config.settings.mute_duration_minutes)))
        log_ch = int(get_guild_setting(gid, "automod_log_channel_id", "") or 0) or None

        if count >= maks:
            # Mute DULU, reset warning HANYA bila mute berhasil.
            # (Urutan lama: reset dulu → kalau mute gagal, warning hilang permanen tanpa mute.)
            try:
                mute_txt = await _mute(message.author, f"Auto-mute: {maks}x warning kata kasar", durasi)
            except (discord.NotFound, discord.HTTPException) as e:
                log.warning("Auto-mute gagal untuk %s (%s); warning dipertahankan.", message.author, e)
                mute_txt = ""
            if mute_txt:
                with get_connection() as conn:
                    conn.execute(
                        "UPDATE warnings SET count = 0 WHERE user_id = ? AND guild_id = ?",
                        (message.author.id, message.guild.id),
                    )
                    conn.commit()
                modactions.catat_mod_action(
                    message.guild.id, message.author.id,
                    self.bot.user.id if self.bot.user else 0,
                    "mute", f"auto-mute: {maks}x warning kata kasar",
                )
            await message.channel.send(
                f"🚫 {message.author.mention}, sudah {maks}x kena warning kata kasar.{mute_txt}",
                delete_after=10,
            )
            await modlog.log_event(
                self.bot,
                "🚫 Auto-mute kata kasar",
                f"{message.author.mention} mencapai {maks}x warning "
                f"(kata: `{kata}`).{mute_txt}",
                discord.Color.red(),
                channel_id=log_ch,
            )
        else:
            await message.channel.send(
                f"⚠️ {message.author.mention}, bahasa tidak pantas tidak boleh di sini! "
                f"Warning {count}/{maks}.",
                delete_after=10,
            )
            await modlog.log_event(
                self.bot,
                "⚠️ Warning kata kasar",
                f"{message.author.mention} warning {count}/{maks} di "
                f"{message.channel.mention} (kata: `{kata}`).",
                discord.Color.orange(),
                channel_id=log_ch,
            )
            modactions.catat_mod_action(
                message.guild.id, message.author.id,
                self.bot.user.id if self.bot.user else 0,
                "warn", f"kata kasar ({kata}) — warning {count}/{maks}",
            )

    @commands.hybrid_command(
        name="warnings", description="Cek jumlah warning member (khusus mod)"
    )
    @commands.has_permissions(manage_messages=True)
    async def warnings(self, ctx: commands.Context, member: discord.Member = None):
        """Cek warning: !warnings @user / /warnings [@user]"""
        target = member or ctx.author
        gid = ctx.guild.id if ctx.guild else 0
        with get_connection() as conn:
            row = conn.execute(
                "SELECT count FROM warnings WHERE user_id = ? AND guild_id = ?",
                (target.id, gid),
            ).fetchone()
        count = row[0] if row else 0
        maks = max(1, config.settings.warn_max)
        embed = base_embed(
            f"⚠️ Warning — {target.display_name}",
            f"**{count}/{maks}** warning.\n"
            f"{'Auto-mute saat mencapai batas.' if count < maks else 'Sudah mencapai batas!'}",
        )
        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(
        name="reset-warn", description="Reset warning member (khusus mod)"
    )
    @commands.has_permissions(manage_messages=True)
    async def reset_warn(self, ctx: commands.Context, member: discord.Member):
        """Reset warning: !reset-warn @user / /reset-warn @user"""
        gid = ctx.guild.id if ctx.guild else 0
        with get_connection() as conn:
            conn.execute(
                "UPDATE warnings SET count = 0 WHERE user_id = ? AND guild_id = ?",
                (member.id, gid),
            )
            conn.commit()
        await ctx.send(f"✅ Warning {member.mention} di-reset.", ephemeral=True)
        modactions.catat_mod_action(gid, member.id, ctx.author.id, "reset-warn", "")
        await modlog.log_event(
            self.bot,
            "✅ Warning di-reset",
            f"{ctx.author.mention} me-reset warning {member.mention}.",
            discord.Color.green(),
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoMod(bot))
