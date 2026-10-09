"""Sistem tiket support — channel privat per laporan.

- `/panel-tiket` (mod): pasang panel + tombol "Buat Tiket" (persistent, sekali saja).
- User klik → channel privat `tiket-<nama>` (hanya user + moderator yang bisa lihat).
- Di dalam tiket ada tombol "Tutup Tiket" → transcript (.txt) dikirim ke mod-log,
  channel dihapus. Maksimal 1 tiket terbuka per user.
"""
import asyncio
import io
import logging
import re

import discord
from discord.ext import commands

from src import config
from src.store import get_connection
from src.utils import modlog
from src.utils.embeds import base_embed

log = logging.getLogger("finch")

from src.utils.constants import KATEGORI_TIKET  # sumber tunggal; diimpor ulang oleh tests
TICKET_CREATE_ID = "finch:ticket-create"
TICKET_CLOSE_ID = "finch:ticket-close"


class TicketKategoriSelect(discord.ui.Select):
    """Pilih kategori tiket (dikirim sekali saat channel dibuat)."""

    def __init__(self):
        super().__init__(
            placeholder="Pilih kategori tiketmu...",
            custom_id="finch:tiket-kategori-select",
            options=[discord.SelectOption(label=k, value=k) for k in KATEGORI_TIKET],
        )

    async def callback(self, interaction: discord.Interaction):
        kategori = self.values[0]
        channel = interaction.channel
        member = interaction.user
        with get_connection() as conn:
            row = conn.execute(
                "SELECT owner_id FROM tickets WHERE channel_id = ? AND closed = 0",
                (channel.id,),
            ).fetchone()
        if row is None:
            await interaction.response.send_message(
                "❌ Channel ini bukan tiket aktif.", ephemeral=True
            )
            return
        boleh = (
            isinstance(member, discord.Member)
            and (member.id == row[0] or member.guild_permissions.manage_messages)
        )
        if not boleh:
            await interaction.response.send_message(
                "❌ Hanya pembuka tiket / moderator yang bisa memilih.", ephemeral=True
            )
            return
        with get_connection() as conn:
            conn.execute(
                "UPDATE tickets SET kategori = ? WHERE channel_id = ?",
                (kategori, channel.id),
            )
            conn.commit()
        for item in self.view.children:
            item.disabled = True
        await interaction.response.edit_message(
            content=f"✅ Kategori tiket: **{kategori}**.", view=self.view
        )
        self.view.stop()


class TicketKategoriView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=86400)  # 1 hari, cukup untuk dipilih pembuka
        self.add_item(TicketKategoriSelect())


class RatingPersistentView(discord.ui.View):
    """Tombol rating 1-5 bintang via DM — persisten (survive restart).

    custom_id tetap (tanpa tiket_id); tiket aktif diambil dari
    tabel tiket_rating_pending per user.
    """

    def __init__(self):
        super().__init__(timeout=None)
        for bintang in range(1, 6):
            btn = discord.ui.Button(
                label=str(bintang),
                style=discord.ButtonStyle.secondary,
                custom_id=f"finch:tiket-rate:{bintang}",
            )

            async def rate_cb(interaction: discord.Interaction, b=bintang):
                await self._rate(interaction, b)

            btn.callback = rate_cb
            self.add_item(btn)

    async def _rate(self, interaction: discord.Interaction, bintang: int) -> None:
        with get_connection() as conn:
            pending = conn.execute(
                "SELECT tiket_id, guild_id FROM tiket_rating_pending WHERE owner_id = ?",
                (interaction.user.id,),
            ).fetchone()
        if not pending:
            await interaction.response.send_message(
                "❌ Rating ini sudah kedaluwarsa.", ephemeral=True
            )
            return
        tiket_id, guild_id = pending
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO tiket_rating (tiket_id, guild_id, user_id, rating) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(tiket_id) DO UPDATE SET rating = excluded.rating",
                (tiket_id, guild_id, interaction.user.id, bintang),
            )
            conn.execute(
                "DELETE FROM tiket_rating_pending WHERE owner_id = ?",
                (interaction.user.id,),
            )
            conn.commit()
        for item in self.children:
            item.disabled = True
        try:
            await interaction.response.edit_message(
                content=f"⭐ Terima kasih! Kamu memberi rating **{bintang}/5**.",
                view=self,
            )
        except discord.HTTPException:
            await interaction.response.send_message(
                f"⭐ Terima kasih! Rating **{bintang}/5** tersimpan.", ephemeral=True
            )


