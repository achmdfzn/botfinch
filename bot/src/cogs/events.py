"""Event server — buat acara + RSVP + reminder otomatis.

- `/event <nama> <waktu> <deskripsi>` (mod): waktu `DD-MM-YYYY HH:MM` (WIB).
  Post embed + tombol RSVP (Hadir ✅ / Tidak ❌ / Mungkin ❓).
- Loop 5 menit: event ≤1 jam lagi & belum diingatkan → reminder + mention yang Hadir.
- `/event-list`: acara yang akan datang.
"""
import datetime
import logging

import discord
from discord.ext import commands, tasks

from src.bot import MENTIONS_PENGUMUMAN
from src.store import get_connection
from src.utils.embeds import base_embed

log = logging.getLogger("finch")

WIB = datetime.timezone(datetime.timedelta(hours=7))
UTC = datetime.timezone.utc

STATUS_LABEL = {"hadir": "✅ Hadir", "tidak": "❌ Tidak", "mungkin": "❓ Mungkin"}


def parse_waktu_event(teks: str) -> datetime.datetime | None:
    """'25-12-2026 19:00' (WIB) -> datetime aware UTC. None kalau salah.

    Pure function — gampang dites.
    """
    try:
        naive = datetime.datetime.strptime((teks or "").strip(), "%d-%m-%Y %H:%M")
    except ValueError:
        return None
    return naive.replace(tzinfo=WIB).astimezone(UTC)


def embed_event(
    nama: str, deskripsi: str, kapan: datetime.datetime, counts: dict
) -> discord.Embed:
    """Embed event + hitungan RSVP. Pure (bangun embed) — gampang dites."""
    ts = int(kapan.timestamp())
    embed = base_embed("📅 " + nama, deskripsi or "*(tanpa deskripsi)*")
    embed.add_field(
        name="Waktu", value=f"<t:{ts}:F>\n(<t:{ts}:R>)", inline=True
    )
    embed.add_field(name="Hadir", value=f"**{counts.get('hadir', 0)}**", inline=True)
    embed.add_field(name="Tidak", value=f"**{counts.get('tidak', 0)}**", inline=True)
    embed.add_field(name="Mungkin", value=f"**{counts.get('mungkin', 0)}**", inline=True)
    return embed


def hitung_rsvp(conn, event_id: int) -> dict:
    """{'hadir': n, 'tidak': n, 'mungkin': n}. Pure query — gampang dites."""
    counts = {"hadir": 0, "tidak": 0, "mungkin": 0}
    for status, c in conn.execute(
        "SELECT status, COUNT(*) FROM event_rsvp WHERE event_id = ? GROUP BY status",
        (event_id,),
    ):
        if status in counts:
            counts[status] = c
    return counts


class RSVPView(discord.ui.View):
    """Tombol RSVP. custom_id memuat event_id agar survive restart (re-register di setup)."""

    def __init__(self, event_id: int):
        super().__init__(timeout=None)
        self.event_id = event_id
        for status, label in [
            ("hadir", "Hadir"),
            ("tidak", "Tidak"),
            ("mungkin", "Mungkin"),
        ]:
            btn = discord.ui.Button(
                label=label,
                style=discord.ButtonStyle.secondary,
                custom_id=f"finch:event-rsvp:{event_id}:{status}",
            )

            async def rsvp_cb(interaction: discord.Interaction, s=status):
                await _rsvp(interaction, event_id, s)

            btn.callback = rsvp_cb
            self.add_item(btn)


