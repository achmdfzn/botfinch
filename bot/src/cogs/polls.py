"""Polling — voting pakai tombol.

`/poll "mabar jam berapa?" "19.00, 20.00, 21.00" 1h` → tombol per opsi,
hasil real-time di embed, 1 suara per orang (bisa ganti pilihan),
tutup otomatis saat durasi habis atau manual via tombol (host/mod).
Data di SQLite sehingga survive restart.
"""
import datetime
import json
import logging

import discord
from discord.ext import commands, tasks

from src.bot import MENTIONS_PENGUMUMAN
from src.store import get_connection
from src.utils.embeds import base_embed, get_progress_bar
from src.utils.filters import parse_durasi
from src.utils.rutin import catat_gagal_rutin

log = logging.getLogger("finch")

MAX_OPSI = 5

POLL_COOLDOWN_DETIK = 60


def _klaim_cooldown_poll(conn, guild_id: int, user_id: int) -> float:
    """Klaim cooldown /poll atomik. Return 0 bila boleh, sisa detik bila tidak.

    Pola UPSERT yang sama seperti sosial._cooldown_klaim (duplikasi lokal yang
    disengaja — import antar-cog dilarang ARCHITECTURE.md).
    """
    sekarang = discord.utils.utcnow().isoformat()
    cur = conn.execute(
        "INSERT INTO cooldown_aksi (user_id, guild_id, aksi, terakhir) VALUES (?, ?, 'poll', ?) "
        "ON CONFLICT(user_id, guild_id, aksi) DO UPDATE SET terakhir = excluded.terakhir "
        "WHERE (strftime('%s', 'now') - strftime('%s', terakhir)) >= ?",
        (user_id, guild_id, sekarang, POLL_COOLDOWN_DETIK),
    )
    conn.commit()
    if cur.rowcount == 1:
        return 0
    row = conn.execute(
        "SELECT terakhir FROM cooldown_aksi WHERE user_id = ? AND guild_id = ? AND aksi = 'poll'",
        (user_id, guild_id),
    ).fetchone()
    if not row:
        return 0
    try:
        dt = datetime.datetime.fromisoformat(row[0])
    except ValueError:
        return 0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    sisa = (dt + datetime.timedelta(seconds=POLL_COOLDOWN_DETIK) - discord.utils.utcnow()).total_seconds()
    return max(0, sisa)


def parse_opsi(teks: str) -> list[str]:
    """'a, b, c' -> ['a', 'b', 'c']. Pure function — gampang dites."""
    return [o.strip() for o in (teks or "").split(",") if o.strip()]


# Batas panjang agar embed poll tidak menabrak limit Discord
# (deskripsi 4096, nama field 256) — input lebih panjang = API 400.
MAKS_PERTANYAAN = 500
MAKS_OPSI_TEKS = 100


def validasi_teks_poll(pertanyaan: str, options: list[str]) -> str | None:
    """Return pesan error bila teks poll kepanjangan, None bila aman.

    Pure function — gampang dites.
    """
    if len((pertanyaan or "").strip()) > MAKS_PERTANYAAN:
        return f"❌ Pertanyaan kepanjangan (maks {MAKS_PERTANYAAN} karakter)."
    for opt in options:
        if len(opt) > MAKS_OPSI_TEKS:
            return f"❌ Opsi kepanjangan (maks {MAKS_OPSI_TEKS} karakter per opsi)."
    return None


def simpan_poll_db(
    message_id: int,
    channel_id: int,
    guild_id: int,
    host_id: int,
    pertanyaan: str,
    options: list[str],
    ends_at: str | None,
) -> None:
    """Simpan metadata poll ke DB. Dipakai /poll & /poll-rutin."""
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO polls (message_id, channel_id, guild_id, host_id, question, options, ends_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                message_id,
                channel_id,
                guild_id,
                host_id,
                pertanyaan,
                json.dumps(options),
                ends_at,
            ),
        )
        conn.commit()