async def kirim_dm_rating(
    bot: commands.Bot, guild_id: int, owner_id: int, tiket_id: int
) -> None:
    """DM pembuka tiket minta rating 1-5. Best effort."""
    try:
        with get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO tiket_rating_pending (owner_id, tiket_id, guild_id)"
                " VALUES (?, ?, ?)",
                (owner_id, tiket_id, guild_id),
            )
            conn.commit()
        user = bot.get_user(owner_id)
        if user is None:
            user = await bot.fetch_user(owner_id)
        await user.send(
            "🎫 Tiket support-mu sudah ditutup. Puas dengan pelayanannya?\n"
            "Kasih rating bintang yuk 👇",
            view=RatingPersistentView(),
        )
    except (discord.Forbidden, discord.HTTPException):
        pass
    except Exception:
        pass

_ticket_locks = {}  # (guild_id, user_id) -> asyncio.Lock (cegah klik ganda)


def format_transcript(entries: list[tuple[str, str, str]]) -> str:
    """Format transcript dari list (jam, author, isi). Pure function — gampang dites."""
    return "\n".join(f"[{jam}] {author}: {isi}" for jam, author, isi in entries)


def _nama_channel(member: discord.Member) -> str:
    dasar = re.sub(r"[^a-z0-9-]", "", member.name.lower().replace(" ", "-"))[:20]
    return f"tiket-{dasar or 'user'}"


async def buat_tiket(
    bot: commands.Bot,
    guild: discord.Guild,
    member: discord.Member,
    laporan: discord.Message | None = None,
) -> discord.TextChannel:
    """Buat channel tiket privat untuk member. Dipakai interaction + report context menu.

    Return channel yang baru dibuat. Caller yang urus ephemeral reply.
    Kalau gagal (Forbidden) raise.
    """
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        member: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
    }
    for role in guild.roles:
        if not role.is_default() and role.permissions.manage_messages:
            overwrites[role] = discord.PermissionOverwrite(
                read_messages=True, send_messages=True
            )

    nama = _nama_channel(member)
    if discord.utils.get(guild.text_channels, name=nama):
        nama = f"{nama}-{member.id % 100000}"

    category = None
    cat_id = config.settings.ticket_category_id
    if cat_id:
        ch = guild.get_channel(cat_id)
        if isinstance(ch, discord.CategoryChannel):
            category = ch

    # Cari tiket terbuka atau buat baru
    key = (guild.id, member.id)
    lock = _ticket_locks.get(key)
    if lock is None:
        lock = _ticket_locks[key] = asyncio.Lock()
    
    async with lock:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT channel_id FROM tickets WHERE guild_id = ? AND owner_id = ? AND closed = 0",
                (guild.id, member.id),
            ).fetchone()
            if row:
                ch = guild.get_channel(row[0])
                if ch and isinstance(ch, discord.TextChannel):
                    return ch

        channel = await guild.create_text_channel(
            nama, overwrites=overwrites, category=category, reason=f"Tiket dibuka {member}"
        )

        with get_connection() as conn:
            conn.execute(
                "INSERT INTO tickets (channel_id, guild_id, owner_id) VALUES (?, ?, ?)",
                (channel.id, guild.id, member.id),
            )
            conn.commit()

        embed = base_embed(
            "🎫 Tiket Dibuka",
            f"Halo {member.mention}! Tulis keluhan/pertanyaanmu di sini, "
            "moderator akan segera membantu.\n\nKlik **Tutup Tiket** kalau sudah selesai.",
        )
        if laporan:
            embed.add_field(name="Laporan Pesan", value=f"Author: {laporan.author.mention}\nIsi: {laporan.content[:500]}\n[Jump link]({laporan.jump_url})", inline=False)
        
        await channel.send(embed=embed, view=TicketCloseView())
        # Minta pembuka memilih kategori tiket (Tahap 12)
        try:
            await channel.send(
                "🏷️ Pilih kategori tiketmu di bawah ini:",
                view=TicketKategoriView(),
            )
        except discord.HTTPException:
            pass

        # log via bot instance dari caller (API publik — dulu pakai private API)
        await modlog.log_event(
            bot,
            "🎫 Tiket dibuka",
            f"{member.mention} membuka {channel.mention}.",
            discord.Color.blurple(),
        )
        return channel