async def _rsvp(interaction: discord.Interaction, event_id: int, status: str) -> None:
    uid = interaction.user.id
    with get_connection() as conn:
        row = conn.execute(
            "SELECT nama, deskripsi, kapan FROM events WHERE id = ?", (event_id,)
        ).fetchone()
        if row is None:
            await interaction.response.send_message(
                "❌ Event tidak ketemu.", ephemeral=True
            )
            return
        nama, deskripsi, kapan_iso = row
        conn.execute(
            "INSERT INTO event_rsvp (event_id, user_id, status) VALUES (?, ?, ?) "
            "ON CONFLICT(event_id, user_id) DO UPDATE SET status = excluded.status",
            (event_id, uid, status),
        )
        conn.commit()
        counts = hitung_rsvp(conn, event_id)
    try:
        kapan = datetime.datetime.fromisoformat(kapan_iso)
        if kapan.tzinfo is None:
            kapan = kapan.replace(tzinfo=UTC)
    except ValueError:
        kapan = datetime.datetime.now(UTC)
    try:
        if interaction.message is not None:
            await interaction.message.edit(
                embed=embed_event(nama, deskripsi, kapan, counts), view=RSVPView(event_id)
            )
    except discord.HTTPException:
        pass
    await interaction.response.send_message(
        f"{STATUS_LABEL.get(status, status)} — RSVP-mu tercatat untuk **{nama}**!",
        ephemeral=True,
    )


