"""Moderasi: anti-spam, anti-invite-link, dan bersih-bersih."""
import asyncio
import datetime
import logging
import time
from collections import defaultdict, deque

import discord
from discord.ext import commands, tasks

from src import config
from src.store import get_connection
from src.utils import embeds, filters, modactions, modlog
from src.utils.views import TimeoutSafeView, bind_view_message

log = logging.getLogger("finch")

_riwayat = defaultdict(lambda: deque())
# channel_id -> deque[timestamp] untuk slowmode otomatis (dibatasi 200 channel)
_slowmode_riwayat: dict[int, deque] = defaultdict(lambda: deque())
# guild_id -> deque[timestamp] join untuk anti-raid
_join_riwayat: dict[int, deque] = defaultdict(lambda: deque())


def _caps_berlebihan(teks: str) -> bool:
    """True bila pesan panjang dan mayoritas hurufnya kapital."""
    huruf = [c for c in (teks or "") if c.isalpha()]
    if len(huruf) < 10:
        return False
    kapital = sum(1 for c in huruf if c.isupper())
    return kapital / len(huruf) > 0.7


class ConfirmBersihkanView(TimeoutSafeView):
    def __init__(self, author_id: int, jumlah: int, cog: "Moderation"):
        super().__init__(timeout=30)
        self.author_id = author_id
        self.jumlah = jumlah
        self.cog = cog

    @discord.ui.button(label="Ya, bersihkan", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Hanya pemanggil yang bisa konfirmasi.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        # eksekusi purge
        try:
            channel = interaction.channel
            deleted = await channel.purge(limit=self.jumlah, oldest_first=False, bulk=True)
            count = len(deleted)
        except discord.Forbidden:
            await interaction.followup.send("❌ Bot butuh izin Manage Messages + Read History.", ephemeral=True)
            return
        except discord.HTTPException as e:
            await interaction.followup.send(f"❌ Gagal bersihkan: {e.text[:100] if hasattr(e, 'text') else str(e)[:100]}", ephemeral=True)
            return

        # embed keren
        embed = embeds.base_embed("🧹 Bersihkan Selesai", f"**{count}** pesan berhasil dihapus di {channel.mention}")
        embed.add_field(name="Moderator", value=interaction.user.mention, inline=True)
        embed.add_field(name="Jumlah", value=f"`{count}`", inline=True)
        embed.color = discord.Color.green()
        if interaction.guild and interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)

        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(embed=embed, view=self)
        # mod-log
        try:
            await modlog.log_event(
                self.cog.bot,
                "🧹 Pesan dibersihkan",
                f"{interaction.user.mention} menghapus {count} pesan di {channel.mention}.",
                discord.Color.blurple(),
            )
        except Exception:
            pass
        if interaction.guild:
            modactions.catat_mod_action(
                interaction.guild.id, 0, interaction.user.id,
                "bersihkan", f"{count} pesan di #{channel.name}",
            )

    @discord.ui.button(label="Batal", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Hanya pemanggil yang bisa batal.", ephemeral=True)
            return
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="❌ Dibatalkan.", embed=None, view=self)