async def _buat_tiket(interaction: discord.Interaction) -> None:
    user = interaction.user
    guild = interaction.guild
    if guild is None or not isinstance(user, discord.Member):
        await interaction.response.send_message(
            "❌ Tombol ini hanya bisa dipakai di server.", ephemeral=True
        )
        return

    with get_connection() as conn:
        row = conn.execute(
            "SELECT channel_id FROM tickets WHERE guild_id = ? AND owner_id = ? AND closed = 0",
            (guild.id, user.id),
        ).fetchone()
    if row:
        # Verifikasi channel masih ada — baris yatim (channel dihapus manual)
        # jangan memblokir user buka tiket baru selamanya.
        ch_lama = guild.get_channel(row[0])
        if ch_lama is not None:
            await interaction.response.send_message(
                f"❌ Kamu sudah punya tiket terbuka: <#{row[0]}>", ephemeral=True
            )
            return
        with get_connection() as conn:
            conn.execute(
                "UPDATE tickets SET closed = 1 WHERE guild_id = ? AND owner_id = ? AND closed = 0",
                (guild.id, user.id),
            )
            conn.commit()

    await interaction.response.defer(ephemeral=True)

    try:
        channel = await buat_tiket(interaction.client, guild, user)
    except discord.Forbidden:
        await interaction.followup.send(
            "❌ Bot butuh izin Manage Channels.", ephemeral=True
        )
        return
    except discord.HTTPException:
        await interaction.followup.send(
            "❌ Gagal membuat tiket (kesalahan Discord). Coba lagi ya.",
            ephemeral=True,
        )
        return
    except Exception:
        log.exception("Gagal membuat tiket untuk %s di guild %s", user.id, guild.id)
        await interaction.followup.send(
            "❌ Gagal membuat tiket. Coba lagi ya.", ephemeral=True
        )
        return

    await interaction.followup.send(f"✅ Tiket dibuat: {channel.mention}", ephemeral=True)