class Events(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cek_event.start()

    def cog_unload(self):
        self.cek_event.cancel()

    @commands.hybrid_command(name="event", description="Buat event server (khusus mod)")
    @commands.has_permissions(manage_messages=True)
    @discord.app_commands.describe(
        nama="Nama event",
        waktu="Format: DD-MM-YYYY HH:MM (WIB). Contoh: 25-12-2026 19:00",
        deskripsi="Deskripsi event",
    )
    async def event(
        self, ctx: commands.Context, nama: str, waktu: str, *, deskripsi: str = ""
    ):
        """Buat event: /event "Mabar" "25-12-2026 19:00" Seru-seruan"""
        if ctx.guild is None:
            await ctx.send("❌ Hanya bisa di server.", ephemeral=True)
            return
        kapan = parse_waktu_event(waktu)
        if kapan is None:
            await ctx.send(
                "❌ Format waktu salah. Pakai `DD-MM-YYYY HH:MM` (WIB).\n"
                "Contoh: `/event Mabar 25-12-2026 19:00 Main bareng!`",
                ephemeral=True,
            )
            return
        if kapan <= datetime.datetime.now(UTC):
            await ctx.send("❌ Waktu event harus di masa depan.", ephemeral=True)
            return
        # Batas panjang agar embed tidak menabrak limit Discord
        # (judul 256, deskripsi 4096) — input lebih panjang = API 400.
        if len(nama.strip()) > 200:
            await ctx.send("❌ Nama event kepanjangan (maks 200 karakter).", ephemeral=True)
            return
        if len(deskripsi.strip()) > 2000:
            await ctx.send(
                "❌ Deskripsi event kepanjangan (maks 2000 karakter).", ephemeral=True
            )
            return
        embed = embed_event(nama.strip(), deskripsi.strip(), kapan, {})
        try:
            # Event dibuat mod -> boleh @everyone.
            msg = await ctx.channel.send(embed=embed, allowed_mentions=MENTIONS_PENGUMUMAN)
        except discord.HTTPException:
            await ctx.send("❌ Gagal posting event (cek permission).", ephemeral=True)
            return
        with get_connection() as conn:
            cur = conn.execute(
                "INSERT INTO events (guild_id, channel_id, message_id, nama, kapan, deskripsi) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    ctx.guild.id,
                    ctx.channel.id,
                    msg.id,
                    nama.strip(),
                    kapan.isoformat(),
                    deskripsi.strip(),
                ),
            )
            conn.commit()
            eid = cur.lastrowid
        try:
            await msg.edit(view=RSVPView(eid))
        except discord.HTTPException:
            pass
        await ctx.send(f"📅 Event **{nama.strip()}** dibuat! (ID: `{eid}`)", ephemeral=True)

    @commands.hybrid_command(name="event-list", description="Lihat event yang akan datang")
    async def event_list(self, ctx: commands.Context):
        """Lihat event: /event-list"""
        gid = ctx.guild.id if ctx.guild else 0
        now_iso = datetime.datetime.now(UTC).isoformat()
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT id, nama, kapan FROM events WHERE guild_id = ? AND kapan > ? "
                "ORDER BY kapan LIMIT 10",
                (gid, now_iso),
            ).fetchall()
            data = []
            for eid, nama, kapan_iso in rows:
                counts = hitung_rsvp(conn, eid)
                data.append((eid, nama, kapan_iso, counts))
        if not data:
            await ctx.send("📭 Tidak ada event yang akan datang.", ephemeral=True)
            return
        embed = base_embed("📅 Event Mendatang", f"Total: **{len(data)}**")
        for eid, nama, kapan_iso, counts in data:
            try:
                ts = int(datetime.datetime.fromisoformat(kapan_iso).timestamp())
                kapan_txt = f"<t:{ts}:F>"
            except ValueError:
                kapan_txt = kapan_iso
            embed.add_field(
                name=f"`{eid}` {nama}",
                value=f"{kapan_txt}\nHadir: {counts['hadir']} · Tidak: {counts['tidak']} · Ragu: {counts['mungkin']}",
                inline=False,
            )
        await ctx.send(embed=embed)

    @tasks.loop(minutes=5)
    async def cek_event(self):
        now = datetime.datetime.now(UTC)
        batas = now + datetime.timedelta(hours=1)
        try:
            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT id, guild_id, channel_id, nama, kapan FROM events "
                    "WHERE notif_terkirim = 0 AND kapan > ? AND kapan <= ?",
                    (now.isoformat(), batas.isoformat()),
                ).fetchall()
        except Exception:
            # Satu DB error tidak boleh membunuh loop 5-menit selamanya
            log.exception("Gagal baca events")
            return
        for eid, gid, cid, nama, kapan_iso in rows:
            try:
                ts = int(datetime.datetime.fromisoformat(kapan_iso).timestamp())
            except ValueError:
                ts = int(now.timestamp())
            try:
                with get_connection() as conn:
                    hadir = [
                        r[0]
                        for r in conn.execute(
                            "SELECT user_id FROM event_rsvp WHERE event_id = ? AND status = 'hadir'",
                            (eid,),
                        )
                    ]
            except Exception:
                log.exception("Gagal baca RSVP event %s", eid)
                continue
            channel = self.bot.get_channel(cid)
            if channel is None:
                continue  # coba lagi loop berikut
            if not isinstance(channel, discord.abc.Messageable):
                # ID menunjuk ke voice channel / kategori: .send tidak ada
                # (AttributeError) dan dulu membunuh loop 5-menit selamanya.
                log.warning("Event #%s: channel %s bukan channel teks.", eid, cid)
                continue
            mentions = " ".join(f"<@{u}>" for u in hadir)
            teks = f"⏰ **Reminder:** event **{nama}** dimulai <t:{ts}:R>!"
            if mentions:
                teks += f"\n{mentions}"
            try:
                # Nama event ditulis mod -> boleh @everyone.
                await channel.send(teks, allowed_mentions=MENTIONS_PENGUMUMAN)
            except discord.HTTPException:
                log.warning("Gagal kirim reminder event %s", eid)
                continue
            # Tandai terkirim HANYA setelah sukses (bug lama: ditandai dulu → hilang diam-diam)
            with get_connection() as conn:
                conn.execute("UPDATE events SET notif_terkirim = 1 WHERE id = ?", (eid,))
                conn.commit()

    @cek_event.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Events(bot))
    # re-register view RSVP agar tombol event lama tetap jalan setelah restart
    try:
        with get_connection() as conn:
            now_iso = datetime.datetime.now(UTC).isoformat()
            rows = conn.execute(
                "SELECT id FROM events WHERE kapan > ?", (now_iso,)
            ).fetchall()
        for (eid,) in rows:
            bot.add_view(RSVPView(eid))
    except Exception:
        log.exception("Gagal re-register RSVP views")
