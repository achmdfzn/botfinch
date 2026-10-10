"""Auto-mod kata kasar — filter + sistem warning.

- Pesan mengandung kata di BAD_WORDS (.env) → dihapus + warning tercatat di DB.
- Warning mencapai WARN_MAX (default 3) → auto-mute MUTE_DURATION_MINUTES
  (pakai Discord timeout, persisten seperti auto-mute spam).
  Ambang bisa dioverride per-server via dashboard (`automod_warn_max`, 1–10).
- Moderator (Manage Messages) bypass filter.
- `/warnings [@user]` cek warning, `/reset-warn @user` reset (khusus mod).
- Anti-hoist ala Dyno/MEE6: display_name yang diawali karakter dekoratif
  non-alfanumerik (agar nangkring di atas member list) di-strip otomatis
  saat member join / ganti nama. Ikut toggle `automod_enabled`.
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


async def _kirim_aman(channel, teks: str, **kwargs) -> None:
    """Kirim peringatan tanpa crash listener bila izin kirim kurang.

    Lokal di modul ini (duplikat kecil dari moderation.py disengaja —
    import antar-cog dilarang ARCHITECTURE.md).
    """
    try:
        await channel.send(teks, **kwargs)
    except (discord.Forbidden, discord.HTTPException):
        pass


def warn_max_guild(guild_id: int) -> int:
    """Ambang warning pemicu auto-mute untuk satu server.

    Override per-server via dashboard (`automod_warn_max`, 1–10);
    fallback ke WARN_MAX global bila belum dikonfigurasi.
    """
    from src.cogs.dashboard_sync import get_guild_setting_int

    return max(1, min(10, get_guild_setting_int(guild_id, "automod_warn_max", config.settings.warn_max)))


def _strip_hoist(nama: str) -> str | None:
    """Strip karakter dekoratif non-alfanumerik di depan nama (trik hoist).

    Return nama bersih bila `nama` diawali karakter non-alfanumerik;
    return None bila nama sudah bersih (jangan disentuh). Maksimal
    10 karakter di-strip; bila sisa kosong, kembalikan "Member".
    Pure function — gampang dites.
    """
    if not nama or nama[0].isalnum():
        return None
    i = 0
    for ch in nama:
        if i >= 10 or ch.isalnum():
            break
        i += 1
    return nama[i:] or "Member"


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
    except (discord.NotFound, discord.HTTPException):
        log.warning("Gagal mute %s (error Discord).", member)
        return ""
    # Timeout BERHASIL: catat ke DB. DB error tidak boleh melempar keluar —
    # mute sudah jalan di Discord, cukup catat warning.
    try:
        with get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO mutes (user_id, guild_id, ends_at) VALUES (?, ?, ?)",
                (member.id, member.guild.id, until.isoformat()),
            )
            conn.commit()
    except Exception:
        log.exception("Gagal catat mute %s ke DB (mute Discord tetap jalan)", member)
    return f" 🔇 Di-mute {duration} menit."


class AutoMod(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _dehoist(self, member: discord.Member) -> None:
        """Strip dekorasi hoist dari display_name bila automod aktif."""
        # Import malas: pola yang sama dipakai listener lain di repo ini.
        from src.cogs.dashboard_sync import modul_aktif

        if not modul_aktif(member.guild.id, "automod_enabled"):
            return
        bersih = _strip_hoist(member.display_name)
        if bersih is None:
            return
        me = member.guild.me
        if me is None or not me.guild_permissions.manage_nicknames:
            return
        try:
            if member.top_role.position >= me.top_role.position:
                return  # target lebih tinggi hierarkinya
        except (AttributeError, TypeError):
            pass
        try:
            await member.edit(nick=bersih, reason="Anti-hoist otomatis")
            log.debug("Anti-hoist: %s → %s", member.display_name, bersih)
        except (discord.Forbidden, discord.HTTPException) as e:
            log.debug("Anti-hoist gagal untuk %s: %s", member, e)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        await self._dehoist(member)

    @commands.Cog.listener()
    async def on_member_update(
        self, before: discord.Member, after: discord.Member
    ):
        if before.display_name != after.display_name:
            await self._dehoist(after)

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
        except (discord.Forbidden, discord.HTTPException):
            pass

        try:
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
        except Exception:
            # DB gagal: pesan sudah dihapus, kirim teguran tanpa hitungan
            # (jangan crash listener).
            log.exception("Gagal catat warning kata kasar untuk %s", message.author)
            await _kirim_aman(
                message.channel,
                f"⚠️ {message.author.mention}, bahasa tidak pantas tidak boleh di sini!",
                delete_after=10,
            )
            return
        count = row[0] if row else 1
        maks = warn_max_guild(gid)
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
            await _kirim_aman(
                message.channel,
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
            await _kirim_aman(
                message.channel,
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
        maks = warn_max_guild(gid)
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
