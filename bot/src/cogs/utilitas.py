"""Utilitas Tahap 12 — dashboard web, backup DB, grafik, embed builder, event rutin.

- Dashboard: server aiohttp di DASHBOARD_HOST:DASHBOARD_PORT (background, non-blokir)
- Backup DB harian ke BACKUP_CHANNEL_ID
- /grafik level, /grafik voice — visual distribusi ala bot keren
- /embed-buat (mod) — modal pembuat embed pengumuman
- /rutin buat, /rutin list, /rutin hapus + loop tiap 5 menit
"""
import asyncio
import datetime
import html
import logging
import os
import re
import shutil

import discord
from discord.ext import commands, tasks

from src import config
from src.bot import MENTIONS_PENGUMUMAN
from src.store import DB_PATH, get_connection
from src.utils.embeds import error_embed, finch_embed, get_progress_bar, sukses_embed
from src.utils.filters import parse_durasi
from src.utils.teks import nama_member_atau_id

log = logging.getLogger("finch")

WARNA_MAP = {
    "biru": discord.Color.blue(),
    "hijau": discord.Color.green(),
    "merah": discord.Color.red(),
    "emas": discord.Color.gold(),
    "ungu": discord.Color.purple(),
}


# ---------- fungsi murni (gampang dites) ----------

def _fmt_interval(detik: int) -> str:
    """604800 -> '7 hari'. Pure function."""
    if detik % 86400 == 0:
        n = detik // 86400
        return f"{n} hari"
    if detik % 3600 == 0:
        n = detik // 3600
        return f"{n} jam"
    if detik % 60 == 0:
        n = detik // 60
        return f"{n} menit"
    return f"{detik} detik"


def _bucket_distribusi(levels: list[int]) -> list[tuple[str, int]]:
    """Kelompokkan level ke 10 rentang (1-5, 6-10, ...). Pure function."""
    hasil = []
    for i in range(10):
        lo, hi = i * 5 + 1, (i + 1) * 5
        jumlah = sum(1 for lv in levels if lo <= lv <= hi)
        hasil.append((f"Lv {lo}–{hi}", jumlah))
    return hasil


def _jatuh_tempo(terakhir: str | None, interval: int, now: datetime.datetime) -> bool:
    """True kalau event rutin sudah waktunya jalan lagi. Pure function."""
    if not terakhir:
        return True
    try:
        last = datetime.datetime.fromisoformat(terakhir)
        if last.tzinfo is None:
            last = last.replace(tzinfo=datetime.timezone.utc)
        return (now - last).total_seconds() >= interval
    except ValueError:
        return True


def _render_dashboard_html(
    nama_bot: str,
    guilds: list[tuple[str, int]],
    top_level: list[tuple[int, int, int]],
    top_koin: list[tuple[int, int]],
) -> str:
    """Render halaman dashboard. Pure function — HTML inline string."""
    total_member = sum(m for _, m in guilds)
    baris_guild = "".join(
        f"<li>{html.escape(nama)} — {member} member</li>" for nama, member in guilds
    ) or "<li>(belum ada guild)</li>"
    baris_level = "".join(
        f"<li>#{i + 1} <code>{uid}</code> — Level <b>{lv}</b> ({xp} XP)</li>"
        for i, (uid, lv, xp) in enumerate(top_level)
    ) or "<li>(belum ada data)</li>"
    baris_koin = "".join(
        f"<li>#{i + 1} <code>{uid}</code> — <b>{koin:,}</b> 🪙</li>"
        for i, (uid, koin) in enumerate(top_koin)
    ) or "<li>(belum ada data)</li>"
    return f"""<!doctype html>
<html lang="id"><head><meta charset="utf-8">
<title>{html.escape(nama_bot)} — Dashboard</title>
<style>body{{font-family:sans-serif;max-width:720px;margin:2em auto;padding:0 1em}}
h1{{color:#5865F2}}li{{margin:.25em 0}}</style>
</head><body>
<h1>🐦 {html.escape(nama_bot)} — Dashboard</h1>
<p><b>{len(guilds)}</b> guild · <b>{total_member}</b> total member</p>
<h2>Guild</h2><ul>{baris_guild}</ul>
<h2>🏆 Top 10 Level</h2><ol>{baris_level}</ol>
<h2>🪙 Top 10 Koin</h2><ol>{baris_koin}</ol>
<p><a href="/api/stats">API stats (JSON)</a></p>
</body></html>"""