class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_mutes.start()

    def cog_unload(self):
        self.check_mutes.cancel()

    @tasks.loop(minutes=1)
    async def check_mutes(self):
        try:
            with get_connection() as conn:
                conn.execute("DELETE FROM mutes WHERE ends_at < ?", (discord.utils.utcnow().isoformat(),))
                conn.commit()
        except Exception:
            # Satu DB error tidak boleh membunuh loop 1-menit selamanya
            log.exception("Gagal bersihkan tabel mutes")
        # Evict _riwayat anti-spam: buang timestamp >1 jam, hapus key yang kosong
        batas = time.time() - 3600
        for key in list(_riwayat.keys()):
            dq = _riwayat[key]
            while dq and dq[0] < batas:
                dq.popleft()
            if not dq:
                del _riwayat[key]

    @check_mutes.before_loop
    async def before_mutes(self):
        await self.bot.wait_until_ready()

    async def _reply(self, ctx: commands.Context, msg: str = None, *, embed: discord.Embed = None, ephemeral: bool = False, view=None):
        """Kirim balasan (prefix/slash). Return pesan yang dikirim (bisa None untuk slash)."""
        content = msg
        kw = dict(ephemeral=ephemeral)
        if embed:
            kw["embed"] = embed
        if view:
            kw["view"] = view
        if ctx.interaction:
            if not ctx.interaction.response.is_done():
                await ctx.interaction.response.send_message(content, **kw)
                return None
            else:
                return await ctx.followup.send(content, **kw)
        else:
            # prefix tidak support ephemeral/view ephemeral -> kirim biasa
            return await ctx.send(content, embed=embed, view=view)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        gid = member.guild.id
        with get_connection() as conn:
            row = conn.execute("SELECT ends_at FROM mutes WHERE user_id = ? AND guild_id = ?", (member.id, gid)).fetchone()
        if row:
            try:
                ends_at = datetime.datetime.fromisoformat(row[0])
                if ends_at.tzinfo is None:
                    ends_at = ends_at.replace(tzinfo=datetime.timezone.utc)
                if discord.utils.utcnow() < ends_at:
                    await member.timeout(ends_at, reason="Persisten mute: spam")
            except Exception as e:
                log.warning("Gagal re-apply mute untuk %s: %s", member, e)
        # Anti-raid: >=5 join dalam 60 detik -> naikkan verification level
        dq = _join_riwayat[gid]
        now = time.time()
        dq.append(now)
        while dq and now - dq[0] > 60:
            dq.popleft()
        if len(dq) >= 5:
            jumlah = len(dq)
            dq.clear()  # cegah trigger berulang
            try:
                await member.guild.edit(
                    verification_level=discord.VerificationLevel.high,
                    reason="Anti-raid otomatis: banyak join mendadak",
                )
            except (discord.Forbidden, discord.HTTPException) as e:
                log.warning("Anti-raid: gagal naikkan verification level (%s)", e)
                return
            except Exception:
                return
            try:
                await modlog.log_event(
                    self.bot,
                    "🚨 Kemungkinan raid terdeteksi",
                    f"**{jumlah}** member join dalam 60 detik. "
                    "Verification level server dinaikkan ke **high**.",
                    discord.Color.red(),
                )
            except Exception:
                pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        # Modul AutoMod bisa dimatikan per-server via dashboard web
        from src.cogs.dashboard_sync import get_guild_setting, get_guild_setting_int

        gid = message.guild.id
        if get_guild_setting(gid, "automod_enabled", "1") != "1":
            return
        log_ch = int(get_guild_setting(gid, "automod_log_channel_id", "") or 0) or None
        # Slowmode otomatis: >20 pesan/30 detik di text channel -> slowmode 10 dtk (5 menit)
        await self._cek_slowmode(message)
        if message.author.guild_permissions.manage_messages:
            return
        if get_guild_setting(gid, "automod_invites", "1") == "1" and config.settings.anti_invite and filters.contains_invite_link(message.content):
            try:
                await message.delete()
            except discord.Forbidden:
                pass
            await message.channel.send(f"🚫 {message.author.mention}, link invite tidak boleh di sini ya!", delete_after=10)
            await modlog.log_event(self.bot, "🚫 Invite link dihapus", f"{message.author.mention} kirim invite di {message.channel.mention}", discord.Color.orange(), channel_id=log_ch)
            return

        if get_guild_setting(gid, "automod_caps", "1") == "1" and _caps_berlebihan(message.content):
            try:
                await message.delete()
            except discord.Forbidden:
                pass
            await message.channel.send(f"🔠 {message.author.mention}, jangan caps berlebihan ya!", delete_after=10)
            await modlog.log_event(self.bot, "🔠 Caps dihapus", f"{message.author.mention} kirim caps berlebihan di {message.channel.mention}", discord.Color.orange(), channel_id=log_ch)
            return

        if get_guild_setting(gid, "automod_spam", "1") != "1":
            return
        now = time.time()
        riwayat = _riwayat[(message.guild.id, message.author.id)]
        riwayat.append(now)
        jendela = config.settings.spam_window_seconds
        while riwayat and now - riwayat[0] > jendela:
            riwayat.popleft()
        if len(riwayat) > config.settings.spam_max_messages:
            try:
                await message.delete()
            except discord.Forbidden:
                pass
            duration = max(1, min(10080, get_guild_setting_int(gid, "automod_mute_minutes", config.settings.mute_duration_minutes)))
            until = discord.utils.utcnow() + datetime.timedelta(minutes=duration)
            mute_txt = ""
            try:
                await message.author.timeout(until, reason="Auto-mute: spam")
                with get_connection() as conn:
                    conn.execute("INSERT OR REPLACE INTO mutes (user_id, guild_id, ends_at) VALUES (?, ?, ?)", (message.author.id, message.guild.id, until.isoformat()))
                    conn.commit()
                mute_txt = f" 🔇 Di-mute {duration} menit."
            except discord.Forbidden:
                pass
            if mute_txt:
                modactions.catat_mod_action(
                    message.guild.id, message.author.id,
                    self.bot.user.id if self.bot.user else 0,
                    "mute", "auto-mute: spam",
                )
            await message.channel.send(f"⚠️ {message.author.mention}, pelan-pelan ya! Jangan spam.{mute_txt}", delete_after=10)
            await modlog.log_event(self.bot, "⚠️ Spam + Mute", f"{message.author.mention} kena filter di {message.channel.mention}.", discord.Color.orange(), channel_id=log_ch)
            riwayat.clear()

    async def _cek_slowmode(self, message: discord.Message) -> None:
        """Aktifkan slowmode 10 detik otomatis saat channel terlalu ramai."""
        ch = message.channel
        if not isinstance(ch, discord.TextChannel):
            return
        now = time.time()
        dq = _slowmode_riwayat[ch.id]
        dq.append(now)
        while dq and now - dq[0] > 30:
            dq.popleft()
        # Batasi 200 channel yang dilacak: buang yang sepi >5 menit
        if len(_slowmode_riwayat) > 200:
            batas = now - 300
            for k in [k for k, v in _slowmode_riwayat.items() if not v or v[-1] < batas][:50]:
                del _slowmode_riwayat[k]
        if len(dq) <= 20:
            return
        try:
            delay = ch.slowmode_delay or 0
        except Exception:
            return
        if delay >= 10:
            return
        try:
            await ch.edit(slowmode_delay=10, reason="Slowmode otomatis: chat terlalu ramai")
        except (discord.Forbidden, discord.HTTPException):
            return
        except Exception:
            return
        log.info("Slowmode otomatis aktif di #%s (%d pesan/30 dtk).", ch.name, len(dq))
        dq.clear()

        async def _kembalikan():
            await asyncio.sleep(300)
            try:
                await ch.edit(slowmode_delay=0, reason="Slowmode otomatis selesai")
            except (discord.Forbidden, discord.HTTPException):
                pass
            except Exception:
                pass

        asyncio.create_task(_kembalikan())

    @commands.Cog.listener()
    async def on_message_edit(
        self, before: discord.Message, after: discord.Message
    ):
        if after.author.bot or not after.guild:
            return
        if before.content == after.content or not after.content:
            return
        try:
            await modlog.log_event(
                self.bot,
                "✏️ Pesan diedit",
                f"{after.author.mention} di {after.channel.mention}:\n"
                f"Sebelum: {before.content[:200]}\n"
                f"Sesudah: {after.content[:500]}",
                discord.Color.gold(),
            )
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        author = getattr(message, "author", None)
        if author is None or author.bot:
            return
        if not message.guild or not message.content:
            return
        # Anti-banjir: pesan counting yang dihapus tidak di-log
        if message.channel.id == config.settings.counting_channel_id:
            return
        try:
            await modlog.log_event(
                self.bot,
                "🗑️ Pesan dihapus",
                f"{author.mention} di {message.channel.mention}:\n{message.content[:500]}",
                discord.Color.dark_grey(),
            )
        except Exception:
            pass

    @commands.hybrid_command(name="lockdown", description="Kunci semua text channel (khusus admin)")
    @commands.has_permissions(administrator=True)
    @discord.app_commands.describe(alasan="Alasan lockdown")
    async def lockdown(self, ctx: commands.Context, *, alasan: str = "Lockdown oleh admin"):
        """Kunci kirim pesan di semua text channel: /lockdown [alasan]"""
        if not ctx.guild:
            await self._reply(ctx, "❌ Hanya bisa di server.", ephemeral=True)
            return
        terkunci = 0
        for ch in ctx.guild.text_channels:
            try:
                # Snapshot permission asli @everyone (agar unlockdown mengembalikan,
                # bukan merusak channel yang memang read-only). INSERT OR IGNORE:
                # lockdown ganda tidak menimpa snapshot pertama.
                ow = ch.overwrites_for(ctx.guild.default_role)
                with get_connection() as conn:
                    conn.execute(
                        "INSERT OR IGNORE INTO lockdown_state (channel_id, guild_id, send_messages)"
                        " VALUES (?, ?, ?)",
                        (ch.id, ctx.guild.id,
                         None if ow.send_messages is None else int(ow.send_messages)),
                    )
                    conn.commit()
                await ch.set_permissions(
                    ctx.guild.default_role,
                    send_messages=False,
                    reason=f"Lockdown: {alasan}",
                )
                terkunci += 1
            except discord.Forbidden:
                continue
            except discord.HTTPException:
                continue
            except Exception:
                continue
        try:
            await modlog.log_event(
                self.bot,
                "🔒 Lockdown",
                f"{ctx.author.mention} mengunci **{terkunci}** channel.\nAlasan: {alasan}",
                discord.Color.red(),
            )
        except Exception:
            pass
        modactions.catat_mod_action(
            ctx.guild.id, 0, ctx.author.id, "lockdown",
            f"{terkunci} channel dikunci — {alasan}",
        )
        await self._reply(ctx, f"🔒 Lockdown aktif: **{terkunci}** channel dikunci.", ephemeral=True)

    @commands.hybrid_command(name="unlockdown", description="Buka kunci semua text channel (khusus admin)")
    @commands.has_permissions(administrator=True)
    async def unlockdown(self, ctx: commands.Context):
        """Buka lockdown: /unlockdown"""
        if not ctx.guild:
            await self._reply(ctx, "❌ Hanya bisa di server.", ephemeral=True)
            return
        dibuka = 0
        snapshots = {}
        with get_connection() as conn:
            for r in conn.execute(
                "SELECT channel_id, send_messages FROM lockdown_state WHERE guild_id = ?",
                (ctx.guild.id,),
            ):
                snapshots[r[0]] = r[1]
        for ch in ctx.guild.text_channels:
            try:
                # Kembalikan permission asli; tanpa snapshot → netral (None)
                val = snapshots.get(ch.id)
                await ch.set_permissions(
                    ctx.guild.default_role,
                    send_messages=None if val is None else bool(val),
                    reason="Unlockdown",
                )
                dibuka += 1
            except discord.Forbidden:
                continue
            except discord.HTTPException:
                continue
            except Exception:
                continue
        with get_connection() as conn:
            conn.execute("DELETE FROM lockdown_state WHERE guild_id = ?", (ctx.guild.id,))
            conn.commit()
        try:
            await modlog.log_event(
                self.bot,
                "🔓 Lockdown dibuka",
                f"{ctx.author.mention} membuka **{dibuka}** channel.",
                discord.Color.green(),
            )
        except Exception:
            pass
        modactions.catat_mod_action(
            ctx.guild.id, 0, ctx.author.id, "unlockdown",
            f"{dibuka} channel dibuka",
        )
        await self._reply(ctx, f"🔓 Lockdown dibuka: **{dibuka}** channel.", ephemeral=True)

    @commands.hybrid_command(name="bersihkan", description="Hapus pesan massal (1-100) dengan konfirmasi")
    @commands.has_permissions(manage_messages=True)
    @discord.app_commands.describe(jumlah="Jumlah pesan yang akan dihapus (1-100)")
    async def bersihkan(self, ctx: commands.Context, jumlah: int = 10):
        """Hapus pesan massal (khusus moderator): !bersihkan 10 / /bersihkan 10 — dengan UI konfirmasi."""
        if not ctx.guild:
            await self._reply(ctx, "❌ Hanya bisa di server.", ephemeral=True)
            return
        # block channel sensitif
        dilindungi = {i for i in (config.settings.mod_log_channel_id, config.settings.verify_channel_id) if i}
        if ctx.channel.id in dilindungi:
            await self._reply(ctx, "❌ Tidak boleh bersihkan di channel log/verifikasi.", ephemeral=True)
            return
        jumlah = max(1, min(int(jumlah), 100))

        embed = embeds.base_embed("⚠️ Konfirmasi Bersihkan", f"Kamu akan menghapus **{jumlah}** pesan terakhir di {ctx.channel.mention}.\nLanjutkan?")
        embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
        embed.add_field(name="Jumlah", value=f"`{jumlah}`", inline=True)
        embed.set_footer(text="Finch")

        view = ConfirmBersihkanView(ctx.author.id, jumlah, self)
        # kalau slash: ephemeral konfirmasi biar tidak spam channel publik
        is_slash = ctx.interaction is not None
        sent = await self._reply(ctx, embed=embed, view=view, ephemeral=is_slash)
        await bind_view_message(ctx, view, sent)


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))