def ambil_poll_rutin_jatuh_tempo(conn, now: datetime.datetime):
    """Poll rutin yang intervalnya sudah lewat. Return list row penuh.

    Pure-ish — gampang dites.
    """
    out = []
    for row in conn.execute(
        "SELECT id, guild_id, channel_id, interval_detik, pertanyaan, opsi, terakhir "
        "FROM poll_rutin"
    ).fetchall():
        _rid, _gid, _cid, interval_detik, _tanya, _opsi, terakhir = row
        if not terakhir:
            out.append(row)
            continue
        try:
            last = datetime.datetime.fromisoformat(terakhir)
        except ValueError:
            out.append(row)
            continue
        if last.tzinfo is None:
            last = last.replace(tzinfo=datetime.timezone.utc)
        if (now - last).total_seconds() >= interval_detik:
            out.append(row)
    return out


def hitung_suara(conn, message_id: int, n_opsi: int) -> list[int]:
    """Jumlah suara per opsi (index 0..n-1)."""
    counts = [0] * n_opsi
    for idx, c in conn.execute(
        "SELECT option_idx, COUNT(*) FROM poll_votes WHERE message_id = ? GROUP BY option_idx",
        (message_id,),
    ):
        if 0 <= idx < n_opsi:
            counts[idx] = c
    return counts


def embed_poll(
    question: str,
    options: list[str],
    counts: list[int],
    ends_ts: int | None = None,
    ended: bool = False,
) -> discord.Embed:
    total = sum(counts)
    judul = "📊 POLL DITUTUP" if ended else "📊 Poll"
    embed = base_embed(judul, f"**{question}**\n\nTotal suara: **{total}**")
    for i, opt in enumerate(options):
        c = counts[i] if i < len(counts) else 0
        bar = get_progress_bar(c, max(total, 1), length=8)
        embed.add_field(
            name=f"{i + 1}. {opt}",
            value=f"`{bar}` **{c}** suara",
            inline=False,
        )
    if ended:
        embed.set_footer(text="Finch")
    elif ends_ts:
        embed.set_footer(text="Finch")
        embed.description += f"\n\nBerakhir <t:{ends_ts}:R>"
    else:
        embed.set_footer(text="Finch")
    return embed


async def _vote(interaction: discord.Interaction, idx: int) -> None:
    if interaction.user.bot:
        await interaction.response.send_message("❌ Bot tidak boleh pakai tombol ini.", ephemeral=True)
        return
    mid = interaction.message.id
    uid = interaction.user.id
    with get_connection() as conn:
        poll = conn.execute(
            "SELECT question, options, ends_at, ended FROM polls WHERE message_id = ?",
            (mid,),
        ).fetchone()
        if poll is None or poll[3]:
            await interaction.response.send_message(
                "❌ Poll sudah ditutup.", ephemeral=True
            )
            return
        question, options_json, ends_at, _ = poll
        options = json.loads(options_json)
        if not 0 <= idx < len(options):
            await interaction.response.send_message(
                "❌ Opsi tidak valid.", ephemeral=True
            )
            return
        conn.execute(
            "INSERT INTO poll_votes (message_id, user_id, option_idx) VALUES (?, ?, ?) "
            "ON CONFLICT(message_id, user_id) DO UPDATE SET option_idx=excluded.option_idx",
            (mid, uid, idx),
        )
        conn.commit()
        counts = hitung_suara(conn, mid, len(options))
    ends_ts = None
    if ends_at:
        try:
            ends_ts = int(datetime.datetime.fromisoformat(ends_at).timestamp())
        except ValueError:
            pass
    try:
        await interaction.message.edit(
            embed=embed_poll(question, options, counts, ends_ts)
        )
    except discord.HTTPException:
        pass
    await interaction.response.send_message(
        f"✅ Suaramu: **{options[idx]}**", ephemeral=True
    )


async def _tutup_dan_render(
    bot: commands.Bot, message_id: int, channel_id: int
) -> None:
    """Tutup poll: render hasil akhir + tandai ended. Dipakai tombol & task."""
    with get_connection() as conn:
        poll = conn.execute(
            "SELECT question, options FROM polls WHERE message_id = ? AND ended = 0",
            (message_id,),
        ).fetchone()
        if poll is None:
            return
        question, options_json = poll
        options = json.loads(options_json)
        counts = hitung_suara(conn, message_id, len(options))
        conn.execute("UPDATE polls SET ended = 1 WHERE message_id = ?", (message_id,))
        conn.commit()
    channel = bot.get_channel(channel_id)
    if channel is None:
        return
    try:
        msg = await channel.fetch_message(message_id)
        await msg.edit(embed=embed_poll(question, options, counts, ended=True), view=None)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        pass


