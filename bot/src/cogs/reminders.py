"""Pengingat — `/remind 10m <pesan>`.

Bot mengirim DM saat waktunya tiba (fallback: mention di channel asal).
`/remind-list` lihat yang aktif, `/remind-batal <id>` batalkan.
Data di SQLite sehingga survive restart.
"""
import datetime
import logging

import discord
from discord.ext import commands, tasks

from src.store import get_connection
from src.utils.embeds import base_embed
from src.utils.filters import parse_durasi
from src.utils.rutin import catat_gagal_rutin

log = logging.getLogger("finch")

MAKS_DETIK = 30 * 24 * 3600  # 30 hari


def ambil_jatuh_tempo(conn, now_iso: str):
    """Reminder yang sudah waktunya & belum dikirim. Pure query — gampang dites."""
    return conn.execute(
        "SELECT id, user_id, channel_id, message FROM reminders "
        "WHERE done = 0 AND remind_at <= ?",
        (now_iso,),
    ).fetchall()


def _format_interval(detik: int) -> str:
    """3600 -> '1 jam', 90000 -> '1 hari 1 jam'. Pure — gampang dites."""
    detik = int(detik)
    hari, sisa = divmod(detik, 86400)
    jam, sisa = divmod(sisa, 3600)
    menit, _ = divmod(sisa, 60)
    bagian = []
    if hari:
        bagian.append(f"{hari} hari")
    if jam:
        bagian.append(f"{jam} jam")
    if menit or not bagian:
        bagian.append(f"{menit} menit")
    return " ".join(bagian)


def ambil_rutin_jatuh_tempo(conn, now: "datetime.datetime"):
    """Pengingat rutin yang intervalnya sudah lewat sejak `terakhir`.

    Return list (id, user_id, channel_id, teks). Pure-ish — gampang dites.
    """
    out = []
    for rid, user_id, channel_id, interval_detik, teks, terakhir in conn.execute(
        "SELECT id, user_id, channel_id, interval_detik, teks, terakhir "
        "FROM reminder_rutin"
    ).fetchall():
        if not terakhir:
            continue
        try:
            last = datetime.datetime.fromisoformat(terakhir)
        except ValueError:
            continue
        if last.tzinfo is None:
            last = last.replace(tzinfo=datetime.timezone.utc)
        if (now - last).total_seconds() >= interval_detik:
            out.append((rid, user_id, channel_id, teks))
    return out


