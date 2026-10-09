"""Moderasi+ Tahap 12 — pelengkap sistem yang sudah ada.

- Auto-lockdown saat raid join massal (beda ambang dari anti-raid di moderation.py).
- Log voice join/leave/pindah ke mod-log.
- /warn-list, /tiket-kategori, /faq, SLA tiket (loop 30 menit).
- Listener on_message: update balas_terakhir tiket (untuk SLA).
"""
import logging
import time
from collections import defaultdict, deque

import discord
from discord.ext import commands, tasks

from src import config
from src.store import get_connection
from src.utils import modlog
from src.utils.waktu import parse_iso
from src.utils.embeds import error_embed, finch_embed, sukses_embed

log = logging.getLogger("finch")

from src.utils.constants import KATEGORI_TIKET  # sumber tunggal; diimpor ulang oleh tests

# Auto-lockdown
JOIN_AMBANG = 8          # >=8 join dalam 60 detik -> lockdown
JOIN_WINDOW = 60
LOCKDOWN_COOLDOWN = 30 * 60  # jangan trigger 2x dalam 30 menit


class ModerasiPlus(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._join_riwayat: dict[int, deque] = defaultdict(lambda: deque(maxlen=50))
        self._lockdown_terakhir: dict[int, float] = {}

    def cog_unload(self):
        self.cek_sla.cancel()

    # ---------- 1. Auto-lockdown ----------

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        # Auto-lockdown adalah aksi moderasi otomatis -> ikut toggle automod.
        # Tanpa ini, admin yang mematikan AutoMod di dashboard tetap kena
        # lockdown semua channel saat 8 join dalam 60 detik.
        from src.cogs.dashboard_sync import get_guild_setting

        if get_guild_setting(member.guild.id, "automod_enabled", "1") != "1":
            return
        guild = member.guild
        now = time.time()
        dq = self._join_riwayat[guild.id]
        dq.append(now)
        while dq and now - dq[0] > JOIN_WINDOW:
            dq.popleft()
        if len(dq) < JOIN_AMBANG:
            return
        if now - self._lockdown_terakhir.get(guild.id, 0) < LOCKDOWN_COOLDOWN:
            return
        self._lockdown_terakhir[guild.id] = now
        await self._auto_lockdown(guild, len(dq))

    async def _auto_lockdown(self, guild: discord.Guild, jumlah: int) -> None:
        terkunci = 0
        for ch in guild.text_channels:
            try:
                # Snapshot permission asli (format sama seperti /lockdown)
                ow = ch.overwrites_for(guild.default_role)
                with get_connection() as conn:
                    conn.execute(
                        "INSERT OR IGNORE INTO lockdown_state (channel_id, guild_id, send_messages)"
                        " VALUES (?, ?, ?)",
                        (ch.id, guild.id,
                         None if ow.send_messages is None else int(ow.send_messages)),
                    )
                    conn.commit()
                await ch.set_permissions(
                    guild.default_role,
                    send_messages=False,
                    reason=f"Auto-lockdown: raid {jumlah} join/{JOIN_WINDOW}s",
                )
                terkunci += 1
            except (discord.Forbidden, discord.HTTPException):
                continue
            except Exception:
                log.exception("Auto-lockdown gagal di channel %s", ch.id)
        await modlog.log_event(
            self.bot,
            "🚨 AUTO-LOCKDOWN",
            f"Terdeteksi **{jumlah}** join dalam {JOIN_WINDOW} detik — "
            f"**{terkunci}** channel dikunci otomatis.\n"
            "Buka manual dengan `/unlockdown` setelah situasi aman.",
            discord.Color.dark_red(),
        )
        log.warning("Auto-lockdown guild %s: %d channel dikunci.", guild.id, terkunci)

    # ---------- 2. Voice log ----------

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        if before.channel == after.channel:
            return  # mute/deafen/stream saja -> abaikan
        # Log voice ikut toggle "Message Log" (msglog_enabled): admin yang
        # mematikan logging tidak boleh tetap dibanjiri join/leave voice.
        from src.cogs.dashboard_sync import modul_aktif

        if not modul_aktif(member.guild.id, "msglog_enabled"):
            return
        if before.channel is None and after.channel is not None:
            judul, teks = "🔊 Masuk Voice", f"{member.mention} masuk **{after.channel.name}**."
        elif after.channel is None and before.channel is not None:
            judul, teks = "🔇 Keluar Voice", f"{member.mention} keluar dari **{before.channel.name}**."
        else:
            judul, teks = (
                "🔀 Pindah Voice",
                f"{member.mention} pindah **{before.channel.name}** → **{after.channel.name}**.",
            )
        try:
            await modlog.log_event(self.bot, judul, teks, discord.Color.blurple())
        except Exception:
            log.exception("Gagal kirim log voice ke mod-log")

    # ---------- 3. /warn-list ----------

    @commands.hybrid_command(name="warn-list", description="Lihat daftar warning (khusus mod)")
    @commands.has_permissions(manage_messages=True)
    async def warn_list(self, ctx: commands.Context, user: discord.Member | None = None):
        """Warning list: /warn-list [@user]"""
        if ctx.guild is None:
            await ctx.send(embed=error_embed("Hanya bisa di server."), ephemeral=True)
            return
        gid = ctx.guild.id
        with get_connection() as conn:
            if user is not None:
                row = conn.execute(
                    "SELECT count, updated_at FROM warnings WHERE user_id = ? AND guild_id = ?",
                    (user.id, gid),
                ).fetchone()
                count, updated = row if row else (0, "-")
                embed = finch_embed(
                    f"⚠️ Warning {user.display_name}",
                    warna="moderasi",
                    thumbnail=user.display_avatar.url,
                )
                embed.add_field(name="Jumlah", value=f"**{count}**x", inline=True)
                embed.add_field(name="Terakhir", value=str(updated), inline=True)
                await ctx.send(embed=embed, ephemeral=True)
                return
            rows = conn.execute(
                "SELECT user_id, count, updated_at FROM warnings"
                " WHERE guild_id = ? AND count > 0 ORDER BY count DESC LIMIT 10",
                (gid,),
            ).fetchall()
        if not rows:
            await ctx.send(embed=finch_embed("⚠️ Warning", "Belum ada warning tercatat.", warna="moderasi"), ephemeral=True)
            return
        embed = finch_embed("⚠️ Top Warning", "10 user dengan warning terbanyak.", warna="moderasi")
        for uid, count, updated in rows:
            embed.add_field(
                name=f"<@{uid}>",
                value=f"**{count}**x\n_{updated}_",
                inline=True,
            )
        await ctx.send(embed=embed, ephemeral=True)

    # ---------- 4. /tiket-kategori ----------

    @commands.hybrid_command(name="tiket-kategori", description="Ubah kategori tiket ini (khusus mod)")
    @commands.has_permissions(manage_messages=True)
    @discord.app_commands.describe(kategori="Kategori baru tiket")
    @discord.app_commands.choices(
        kategori=[discord.app_commands.Choice(name=k, value=k) for k in KATEGORI_TIKET]
    )
    async def tiket_kategori(self, ctx: commands.Context, kategori: str):
        """Ubah kategori: /tiket-kategori Report (di dalam channel tiket)"""
        if ctx.guild is None or not isinstance(ctx.channel, discord.TextChannel):
            await ctx.send(embed=error_embed("Hanya bisa di server."), ephemeral=True)
            return
        if kategori not in KATEGORI_TIKET:
            await ctx.send(
                embed=error_embed(f"Kategori harus salah satu: {', '.join(KATEGORI_TIKET)}."),
                ephemeral=True,
            )
            return
        with get_connection() as conn:
            row = conn.execute(
                "SELECT channel_id FROM tickets WHERE channel_id = ? AND closed = 0",
                (ctx.channel.id,),
            ).fetchone()
            if row is None:
                await ctx.send(embed=error_embed("Channel ini bukan tiket aktif."), ephemeral=True)
                return
            conn.execute(
                "UPDATE tickets SET kategori = ? WHERE channel_id = ?",
                (kategori, ctx.channel.id),
            )
            conn.commit()
        await ctx.send(embed=sukses_embed("Kategori diubah", f"Tiket ini sekarang: **{kategori}**."))

    # ---------- 5. /faq ----------

    @commands.hybrid_command(name="faq", description="Cari jawaban cepat di FAQ")
    @discord.app_commands.describe(kata="Kata kunci yang dicari")
    async def faq(self, ctx: commands.Context, kata: str):
        """FAQ: /faq verifikasi"""
        if ctx.guild is None:
            await ctx.send(embed=error_embed("Hanya bisa di server."), ephemeral=True)
            return
        kunci = f"%{kata.strip()}%"
        # Tampilan dipotong + markdown di-escape: kata user mentah bisa merusak
        # format embed (atau melebihi batas 256 char judul embed).
        tampil = discord.utils.escape_markdown(kata.strip()[:60])
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT trigger, respons FROM autoresponder"
                " WHERE guild_id = ? AND (trigger LIKE ? OR respons LIKE ?) LIMIT 5",
                (ctx.guild.id, kunci, kunci),
            ).fetchall()
        if not rows:
            await ctx.send(
                embed=error_embed(
                    f"Tidak ketemu FAQ untuk **{tampil}**.\n"
                    "Buka tiket via `/panel-tiket` kalau butuh bantuan moderator."
                ),
                ephemeral=True,
            )
            return
        embed = finch_embed(f"❓ FAQ: {tampil}", warna="info")
        for trigger, respons in rows:
            embed.add_field(name=trigger[:200], value=respons[:500], inline=False)
        await ctx.send(embed=embed, ephemeral=True)

    # ---------- 6. SLA tiket ----------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        if not isinstance(message.channel, discord.TextChannel):
            return
        try:
            with get_connection() as conn:
                row = conn.execute(
                    "SELECT owner_id FROM tickets WHERE channel_id = ? AND closed = 0",
                    (message.channel.id,),
                ).fetchone()
                # SLA mengawasi respons MOD: pesan owner sendiri TIDAK me-reset timer
                if row and row[0] != message.author.id:
                    conn.execute(
                        "UPDATE tickets SET balas_terakhir = ? WHERE channel_id = ?",
                        (discord.utils.utcnow().isoformat(), message.channel.id),
                    )
                    conn.commit()
        except Exception:
            log.exception("Gagal update balas_terakhir tiket")

    @tasks.loop(minutes=30)
    async def cek_sla(self):
        batas_jam = config.settings.tiket_sla_jam
        now = discord.utils.utcnow()
        try:
            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT t.channel_id, t.guild_id, t.owner_id,"
                    " COALESCE(t.balas_terakhir, t.created_at)"
                    " FROM tickets t LEFT JOIN sla_warned s ON s.channel_id = t.channel_id"
                    " WHERE t.closed = 0 AND s.channel_id IS NULL"
                ).fetchall()
        except Exception:
            log.exception("Gagal baca tiket untuk SLA")
            return
        for channel_id, guild_id, owner_id, terakhir_iso in rows:
            try:
                terakhir = parse_iso(terakhir_iso)
                if terakhir is None:
                    continue
                if (now - terakhir).total_seconds() < batas_jam * 3600:
                    continue
                # Tandai di DB (persisten, anti alert ganda walau restart)
                try:
                    with get_connection() as conn:
                        conn.execute(
                            "INSERT OR IGNORE INTO sla_warned (channel_id, warned_at)"
                            " VALUES (?, ?)",
                            (channel_id, now.isoformat()),
                        )
                        conn.commit()
                except Exception:
                    log.exception("Gagal catat sla_warned %s", channel_id)
                    continue
                # Satu baris yang gagal kirim log tidak boleh membunuh loop 30-menit.
                try:
                    await modlog.log_event(
                        self.bot,
                        "⏰ SLA Tiket",
                        f"Tiket <#{channel_id}> (<@{owner_id}>) tidak ada balasan mod "
                        f"lebih dari **{batas_jam} jam**. Mohon segera ditindaklanjuti.",
                        discord.Color.orange(),
                    )
                except Exception:
                    log.exception("Gagal kirim peringatan SLA tiket %s", channel_id)
                log.warning("SLA tiket %s terlewati (%dh).", channel_id, batas_jam)
            except Exception:
                log.exception("Gagal proses SLA tiket %s", channel_id)

    @cek_sla.before_loop
    async def _before_sla(self):
        await self.bot.wait_until_ready()

    async def cog_load(self):
        self.cek_sla.start()


async def setup(bot: commands.Bot):
    await bot.add_cog(ModerasiPlus(bot))