class PollView(discord.ui.View):
    """Persistent — tombol vote (custom_id statis) + tombol tutup."""

    def __init__(self, options: list[str] | None = None):
        super().__init__(timeout=None)
        labels = options or [f"Opsi {i + 1}" for i in range(MAX_OPSI)]
        for i, label in enumerate(labels[:MAX_OPSI]):
            btn = discord.ui.Button(
                label=label[:80],
                style=discord.ButtonStyle.secondary,
                custom_id=f"finch:poll-vote:{i}",
            )

            async def vote_cb(interaction: discord.Interaction, idx=i):
                await _vote(interaction, idx)

            btn.callback = vote_cb
            self.add_item(btn)
        tutup = discord.ui.Button(
            label="Tutup",
            style=discord.ButtonStyle.danger,
            custom_id="finch:poll-close",
        )
        tutup.callback = self._tutup_cb
        self.add_item(tutup)

    async def _tutup_cb(self, interaction: discord.Interaction):
        mid = interaction.message.id
        member = interaction.user
        with get_connection() as conn:
            row = conn.execute(
                "SELECT host_id, channel_id FROM polls WHERE message_id = ? AND ended = 0",
                (mid,),
            ).fetchone()
        if row is None:
            await interaction.response.send_message(
                "❌ Poll sudah ditutup.", ephemeral=True
            )
            return
        host_id, channel_id = row
        boleh = isinstance(member, discord.Member) and (
            member.id == host_id or member.guild_permissions.manage_messages
        )
        if not boleh:
            await interaction.response.send_message(
                "❌ Hanya pembuat poll / moderator yang bisa menutup.", ephemeral=True
            )
            return
        await _tutup_dan_render(interaction.client, mid, channel_id)
        await interaction.response.send_message("🔒 Poll ditutup.", ephemeral=True)