class TicketCreateView(discord.ui.View):
    """Persistent — tombol 'Buat Tiket' di panel."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Buat Tiket",
        style=discord.ButtonStyle.primary,
        custom_id=TICKET_CREATE_ID,
    )
    async def buat(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.bot:
            await interaction.response.send_message("❌ Bot tidak boleh pakai tombol ini.", ephemeral=True)
            return
        await _buat_tiket(interaction)


class TicketCloseView(discord.ui.View):
    """Persistent — tombol 'Tutup Tiket' di dalam channel tiket."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Tutup Tiket",
        style=discord.ButtonStyle.danger,
        custom_id=TICKET_CLOSE_ID,
    )
    async def tutup(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        member = interaction.user
        with get_connection() as conn:
            row = conn.execute(
                "SELECT owner_id FROM tickets WHERE channel_id = ? AND closed = 0",
                (channel.id,),
            ).fetchone()
        if row is None:
            await interaction.response.send_message(
                "❌ Channel ini bukan tiket aktif.", ephemeral=True
            )
            return
        boleh = (
            isinstance(member, discord.Member)
            and isinstance(channel, discord.TextChannel)
            and (member.id == row[0] or member.guild_permissions.manage_messages)
        )
        if not boleh:
            await interaction.response.send_message(
                "❌ Hanya pembuka tiket / moderator yang bisa menutup.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            "🔒 Menutup tiket, transcript dikirim ke mod-log...", ephemeral=True
        )

        # Guarded close: klaim penutupan atomik — double-click tombol
        # hanya diproses sekali (transcript + DM rating tidak ganda).
        with get_connection() as conn:
            cur = conn.execute(
                "UPDATE tickets SET closed = 1 WHERE channel_id = ? AND closed = 0",
                (channel.id,),
            )
            conn.commit()
        if cur.rowcount == 0:
            return  # sudah ditutup klik sebelumnya

        entries: list[tuple[str, str, str]] = []
        try:
            async for msg in channel.history(limit=200, oldest_first=True):
                isi = msg.content or f"[{len(msg.attachments)} lampiran]"
                entries.append(
                    (msg.created_at.strftime("%H:%M"), str(msg.author), isi)
                )
        except discord.Forbidden:
            pass
        transcript = format_transcript(entries) or "(kosong)"
        buf = io.BytesIO(transcript.encode("utf-8"))
        buf.seek(0)

        # Evict lock (cegah bocor memori lambat di _ticket_locks)
        if interaction.guild is not None:
            _ticket_locks.pop((interaction.guild.id, row[0]), None)

        await modlog.log_event(
            interaction.client,
            "🔒 Tiket ditutup",
            f"Tiket {channel.mention} dibuka oleh <@{row[0]}>, ditutup oleh {member.mention}.",
            discord.Color.greyple(),
            file=discord.File(buf, filename=f"transcript-{channel.name}.txt"),
        )
        # DM pembuka minta rating (sebelum channel dihapus)
        guild_id = channel.guild.id if isinstance(channel, discord.TextChannel) else 0
        await kirim_dm_rating(interaction.client, guild_id, row[0], channel.id)
        try:
            await channel.delete(reason="Tiket ditutup")
        except (discord.Forbidden, discord.HTTPException):
            # Tiket sudah ditutup di DB + transcript terkirim; channel yang
            # gagal dihapus bukan kegagalan fatal (admin bisa hapus manual).
            log.warning("Gagal hapus channel tiket %s setelah ditutup.", channel.id)


class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(
        name="panel-tiket", description="Pasang panel buat tiket (khusus mod)"
    )
    @commands.has_permissions(manage_guild=True)
    async def panel_tiket(self, ctx: commands.Context):
        """Pasang panel tiket: !panel-tiket / /panel-tiket (sekali saja)."""
        embed = base_embed(
            "🎫 Butuh Bantuan?",
            "Klik tombol di bawah untuk membuka **tiket privat** dengan moderator.\n\n"
            "Cocok untuk: laporan masalah, banding mute, pertanyaan sensitif.\n"
            "Maksimal 1 tiket terbuka per orang.",
        )
        await ctx.send(embed=embed, view=TicketCreateView())


    @commands.hybrid_command(
        name="tiket-rating", description="Lihat rata-rata rating tiket (mod)"
    )
    @commands.has_permissions(manage_messages=True)
    async def tiket_rating(self, ctx: commands.Context):
        """Rata-rata rating: /tiket-rating"""
        gid = ctx.guild.id if ctx.guild else 0
        with get_connection() as conn:
            row = conn.execute(
                "SELECT AVG(rating), COUNT(*), "
                "SUM(CASE WHEN rating >= 4 THEN 1 ELSE 0 END) "
                "FROM tiket_rating WHERE guild_id = ?",
                (gid,),
            ).fetchone()
        rata, jumlah, puas = row if row else (None, 0, 0)
        if not jumlah:
            await ctx.send("📭 Belum ada rating tiket.", ephemeral=True)
            return
        bintang = "⭐" * round(rata) if rata else "-"
        embed = base_embed("⭐ Rating Tiket Support")
        embed.add_field(name="Rata-rata", value=f"**{rata:.1f}/5** {bintang}", inline=True)
        embed.add_field(name="Total rating", value=f"**{jumlah}**", inline=True)
        embed.add_field(name="Puas (4-5)", value=f"**{puas}**", inline=True)
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
    bot.add_view(TicketCreateView())
    bot.add_view(TicketCloseView())
    bot.add_view(RatingPersistentView())