class Reminders(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Hitung kegagalan beruntun per rutin (channel dihapus → jangan retry selamanya)
        self._rutin_gagal: dict[int, int] = {}
        self.cek_reminder.start()

    def cog_unload(self):
        self.cek_reminder.cancel()

    @tasks.loop(seconds=30)
    async def cek_reminder(self):
        try:
            now = discord.utils.utcnow().isoformat()
            with get_connection() as conn:
                rows = ambil_jatuh_tempo(conn, now)
        except Exception:
            # Satu DB error tidak boleh membunuh loop 30-detik selamanya
            log.exception("Gagal baca reminders")
            return
        for rid, user_id, channel_id, pesan in rows:
            try:
                await self._kirim(rid, user_id, channel_id, pesan)
            except Exception:
                log.exception("Gagal kirim reminder %s", rid)
        # pengingat rutin (interval berulang)
        try:
            now_dt = discord.utils.utcnow()
            with get_connection() as conn:
                rutin = ambil_rutin_jatuh_tempo(conn, now_dt)
        except Exception:
            log.exception("Gagal baca reminder rutin")
            return
        for rid, user_id, channel_id, teks in rutin:
            try:
                await self._kirim_rutin(rid, user_id, channel_id, teks, now_dt)
            except Exception:
                log.exception("Gagal kirim reminder rutin %s", rid)

    @cek_reminder.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()

    def _tandai(self, rid: int) -> None:
        with get_connection() as conn:
            conn.execute("UPDATE reminders SET done = 1 WHERE id = ?", (rid,))
            conn.commit()

    async def _kirim(self, rid: int, user_id: int, channel_id: int, pesan: str) -> None:
        self._tandai(rid)  # tandai dulu biar tidak double-kirim kalau error
        teks = f"⏰ **Pengingat!**\n{pesan}"
        terkirim = False
        user = self.bot.get_user(user_id)
        if user is None:
            # Fallback: user tidak di cache → fetch dari API (jangan langsung
            # jatuh ke mention channel publik untuk pengingat privat)
            try:
                user = await self.bot.fetch_user(user_id)
            except (discord.NotFound, discord.HTTPException):
                user = None
        if user is not None:
            try:
                await user.send(teks)
                terkirim = True
            except (discord.Forbidden, discord.HTTPException):
                pass
        if not terkirim:
            channel = self.bot.get_channel(channel_id)
            if channel is not None:
                try:
                    # Fallback: mention user di channel asal. AllowedMentions
                    # eksplisit karena bot memakai deny-by-default — tanpa ini
                    # teks <@id> tidak benar-benar nge-ping.
                    # Dibatasi HANYA ke pemilik reminder: isi pesan ditulis
                    # user, jadi users=True polos bisa disalahgunakan untuk
                    # nge-ping orang lain lewat reminder.
                    await channel.send(
                        f"<@{user_id}> {teks}",
                        allowed_mentions=discord.AllowedMentions(
                            users=[discord.Object(id=user_id)]
                        ),
                    )
                except discord.HTTPException:
                    pass

    def _catat_gagal_rutin(self, rid: int) -> bool:
        """Hitung kegagalan beruntun; True bila sudah waktunya rutin dihapus."""
        # ~10 jam gagal terus → channel pasti sudah dihapus permanen
        return catat_gagal_rutin(self._rutin_gagal, rid)

    async def _kirim_rutin(
        self, rid: int, user_id: int, channel_id: int, teks: str, now_dt
    ) -> None:
        """Kirim pengingat rutin ke channel asal + update `terakhir` (hanya jika terkirim)."""
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            if self._catat_gagal_rutin(rid):
                with get_connection() as conn:
                    conn.execute("DELETE FROM reminder_rutin WHERE id = ?", (rid,))
                    conn.commit()
                self._rutin_gagal.pop(rid, None)
                log.warning(
                    "Reminder rutin #%s: channel %s hilang permanen — rutin dihapus.", rid, channel_id
                )
            return  # jangan update `terakhir` → retry interval berikut
        try:
            # Mention dibatasi HANYA ke pemilik rutin: teks ditulis user,
            # users=True polos bisa disalahgunakan untuk nge-ping orang lain.
            await channel.send(
                f"🔁 <@{user_id}> **Pengingat rutin:**\n{teks}",
                allowed_mentions=discord.AllowedMentions(
                    users=[discord.Object(id=user_id)]
                ),
            )
        except discord.HTTPException:
            if self._catat_gagal_rutin(rid):
                with get_connection() as conn:
                    conn.execute("DELETE FROM reminder_rutin WHERE id = ?", (rid,))
                    conn.commit()
                self._rutin_gagal.pop(rid, None)
                log.warning("Reminder rutin #%s: gagal kirim terus — rutin dihapus.", rid)
            return  # jangan update `terakhir` → retry interval berikut
        self._rutin_gagal.pop(rid, None)
        with get_connection() as conn:
            conn.execute(
                "UPDATE reminder_rutin SET terakhir = ? WHERE id = ?",
                (now_dt.isoformat(), rid),
            )
            conn.commit()

    @commands.hybrid_command(name="remind", description="Pasang pengingat")
    @discord.app_commands.describe(
        durasi="Contoh: 10m, 2h, 1d",
        pesan="Isi pengingat",
    )
    async def remind(self, ctx: commands.Context, durasi: str, *, pesan: str):
        """Pasang pengingat: !remind 10m cek oven / /remind"""
        detik = parse_durasi(durasi)
        if detik is None or detik < 10 or detik > MAKS_DETIK:
            await ctx.send(
                "❌ Format durasi salah. Contoh: `10m`, `2h`, `1d` (10 detik – 30 hari).",
                ephemeral=True,
            )
            return
        if len(pesan) > 1500:
            # Pesan >2000 karakter pasti gagal terkirim tapi reminder sudah
            # ditandai done → hilang permanen. Validasi di awal.
            await ctx.send("❌ Pesan pengingat maksimal 1500 karakter.", ephemeral=True)
            return
        at = discord.utils.utcnow() + datetime.timedelta(seconds=detik)
        with get_connection() as conn:
            cur = conn.execute(
                "INSERT INTO reminders (user_id, guild_id, channel_id, message, remind_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    ctx.author.id,
                    ctx.guild.id if ctx.guild else 0,
                    ctx.channel.id,
                    pesan,
                    at.isoformat(),
                ),
            )
            conn.commit()
            rid = cur.lastrowid
        await ctx.send(
            f"⏰ Siap! Aku ingetin <t:{int(at.timestamp())}:R>.\n"
            f"ID: `{rid}` — batal via `/remind-batal {rid}`",
            ephemeral=True,
        )

    @commands.hybrid_command(name="remind-list", description="Lihat pengingat aktif")
    async def remind_list(self, ctx: commands.Context):
        """Lihat pengingat: !remind-list / /remind-list"""
        now = discord.utils.utcnow().isoformat()
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT id, message, remind_at FROM reminders "
                "WHERE user_id = ? AND done = 0 AND remind_at > ? ORDER BY remind_at",
                (ctx.author.id, now),
            ).fetchall()
        if not rows:
            await ctx.send("📭 Tidak ada pengingat aktif.", ephemeral=True)
            return
        desc = "\n".join(
            f"`{rid}` • <t:{int(datetime.datetime.fromisoformat(ra).timestamp())}:R> — {pesan[:60]}"
            for rid, pesan, ra in rows
        )
        await ctx.send(embed=base_embed("⏰ Pengingat Aktif", desc), ephemeral=True)

    @commands.hybrid_command(name="remind-batal", description="Batalkan pengingat")
    @discord.app_commands.describe(id="ID pengingat (lihat /remind-list)")
    async def remind_batal(self, ctx: commands.Context, id: int):
        """Batalkan pengingat: !remind-batal 3 / /remind-batal"""
        with get_connection() as conn:
            cur = conn.execute(
                "UPDATE reminders SET done = 1 WHERE id = ? AND user_id = ? AND done = 0",
                (id, ctx.author.id),
            )
            conn.commit()
            kena = cur.rowcount
        await ctx.send(
            "✅ Pengingat dibatalkan." if kena else "❌ ID tidak ketemu / bukan milikmu.",
            ephemeral=True,
        )

    @commands.hybrid_command(
        name="remind-rutin", description="Pengingat yang berulang otomatis"
    )
    @discord.app_commands.describe(
        interval="Contoh: 1h, 12h, 1d (minimal 1 jam)",
        teks="Isi pengingat",
    )
    async def remind_rutin(self, ctx: commands.Context, interval: str, *, teks: str):
        """Pengingat rutin: /remind-rutin 1d minum obat"""
        detik = parse_durasi(interval)
        if detik is None or detik < 3600:
            await ctx.send(
                "❌ Format interval salah. Contoh: `1h`, `12h`, `1d` (minimal 1 jam).",
                ephemeral=True,
            )
            return
        teks = teks.strip()
        if not teks:
            await ctx.send("❌ Teks pengingat tidak boleh kosong.", ephemeral=True)
            return
        if len(teks) > 1500:
            await ctx.send("❌ Teks pengingat maksimal 1500 karakter.", ephemeral=True)
            return
        now_iso = discord.utils.utcnow().isoformat()
        with get_connection() as conn:
            cur = conn.execute(
                "INSERT INTO reminder_rutin (guild_id, channel_id, user_id, interval_detik, teks, terakhir) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    ctx.guild.id if ctx.guild else 0,
                    ctx.channel.id,
                    ctx.author.id,
                    detik,
                    teks,
                    now_iso,
                ),
            )
            conn.commit()
            rid = cur.lastrowid
        await ctx.send(
            f"🔁 Siap! Pengingat rutin tiap **{interval}**.\n"
            f"ID: `{rid}` — hapus via `/remind-rutin-hapus {rid}`",
            ephemeral=True,
        )

    @commands.hybrid_command(
        name="remind-rutin-list", description="Lihat pengingat rutinmu"
    )
    async def remind_rutin_list(self, ctx: commands.Context):
        """Lihat pengingat rutin: /remind-rutin-list"""
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT id, interval_detik, teks FROM reminder_rutin "
                "WHERE user_id = ? AND guild_id = ? ORDER BY id",
                (ctx.author.id, ctx.guild.id if ctx.guild else 0),
            ).fetchall()
        if not rows:
            await ctx.send("📭 Tidak ada pengingat rutin.", ephemeral=True)
            return
        desc = "\n".join(
            f"`{rid}` • tiap **{_format_interval(d)}** — {teks[:60]}"
            for rid, d, teks in rows
        )
        await ctx.send(embed=base_embed("🔁 Pengingat Rutin", desc), ephemeral=True)

    @commands.hybrid_command(
        name="remind-rutin-hapus", description="Hapus pengingat rutin"
    )
    @discord.app_commands.describe(id="ID (lihat /remind-rutin-list)")
    async def remind_rutin_hapus(self, ctx: commands.Context, id: int):
        """Hapus pengingat rutin: /remind-rutin-hapus 2"""
        with get_connection() as conn:
            cur = conn.execute(
                "DELETE FROM reminder_rutin WHERE id = ? AND user_id = ?",
                (id, ctx.author.id),
            )
            conn.commit()
            kena = cur.rowcount
        await ctx.send(
            "✅ Pengingat rutin dihapus." if kena else "❌ ID tidak ketemu / bukan milikmu.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Reminders(bot))