class Polls(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Hitung kegagalan beruntun per poll rutin (channel dihapus → jangan retry selamanya)
        self._rutin_gagal: dict[int, int] = {}
        self.cek_poll.start()

    def cog_unload(self):
        self.cek_poll.cancel()

    def _catat_gagal_rutin(self, rid: int) -> bool:
        """Hitung kegagalan beruntun; True bila sudah waktunya rutin dihapus."""
        return catat_gagal_rutin(self._rutin_gagal, rid)

    @tasks.loop(seconds=30)
    async def cek_poll(self):
        try:
            now = discord.utils.utcnow().isoformat()
            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT message_id, channel_id FROM polls "
                    "WHERE ended = 0 AND ends_at IS NOT NULL AND ends_at <= ?",
                    (now,),
                ).fetchall()
        except Exception:
            # Satu DB error tidak boleh membunuh loop 30-detik selamanya
            log.exception("Gagal baca polls")
            return
        for message_id, channel_id in rows:
            try:
                await _tutup_dan_render(self.bot, message_id, channel_id)
            except Exception:
                log.exception("Gagal menutup poll %s", message_id)
        # poll rutin: yang jatuh tempo → posting poll baru
        try:
            now_dt = discord.utils.utcnow()
            with get_connection() as conn:
                rutin = ambil_poll_rutin_jatuh_tempo(conn, now_dt)
        except Exception:
            log.exception("Gagal baca poll rutin")
            return
        for rid, gid, cid, _interval, pertanyaan, opsi_json, _terakhir in rutin:
            try:
                await self._posting_poll_rutin(rid, gid, cid, pertanyaan, opsi_json, now_dt)
            except Exception:
                log.exception("Gagal posting poll rutin %s", rid)

    async def _posting_poll_rutin(
        self, rid: int, gid: int, cid: int, pertanyaan: str, opsi_json: str, now_dt
    ) -> None:
        options = json.loads(opsi_json)
        if not 2 <= len(options) <= MAX_OPSI:
            log.warning("Poll rutin %s opsi tidak valid, dilewati.", rid)
            return
        channel = self.bot.get_channel(cid)
        if channel is None:
            # Channel dihapus permanen → jangan retry tiap 30 detik selamanya
            if self._catat_gagal_rutin(rid):
                with get_connection() as conn:
                    conn.execute("DELETE FROM poll_rutin WHERE id = ?", (rid,))
                    conn.commit()
                self._rutin_gagal.pop(rid, None)
                log.warning("Poll rutin #%s: channel %s hilang permanen — rutin dihapus.", rid, cid)
            return
        try:
            # Poll rutin dibuat mod -> boleh @everyone.
            msg = await channel.send(
                embed=embed_poll(
                    pertanyaan, options, [0] * len(options),
                ),
                view=PollView(options),
                allowed_mentions=MENTIONS_PENGUMUMAN,
            )
        except discord.HTTPException:
            log.warning("Gagal posting poll rutin %s (cek permission).", rid)
            return
        host_id = self.bot.user.id if self.bot.user else 0
        simpan_poll_db(msg.id, cid, gid, host_id, pertanyaan, options, None)
        self._rutin_gagal.pop(rid, None)
        with get_connection() as conn:
            conn.execute(
                "UPDATE poll_rutin SET terakhir = ? WHERE id = ?",
                (now_dt.isoformat(), rid),
            )
            conn.commit()

    @cek_poll.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()

    @commands.hybrid_command(name="poll", description="Buat voting")
    @discord.app_commands.describe(
        pertanyaan="Pertanyaan polling",
        opsi="Pilihan dipisah koma, 2-5 opsi. Contoh: 19.00, 20.00, 21.00",
        durasi="Opsional, contoh: 10m, 1h, 1d (min 30 detik)",
    )
    async def poll(
        self,
        ctx: commands.Context,
        pertanyaan: str,
        opsi: str,
        durasi: str | None = None,
    ):
        """Buat polling: !poll "mabar jam?" "19.00, 20.00" 1h / /poll"""
        options = parse_opsi(opsi)
        if not 2 <= len(options) <= MAX_OPSI:
            await ctx.send(
                f"❌ Opsi harus 2-{MAX_OPSI}, pisahkan dengan koma.\n"
                'Contoh: `!poll "mabar jam berapa?" "19.00, 20.00, 21.00" 1h`',
                ephemeral=True,
            )
            return
        if not (pertanyaan or "").strip():
            await ctx.send("❌ Pertanyaan tidak boleh kosong.", ephemeral=True)
            return
        err_teks = validasi_teks_poll(pertanyaan, options)
        if err_teks:
            await ctx.send(err_teks, ephemeral=True)
            return
        # Cooldown anti-spam poll (atomik, persisten di DB).
        if ctx.guild is not None:
            with get_connection() as conn:
                sisa = _klaim_cooldown_poll(conn, ctx.guild.id, ctx.author.id)
            if sisa > 0:
                await ctx.send(
                    f"❌ Tunggu **{sisa:.0f}** detik sebelum membuat poll lagi.",
                    ephemeral=True,
                )
                return
        ends_at = None
        ends_ts = None
        if durasi:
            MAKS_DETIK = 30 * 86400
            detik = parse_durasi(durasi)
            if detik is None or detik < 30:
                await ctx.send(
                    "❌ Format durasi salah. Contoh: `10m`, `1h`, `1d` (minimal 30 detik).",
                    ephemeral=True,
                )
                return
            if detik > MAKS_DETIK:
                await ctx.send("❌ Durasi maksimal 30 hari.", ephemeral=True)
                return
            ends = discord.utils.utcnow() + datetime.timedelta(seconds=detik)
            ends_at = ends.isoformat()
            ends_ts = int(ends.timestamp())

        msg = await ctx.send(
            embed=embed_poll(pertanyaan, options, [0] * len(options), ends_ts),
            view=PollView(options),
            # Poll dibuat user biasa: matikan semua mention agar pertanyaan/
            # opsi tidak bisa dipakai untuk nge-ping orang lain.
            allowed_mentions=discord.AllowedMentions.none(),
        )
        if msg is None and ctx.interaction:
            try:
                msg = await ctx.interaction.original_response()
            except discord.HTTPException:
                msg = None
        if msg is None:
            return
        simpan_poll_db(
            msg.id,
            msg.channel.id,
            ctx.guild.id if ctx.guild else 0,
            ctx.author.id,
            pertanyaan,
            options,
            ends_at,
        )


    @commands.hybrid_command(
        name="poll-rutin", description="Poll yang terbit otomatis berulang (mod)"
    )
    @commands.has_permissions(manage_messages=True)
    @discord.app_commands.describe(
        interval="Contoh: 1h, 12h, 7d (minimal 1 jam)",
        pertanyaan="Pertanyaan polling",
        opsi="Pilihan dipisah koma, 2-5 opsi",
    )
    async def poll_rutin(
        self, ctx: commands.Context, interval: str, pertanyaan: str, *, opsi: str
    ):
        """Poll rutin: /poll-rutin 7d "mabar kapan?" "sabtu, minggu" """
        if ctx.guild is None:
            await ctx.send("❌ Hanya bisa di server.", ephemeral=True)
            return
        detik = parse_durasi(interval)
        if detik is None or detik < 3600:
            await ctx.send(
                "❌ Format interval salah. Contoh: `1h`, `12h`, `7d` (minimal 1 jam).",
                ephemeral=True,
            )
            return
        options = parse_opsi(opsi)
        if not 2 <= len(options) <= MAX_OPSI:
            await ctx.send(
                f"❌ Opsi harus 2-{MAX_OPSI}, pisahkan dengan koma.",
                ephemeral=True,
            )
            return
        err_teks = validasi_teks_poll(pertanyaan, options)
        if err_teks:
            await ctx.send(err_teks, ephemeral=True)
            return
        now_iso = discord.utils.utcnow().isoformat()
        with get_connection() as conn:
            cur = conn.execute(
                "INSERT INTO poll_rutin (guild_id, channel_id, interval_detik, pertanyaan, opsi, terakhir) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    ctx.guild.id,
                    ctx.channel.id,
                    detik,
                    pertanyaan.strip(),
                    json.dumps(options),
                    now_iso,
                ),
            )
            conn.commit()
            rid = cur.lastrowid
        await ctx.send(
            f"📊 Siap! Poll rutin tiap **{interval}** di channel ini.\n"
            f"ID: `{rid}` — hapus via `/poll-rutin-hapus {rid}`",
            ephemeral=True,
        )

    @commands.hybrid_command(
        name="poll-rutin-list", description="Lihat daftar poll rutin (mod)"
    )
    @commands.has_permissions(manage_messages=True)
    async def poll_rutin_list(self, ctx: commands.Context):
        """Lihat poll rutin: /poll-rutin-list"""
        gid = ctx.guild.id if ctx.guild else 0
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT id, channel_id, interval_detik, pertanyaan FROM poll_rutin "
                "WHERE guild_id = ? ORDER BY id",
                (gid,),
            ).fetchall()
        if not rows:
            await ctx.send("📭 Tidak ada poll rutin.", ephemeral=True)
            return
        desc = "\n".join(
            f"`{rid}` • tiap **{_interval_human(d)}** • <#{cid}>\n  _{tanya[:80]}_"
            for rid, cid, d, tanya in rows
        )
        await ctx.send(embed=base_embed("📊 Poll Rutin", desc), ephemeral=True)

    @commands.hybrid_command(
        name="poll-rutin-hapus", description="Hapus poll rutin (mod)"
    )
    @commands.has_permissions(manage_messages=True)
    @discord.app_commands.describe(id="ID (lihat /poll-rutin-list)")
    async def poll_rutin_hapus(self, ctx: commands.Context, id: int):
        """Hapus poll rutin: /poll-rutin-hapus 2"""
        gid = ctx.guild.id if ctx.guild else 0
        with get_connection() as conn:
            cur = conn.execute(
                "DELETE FROM poll_rutin WHERE id = ? AND guild_id = ?", (id, gid)
            )
            conn.commit()
            kena = cur.rowcount
        await ctx.send(
            "✅ Poll rutin dihapus." if kena else "❌ ID tidak ketemu.",
            ephemeral=True,
        )


def _interval_human(detik: int) -> str:
    """3600 -> '1 jam', 604800 -> '7 hari'. Pure — gampang dites."""
    detik = int(detik)
    hari, sisa = divmod(detik, 86400)
    jam, _ = divmod(sisa, 3600)
    if hari and jam:
        return f"{hari} hari {jam} jam"
    if hari:
        return f"{hari} hari"
    return f"{jam} jam"


async def setup(bot: commands.Bot):
    await bot.add_cog(Polls(bot))
    bot.add_view(PollView())