# ---------- modal ----------

class EmbedBuatModal(discord.ui.Modal, title="Buat Embed Pengumuman"):
    judul = discord.ui.TextInput(label="Judul", max_length=256)
    deskripsi = discord.ui.TextInput(
        label="Deskripsi", style=discord.TextStyle.paragraph, required=False, max_length=2000
    )
    warna = discord.ui.TextInput(
        label="Warna (biru/hijau/merah/emas/ungu)", default="biru", max_length=10
    )
    channel = discord.ui.TextInput(
        label="Channel tujuan (#mention atau ID)", max_length=64
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        w = self.warna.value.strip().lower()
        color = WARNA_MAP.get(w)
        if color is None:
            await interaction.response.send_message(
                embed=error_embed(
                    f"Warna `{w}` tidak dikenal. Pilih: biru, hijau, merah, emas, ungu."
                ),
                ephemeral=True,
            )
            return
        m = re.search(r"(\d{15,25})", self.channel.value)
        ch = interaction.client.get_channel(int(m.group(1))) if m else None
        if ch is None or not isinstance(ch, discord.TextChannel):
            await interaction.response.send_message(
                embed=error_embed("Channel tidak ditemukan. Pakai #mention atau ID channel."),
                ephemeral=True,
            )
            return
        # Anti cross-guild: channel harus di server yang sama
        if ch.guild != interaction.guild:
            await interaction.response.send_message(
                embed=error_embed("Channel harus di server ini."),
                ephemeral=True,
            )
            return
        embed = finch_embed(
            self.judul.value.strip() or "📢 Pengumuman",
            self.deskripsi.value.strip(),
            warna="info",
        )
        embed.color = color
        try:
            # Embed ditulis mod -> boleh @everyone.
            await ch.send(embed=embed, allowed_mentions=MENTIONS_PENGUMUMAN)
        except (discord.Forbidden, discord.HTTPException):
            await interaction.response.send_message(
                embed=error_embed(f"Gagal kirim ke {ch.mention} (cek permission)."),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            embed=sukses_embed("Embed terkirim", f"Terkirim ke {ch.mention}."),
            ephemeral=True,
        )


# ---------- cog ----------

class Utilitas(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._dash_task: asyncio.Task | None = None

    async def cog_load(self) -> None:
        self.backup_harian.start()
        self.cek_event_rutin.start()
        self._dash_task = asyncio.create_task(self._jalankan_dashboard())

    def cog_unload(self) -> None:
        self.backup_harian.cancel()
        self.cek_event_rutin.cancel()
        if self._dash_task is not None:
            self._dash_task.cancel()

    # ----- dashboard -----
    async def _dash_index(self, request) -> "object":
        from aiohttp import web

        guilds = [(g.name, g.member_count or 0) for g in self.bot.guilds]
        # Top 10 agregat SEMUA guild (bot publik — jangan cuma guilds[0])
        top_level: list[tuple[int, int, int]] = []
        top_koin: list[tuple[int, int]] = []
        with get_connection() as conn:
            top_level = [
                (r[0], r[1], r[2])
                for r in conn.execute(
                    "SELECT user_id, level, xp FROM users"
                    " ORDER BY level DESC, xp DESC LIMIT 10"
                )
            ]
            top_koin = [
                (r[0], r[1])
                for r in conn.execute(
                    "SELECT user_id, balance FROM economy"
                    " ORDER BY balance DESC LIMIT 10"
                )
            ]
        nama = self.bot.user.name if self.bot.user else "Finch"
        return web.Response(
            text=_render_dashboard_html(nama, guilds, top_level, top_koin),
            content_type="text/html",
        )

    async def _dash_api(self, request) -> "object":
        from aiohttp import web

        return web.json_response(
            {
                "guilds": len(self.bot.guilds),
                "total_members": sum(g.member_count or 0 for g in self.bot.guilds),
                "total_commands": len(self.bot.commands)
                + len(list(self.bot.tree.get_commands())),
            }
        )

    async def _jalankan_dashboard(self) -> None:
        try:
            from aiohttp import web
        except ImportError:
            log.warning("aiohttp tidak terinstal — dashboard web nonaktif.")
            return
        app = web.Application()
        app.router.add_get("/", self._dash_index)
        app.router.add_get("/api/stats", self._dash_api)
        runner = web.AppRunner(app)
        host = config.settings.dashboard_host
        port = config.settings.dashboard_port
        try:
            await runner.setup()
            await web.TCPSite(runner, host, port).start()
            log.info("Dashboard Finch: http://%s:%s", host, port)
            await asyncio.Event().wait()  # jalan terus sampai unload
        except OSError as e:
            log.warning(
                "Dashboard gagal start di %s:%s (%s) — bot tetap jalan.", host, port, e
            )
        except asyncio.CancelledError:
            pass
        finally:
            await runner.cleanup()

    # ----- backup DB -----
    @tasks.loop(hours=24)
    async def backup_harian(self):
        ch_id = config.settings.backup_channel_id
        if not ch_id:
            return
        channel = self.bot.get_channel(ch_id)
        if channel is None or not isinstance(channel, discord.TextChannel):
            # Channel dihapus / ID menunjuk ke voice channel: kirim file ke
            # channel non-teks mustahil (AttributeError) dan dulu membunuh
            # loop harian. Fail-soft saja.
            log.warning("Backup DB: channel %s tidak ditemukan / bukan channel teks.", ch_id)
            return
        nama = datetime.datetime.now().strftime("finch-backup-%Y%m%d.db")
        path_tmp = f"/tmp/{nama}"
        try:
            shutil.copy2(DB_PATH, path_tmp)
        except OSError as e:
            log.warning("Backup DB gagal (copy): %s", e)
            return
        try:
            await channel.send(
                f"💾 Backup database harian — `{nama}`",
                file=discord.File(path_tmp, filename=nama),
            )
            log.info("Backup DB terkirim ke channel %s.", ch_id)
        except (discord.Forbidden, discord.HTTPException) as e:
            log.warning("Backup DB gagal terkirim: %s", e)
        finally:
            try:
                os.remove(path_tmp)
            except OSError:
                pass

    @backup_harian.before_loop
    async def _before_backup(self):
        await self.bot.wait_until_ready()

    # ----- grafik -----
    @commands.hybrid_group(name="grafik", description="📊 Grafik Finch")
    async def grafik(self, ctx: commands.Context):
        """Bantuan grup grafik."""
        await ctx.send(
            embed=finch_embed(
                "📊 Grafik",
                "`/grafik level` — distribusi level member\n`/grafik voice` — top 10 menit voice",
                warna="info",
            ),
            ephemeral=True,
        )
    @grafik.command(name="level", description="Distribusi level member server")
    async def grafik_level(self, ctx: commands.Context):
        """Lihat sebaran level: /grafik level"""
        if ctx.guild is None:
            await ctx.send(embed=error_embed("Hanya bisa dipakai di server."), ephemeral=True)
            return
        with get_connection() as conn:
            levels = [
                r[0]
                for r in conn.execute(
                    "SELECT level FROM users WHERE guild_id = ?", (ctx.guild.id,)
                )
            ]
        if not levels:
            await ctx.send(embed=error_embed("Belum ada data level."), ephemeral=True)
            return
        buckets = _bucket_distribusi(levels)
        maks = max(c for _, c in buckets) or 1
        embed = finch_embed(
            "📊 Distribusi Level",
            f"Total **{len(levels)}** member terdata",
            warna="info",
            thumbnail=ctx.guild.icon.url if ctx.guild.icon else None,
        )
        for label, jumlah in buckets:
            bar = get_progress_bar(jumlah, maks)
            embed.add_field(name=label, value=f"`{bar}` {jumlah}", inline=True)
        await ctx.send(embed=embed)

    @grafik.command(name="voice", description="Top 10 menit voice server")
    async def grafik_voice(self, ctx: commands.Context):
        """Lihat top voice: /grafik voice"""
        if ctx.guild is None:
            await ctx.send(embed=error_embed("Hanya bisa dipakai di server."), ephemeral=True)
            return
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT user_id, menit FROM voice_total WHERE guild_id = ?"
                " ORDER BY menit DESC LIMIT 10",
                (ctx.guild.id,),
            ).fetchall()
        if not rows:
            await ctx.send(embed=error_embed("Belum ada data voice."), ephemeral=True)
            return
        teratas = rows[0][1] or 1
        embed = finch_embed("🎙️ Top 10 Voice", "Menit terlama di voice channel", warna="info")
        for i, (uid, menit) in enumerate(rows):
            bar = get_progress_bar(menit, teratas)
            # Nama sebagai teks, BUKAN <@uid>: mention di field embed ikut
            # nge-ping (users=True) — /grafik voice tak perlu membangunkan
            # 10 orang setiap dijalankan.
            nama = nama_member_atau_id(ctx.guild, uid)
            embed.add_field(
                name=f"#{i + 1} · {nama}", value=f"`{bar}` {menit} mnt", inline=True
            )
        await ctx.send(embed=embed)

    # ----- embed builder -----
    @commands.hybrid_command(name="embed-buat", description="Buat embed pengumuman (khusus mod)")
    @commands.has_permissions(manage_messages=True)
    async def embed_buat(self, ctx: commands.Context):
        """Buka form embed: /embed-buat"""
        if ctx.guild is None:
            await ctx.send(embed=error_embed("Hanya bisa dipakai di server."), ephemeral=True)
            return
        from src.cogs.dashboard_sync import modul_aktif

        if not modul_aktif(ctx.guild.id, "embed_enabled"):
            await ctx.send(
                embed=error_embed("Modul embed dimatikan oleh admin server ini."),
                ephemeral=True,
            )
            return
        if ctx.interaction is None:
            await ctx.send(
                embed=error_embed("Perintah ini hanya bisa lewat slash command `/embed-buat`."),
                ephemeral=True,
            )
            return
        await ctx.interaction.response.send_modal(EmbedBuatModal())

    # ----- event rutin -----
    @commands.hybrid_group(name="rutin", description="🔁 Rutin Finch")
    async def rutin(self, ctx: commands.Context):
        """Bantuan grup rutin."""
        await ctx.send(
            embed=finch_embed(
                "🔁 Rutin",
                "`/rutin buat` — buat event rutin (mod)\n`/rutin list` — daftar event rutin\n`/rutin hapus` — hapus event rutin",
                warna="event",
            ),
            ephemeral=True,
        )
    @rutin.command(name="buat", description="Buat event berulang otomatis (khusus mod)")
    @discord.app_commands.describe(
        nama="Nama event",
        interval="Contoh: 1h, 1d, 7d (minimal 1 jam)",
        deskripsi="Deskripsi event (opsional)",
    )
    @commands.has_permissions(manage_messages=True)
    async def event_rutin_buat(
        self, ctx: commands.Context, nama: str, interval: str, deskripsi: str = ""
    ):
        """Buat event rutin: /rutin buat "Mabar Jumat" 7d"""
        if ctx.guild is None:
            await ctx.send(embed=error_embed("Hanya bisa dipakai di server."), ephemeral=True)
            return
        detik = parse_durasi(interval)
        if detik is None:
            await ctx.send(
                embed=error_embed("Format interval salah. Contoh: `1h`, `1d`, `7d`."),
                ephemeral=True,
            )
            return
        if detik < 3600:
            await ctx.send(
                embed=error_embed("Interval minimal 1 jam."), ephemeral=True
            )
            return
        # Batas panjang agar embed pengumuman tidak menabrak limit Discord
        # (judul 256, deskripsi 4096) — input lebih panjang = API 400.
        if len(nama.strip()) > 200:
            await ctx.send(
                embed=error_embed("Nama event kepanjangan (maks 200 karakter)."),
                ephemeral=True,
            )
            return
        if len(deskripsi.strip()) > 2000:
            await ctx.send(
                embed=error_embed("Deskripsi kepanjangan (maks 2000 karakter)."),
                ephemeral=True,
            )
            return
        with get_connection() as conn:
            cur = conn.execute(
                "INSERT INTO event_rutin (guild_id, channel_id, nama, deskripsi, interval_detik)"
                " VALUES (?, ?, ?, ?, ?)",
                (ctx.guild.id, ctx.channel.id, nama.strip(), deskripsi.strip(), detik),
            )
            conn.commit()
            rid = cur.lastrowid
        await ctx.send(
            embed=sukses_embed(
                "Event rutin dibuat",
                f"**#{rid} {nama.strip()}** — tiap {_fmt_interval(detik)} di {ctx.channel.mention}.",
            ),
            ephemeral=True,
        )
        log.info("Event rutin #%s dibuat: %s (%ds)", rid, nama, detik)

    @rutin.command(name="list", description="Lihat daftar event rutin (khusus mod)")
    @commands.has_permissions(manage_messages=True)
    async def event_rutin_list(self, ctx: commands.Context):
        """Lihat event rutin: /rutin list"""
        if ctx.guild is None:
            await ctx.send(embed=error_embed("Hanya bisa dipakai di server."), ephemeral=True)
            return
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT id, nama, interval_detik, terakhir FROM event_rutin WHERE guild_id = ?"
                " ORDER BY id",
                (ctx.guild.id,),
            ).fetchall()
        if not rows:
            await ctx.send(embed=error_embed("Belum ada event rutin."), ephemeral=True)
            return
        embed = finch_embed("🔁 Event Rutin", f"**{len(rows)}** event terdaftar", warna="info")
        for rid, nama, detik, terakhir in rows:
            embed.add_field(
                name=f"#{rid} · {nama}",
                value=f"Interval: {_fmt_interval(detik)}\nTerakhir: {terakhir or 'belum pernah'}",
                inline=True,
            )
        await ctx.send(embed=embed)

    @rutin.command(name="hapus", description="Hapus event rutin (khusus mod)")
    @discord.app_commands.describe(id="ID event (lihat /rutin list)")
    @commands.has_permissions(manage_messages=True)
    async def event_rutin_hapus(self, ctx: commands.Context, id: int):
        """Hapus event rutin: /rutin hapus <id>"""
        if ctx.guild is None:
            await ctx.send(embed=error_embed("Hanya bisa dipakai di server."), ephemeral=True)
            return
        with get_connection() as conn:
            cur = conn.execute(
                "DELETE FROM event_rutin WHERE id = ? AND guild_id = ?",
                (id, ctx.guild.id),
            )
            conn.commit()
        if cur.rowcount == 0:
            await ctx.send(embed=error_embed(f"Event rutin #{id} tidak ditemukan."), ephemeral=True)
            return
        await ctx.send(
            embed=sukses_embed("Event rutin dihapus", f"Event **#{id}** dihapus."),
            ephemeral=True,
        )

    @tasks.loop(minutes=5)
    async def cek_event_rutin(self):
        now = discord.utils.utcnow()
        try:
            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT id, guild_id, channel_id, nama, deskripsi, interval_detik, terakhir"
                    " FROM event_rutin"
                ).fetchall()
        except Exception:
            # Satu DB error tidak boleh membunuh loop 5-menit selamanya
            log.exception("Gagal baca event rutin")
            return
        for rid, gid, cid, nama, deskripsi, interval, terakhir in rows:
            try:
                await self._posting_event_rutin(now, rid, gid, cid, nama, deskripsi, interval, terakhir)
            except Exception:
                log.exception("Gagal proses event rutin #%s", rid)

    async def _posting_event_rutin(
        self, now, rid: int, gid: int, cid: int, nama: str, deskripsi: str,
        interval: int, terakhir: str | None,
    ) -> None:
        if not _jatuh_tempo(terakhir, interval, now):
            return
        channel = self.bot.get_channel(cid)
        if channel is None:
            log.warning("Event rutin #%s: channel %s hilang.", rid, cid)
            return
        if not isinstance(channel, discord.abc.Messageable):
            log.warning("Event rutin #%s: channel %s bukan channel teks.", rid, cid)
            return
        embed = finch_embed(f"🔁 {nama}", deskripsi or "Event rutin dimulai!", warna="event")
        try:
            # Event rutin dibuat mod -> boleh @everyone.
            msg = await channel.send(embed=embed, allowed_mentions=MENTIONS_PENGUMUMAN)
        except discord.HTTPException:
            log.warning("Event rutin #%s: gagal kirim pengumuman.", rid)
            return
        # Catat sebagai event (kolom ikuti events.py) + update terakhir — hanya jika sukses
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO events (guild_id, channel_id, message_id, nama, kapan, deskripsi)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (gid, cid, msg.id, nama, now.isoformat(), deskripsi or ""),
            )
            conn.execute(
                "UPDATE event_rutin SET terakhir = ? WHERE id = ?",
                (now.isoformat(), rid),
            )
            conn.commit()
        log.info("Event rutin #%s diposting: %s", rid, nama)

    @cek_event_rutin.before_loop
    async def _before_event_rutin(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Utilitas(bot))
