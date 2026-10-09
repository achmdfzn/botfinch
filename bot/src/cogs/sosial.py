"""Fitur sosial — job, nikah, confess, clan, gelar.

- `/job lihat`, `/job pilih` — class dengan bonus pasif (dipakai /kerja, XP chat, /game maling)
- `/nikah lamar`, `/nikah cerai`, `/nikah pasangan`, `/nikah klaim`
- `/confess` — pesan anonim ke channel khusus
- `/clan buat`, `/clan gabung`, `/clan keluar`, `/clan info`, `/clan war`
- `/gelar toko`, `/gelar beli`, `/gelar pasang`, `/gelar lepas`
- `/top-prestige` — leaderboard prestise
"""
import datetime
import logging

import discord
from discord.ext import commands, tasks

from src import config
from src.store import get_connection
from src.utils import economy as eko
from src.utils import filters
from src.utils import job as jobmod
from src.utils.embeds import error_embed, finch_embed, koin_text, sukses_embed
from src.utils.waktu import parse_iso

log = logging.getLogger("finch")

GELAR_TOKO = {
    "sultan": {"nama": "🌟 Sultan", "harga": 5000},
    "legenda": {"nama": "🔥 Legenda", "harga": 10000},
    "kraz": {"nama": "💎 Crazy Rich", "harga": 20000},
}


def _cooldown_sisa(conn, guild_id: int, user_id: int, aksi: str, cooldown_detik: int) -> float:
    """Sisa cooldown (detik) dari DB — persisten, anti bypass via restart."""
    row = conn.execute(
        "SELECT terakhir FROM cooldown_aksi WHERE user_id = ? AND guild_id = ? AND aksi = ?",
        (user_id, guild_id, aksi),
    ).fetchone()
    if not row:
        return 0
    dt = parse_iso(row[0])
    if dt is None:
        return 0
    sisa = (dt + datetime.timedelta(seconds=cooldown_detik) - discord.utils.utcnow()).total_seconds()
    return max(0, sisa)


def _cooldown_klaim(conn, guild_id: int, user_id: int, aksi: str, cooldown_detik: int) -> bool:
    """Klaim cooldown secara atomik. Return True bila klaim berhasil (cooldown tidak aktif).

    Pola check-then-act biasa (cek sisa -> kirim -> catat) bisa lolos ganda bila
    dua command dieksekusi nyaris bersamaan. Klaim ini menggabungkan cek+catat
    dalam satu statement UPSERT sehingga hanya satu pemanggil yang menang.
    """
    sekarang = discord.utils.utcnow().isoformat()
    cur = conn.execute(
        "INSERT INTO cooldown_aksi (user_id, guild_id, aksi, terakhir) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(user_id, guild_id, aksi) DO UPDATE SET terakhir = excluded.terakhir "
        "WHERE (strftime('%s', 'now') - strftime('%s', terakhir)) >= ?",
        (user_id, guild_id, aksi, sekarang, cooldown_detik),
    )
    conn.commit()
    return cur.rowcount == 1

CONFESS_COOLDOWN_DETIK = 5 * 60
NIKAH_CLAIM_COOLDOWN_DETIK = 20 * 3600


class LamaranView(discord.ui.View):
    """Tombol Terima/Tolak lamaran nikah (120 detik)."""

    def __init__(self, pelamar_id: int, target_id: int, guild_id: int):
        super().__init__(timeout=120)
        self.pelamar_id = pelamar_id
        self.target_id = target_id
        self.guild_id = guild_id

    async def _tutup(self, interaction: discord.Interaction, teks: str):
        for item in self.children:
            item.disabled = True
        try:
            await interaction.response.edit_message(content=teks, view=self, embed=None)
        except discord.HTTPException:
            pass
        self.stop()

    @discord.ui.button(label="Terima", style=discord.ButtonStyle.success)
    async def terima(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target_id:
            await interaction.response.send_message(
                "❌ Lamaran ini bukan untukmu.", ephemeral=True
            )
            return
        # Cek ulang: jangan sampai salah satu sudah menikah duluan (race)
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT user_id FROM nikah WHERE user_id IN (?, ?)",
                (self.pelamar_id, self.target_id),
            ).fetchall()
            if rows:
                await self._tutup(interaction, "❌ Lamaran kedaluwarsa — salah satu sudah menikah.")
                return
            sekarang = discord.utils.utcnow().isoformat()
            conn.execute(
                "INSERT INTO nikah (user_id, guild_id, pasangan_id, sejak) VALUES (?, ?, ?, ?)",
                (self.pelamar_id, self.guild_id, self.target_id, sekarang),
            )
            conn.execute(
                "INSERT INTO nikah (user_id, guild_id, pasangan_id, sejak) VALUES (?, ?, ?, ?)",
                (self.target_id, self.guild_id, self.pelamar_id, sekarang),
            )
            conn.commit()
            # Hidden achievement: sosialita
            try:
                from src.utils import achievement as ach
                ach.cek_buka(conn, self.guild_id, self.pelamar_id, {"sosialita": 1})
                ach.cek_buka(conn, self.guild_id, self.target_id, {"sosialita": 1})
            except Exception:
                pass
        await self._tutup(
            interaction,
            f"💒 <@{self.pelamar_id}> & <@{self.target_id}> resmi menikah! "
            "Jangan lupa `/nikah klaim` tiap hari buat bonus koin! 🎉",
        )

    @discord.ui.button(label="Tolak", style=discord.ButtonStyle.danger)
    async def tolak(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target_id:
            await interaction.response.send_message(
                "❌ Lamaran ini bukan untukmu.", ephemeral=True
            )
            return
        await self._tutup(interaction, "💔 Lamaran ditolak. Sabar ya, jodoh tak ke mana~")


class CeraiView(discord.ui.View):
    """Konfirmasi cerai (60 detik)."""

    def __init__(self, user_id: int, pasangan_id: int):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.pasangan_id = pasangan_id

    @discord.ui.button(label="Ya, cerai", style=discord.ButtonStyle.danger)
    async def ya(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "❌ Bukan keputusanmu.", ephemeral=True
            )
            return
        with get_connection() as conn:
            conn.execute(
                "DELETE FROM nikah WHERE user_id IN (?, ?)",
                (self.user_id, self.pasangan_id),
            )
            conn.commit()
        for item in self.children:
            item.disabled = True
        try:
            await interaction.response.edit_message(
                content="💔 Kalian resmi bercerai. Semoga dapat yang lebih baik!", view=self
            )
        except discord.HTTPException:
            pass
        self.stop()


def _sudah_menikah(conn, guild_id: int, user_id: int) -> int | None:
    row = conn.execute(
        "SELECT pasangan_id FROM nikah WHERE user_id = ? AND guild_id = ?",
        (user_id, guild_id),
    ).fetchone()
    return row[0] if row else None


class Sosial(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cek_war.start()
        self.cek_voice_roles.start()

    def cog_unload(self):
        self.cek_war.cancel()
        self.cek_voice_roles.cancel()

    # ---------- JOB ----------
    @commands.hybrid_group(name="job", description="💼 Job Finch")
    async def job_grup(self, ctx: commands.Context):
        """Bantuan grup job."""
        await ctx.send(
            embed=finch_embed(
                "💼 Job",
                "`/job lihat` — daftar job/class\n`/job pilih` — pilih job/class",
                warna="info",
            ),
            ephemeral=True,
        )
    @job_grup.command(name="lihat", description="Lihat daftar job/class")
    async def job(self, ctx: commands.Context):
        """Lihat job: /job lihat"""
        gid = ctx.guild.id if ctx.guild else 0
        with get_connection() as conn:
            aktif = jobmod.get_job(conn, gid, ctx.author.id)
        embed = finch_embed("💼 Daftar Job", "Pilih satu via `/job pilih` — bonusnya otomatis aktif!", warna="info")
        for job_id, info in jobmod.JOBS.items():
            tanda = " ✅" if job_id == aktif else ""
            embed.add_field(
                name=f"{info['nama']}{tanda}",
                value=f"`{job_id}`\n{info['deskripsi']}",
                inline=True,
            )
        await ctx.send(embed=embed)

    @job_grup.command(name="pilih", description="Pilih job/class")
    @discord.app_commands.describe(pilihan="Job yang mau diambil")
    @discord.app_commands.choices(
        pilihan=[
            discord.app_commands.Choice(name="Pedagang (+15% koin /kerja)", value="pedagang"),
            discord.app_commands.Choice(name="Petarung (+15% XP chat)", value="petarung"),
            discord.app_commands.Choice(name="Maling (+10% sukses /game maling)", value="maling"),
        ]
    )
    async def job_pilih(self, ctx: commands.Context, pilihan: str):
        """Pilih job: /job pilih <pedagang|petarung|maling>"""
        if ctx.guild is None:
            await ctx.send(embed=error_embed("Hanya bisa di server."), ephemeral=True)
            return
        if pilihan not in jobmod.JOBS:
            await ctx.send(embed=error_embed("Job tidak dikenal. Pilih: pedagang, petarung, maling."), ephemeral=True)
            return
        with get_connection() as conn:
            jobmod.set_job(conn, ctx.guild.id, ctx.author.id, pilihan)
        info = jobmod.JOBS[pilihan]
        await ctx.send(
            embed=sukses_embed(
                "Job Diambil!", f"Kamu sekarang **{info['nama']}**.\n{info['deskripsi']}"
            )
        )

    # ---------- NIKAH ----------
    @commands.hybrid_group(name="nikah", description="💍 Nikah Finch")
    async def nikah_grup(self, ctx: commands.Context):
        """Bantuan grup nikah."""
        await ctx.send(
            embed=finch_embed(
                "💍 Nikah",
                "`/nikah lamar` — lamar seseorang\n`/nikah cerai` — bercerai 💔\n`/nikah pasangan` — info pasanganmu\n`/nikah klaim` — bonus harian pasangan",
                warna="sosial",
            ),
            ephemeral=True,
        )
    @nikah_grup.command(name="lamar", description="Lamar seseorang 💍")
    @discord.app_commands.describe(target="Siapa yang mau dilamar")
    async def nikah(self, ctx: commands.Context, target: discord.Member):
        """Lamar: /nikah lamar @user"""
        if ctx.guild is None:
            await ctx.send(embed=error_embed("Hanya bisa di server."), ephemeral=True)
            return
        if target.id == ctx.author.id:
            await ctx.send(embed=error_embed("Nggak bisa nikah sama diri sendiri! 😅"), ephemeral=True)
            return
        if target.bot:
            await ctx.send(embed=error_embed("Bot tidak bisa dinikahi! 🤖"), ephemeral=True)
            return
        with get_connection() as conn:
            if _sudah_menikah(conn, ctx.guild.id, ctx.author.id):
                await ctx.send(embed=error_embed("Kamu sudah menikah! Setia dong. 😌"), ephemeral=True)
                return
            if _sudah_menikah(conn, ctx.guild.id, target.id):
                await ctx.send(embed=error_embed(f"{target.display_name} sudah menikah!"), ephemeral=True)
                return
        embed = finch_embed(
            "💍 Lamaran!",
            f"{ctx.author.mention} melamar {target.mention}!\n\n"
            f"{target.mention}, terima lamarannya? (120 detik)",
            warna="sosial",
        )
        await ctx.send(
            content=target.mention, embed=embed,
            view=LamaranView(ctx.author.id, target.id, ctx.guild.id),
        )

    @nikah_grup.command(name="cerai", description="Bercerai 💔")
    async def cerai(self, ctx: commands.Context):
        """Cerai: /nikah cerai"""
        if ctx.guild is None:
            await ctx.send(embed=error_embed("Hanya bisa di server."), ephemeral=True)
            return
        with get_connection() as conn:
            pasangan = _sudah_menikah(conn, ctx.guild.id, ctx.author.id)
        if not pasangan:
            await ctx.send(embed=error_embed("Kamu belum menikah."), ephemeral=True)
            return
        embed = finch_embed(
            "💔 Yakin cerai?",
            f"Kamu akan bercerai dengan <@{pasangan}>. Keputusan ini tidak bisa dibatalkan!",
            warna="sosial",
        )
        await ctx.send(embed=embed, view=CeraiView(ctx.author.id, pasangan), ephemeral=True)

    @nikah_grup.command(name="pasangan", description="Lihat info pasanganmu")
    async def pasangan(self, ctx: commands.Context):
        """Info pasangan: /nikah pasangan"""
        if ctx.guild is None:
            await ctx.send(embed=error_embed("Hanya bisa di server."), ephemeral=True)
            return
        with get_connection() as conn:
            row = conn.execute(
                "SELECT pasangan_id, sejak FROM nikah WHERE user_id = ? AND guild_id = ?",
                (ctx.author.id, ctx.guild.id),
            ).fetchone()
        if not row:
            await ctx.send(embed=error_embed("Kamu masih jomblo. Coba `/nikah lamar @gebetan`~ 😉"), ephemeral=True)
            return
        pasangan_id, sejak = row
        try:
            ts = int(datetime.datetime.fromisoformat(sejak).timestamp())
            sejak_txt = f"<t:{ts}:D>"
        except (ValueError, TypeError):
            sejak_txt = sejak
        embed = finch_embed("💒 Pasanganmu", "", warna="sosial")
        embed.add_field(name="Pasangan", value=f"<@{pasangan_id}>", inline=True)
        embed.add_field(name="Sejak", value=sejak_txt, inline=True)
        embed.add_field(
            name="Bonus", value=f"`/nikah klaim` → **{config.settings.nikah_bonus_harian}** 🪙/hari", inline=True
        )
        await ctx.send(embed=embed)

    @nikah_grup.command(name="klaim", description="Klaim bonus koin harian pasangan")
    async def klaim_nikah(self, ctx: commands.Context):
        """Klaim bonus nikah: /nikah klaim (cooldown 20 jam)"""
        if ctx.guild is None:
            await ctx.send(embed=error_embed("Hanya bisa di server."), ephemeral=True)
            return
        with get_connection() as conn:
            if not _sudah_menikah(conn, ctx.guild.id, ctx.author.id):
                await ctx.send(embed=error_embed("Kamu belum menikah. `/nikah lamar @user` dulu!"), ephemeral=True)
                return
            # Klaim cooldown atomik SEBELUM bagi koin: dua /nikah klaim yang
            # dieksekusi nyaris bersamaan tidak bisa dapat bonus ganda.
            if not _cooldown_klaim(conn, ctx.guild.id, ctx.author.id, "nikah_klaim", NIKAH_CLAIM_COOLDOWN_DETIK):
                sisa = _cooldown_sisa(conn, ctx.guild.id, ctx.author.id, "nikah_klaim", NIKAH_CLAIM_COOLDOWN_DETIK)
                jam = int(sisa // 3600)
                menit = int((sisa % 3600) // 60)
                await ctx.send(
                    embed=error_embed(f"Sudah diklaim! Coba lagi dalam **{jam}j {menit}m**."),
                    ephemeral=True,
                )
                return
            bonus = config.settings.nikah_bonus_harian
            eko.tambah_koin(conn, ctx.guild.id, ctx.author.id, bonus)
        await ctx.send(embed=sukses_embed("Bonus Nikah!", f"Kamu dapat **{koin_text(bonus)}**!"))

    # ---------- CONFESS ----------
    @commands.hybrid_command(name="confess", description="Kirim pesan anonim")
    @discord.app_commands.describe(teks="Isi pesan anonimmu")
    async def confess(self, ctx: commands.Context, *, teks: str):
        """Confess anonim: /confess <teks>"""
        if ctx.guild is None:
            await ctx.send(embed=error_embed("Hanya bisa di server."), ephemeral=True)
            return
        channel_id = config.settings.confess_channel_id
        if not channel_id:
            await ctx.send(
                embed=error_embed("Channel confess belum disetting admin (`CONFESS_CHANNEL_ID`)."),
                ephemeral=True,
            )
            return
        teks = teks.strip()
        if not teks:
            await ctx.send(embed=error_embed("Teks tidak boleh kosong."), ephemeral=True)
            return
        if len(teks) > 1000:
            await ctx.send(embed=error_embed("Teks maksimal 1000 karakter."), ephemeral=True)
            return
        if filters.contains_bad_word(teks, config.settings.bad_words_list()):
            await ctx.send(embed=error_embed("Pesan mengandung kata kasar. Ditolak!"), ephemeral=True)
            return
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                channel = None
        if channel is None:
            await ctx.send(embed=error_embed("Channel confess tidak ditemukan."), ephemeral=True)
            return
        embed = finch_embed("💌 Confess", teks, warna="sosial")
        embed.set_footer(text="💌 pesan anonim")
        # Klaim cooldown atomik tepat sebelum kirim (cek+catat satu statement):
        # double-click yang sama-sama lolos validasi di atas tidak bisa posting ganda.
        # Trade-off: kalau pengiriman gagal setelah klaim, cooldown tetap terpakai.
        with get_connection() as conn:
            diklaim = _cooldown_klaim(conn, ctx.guild.id, ctx.author.id, "confess", CONFESS_COOLDOWN_DETIK)
            sisa = 0.0 if diklaim else _cooldown_sisa(conn, ctx.guild.id, ctx.author.id, "confess", CONFESS_COOLDOWN_DETIK)
        if not diklaim:
            await ctx.send(
                embed=error_embed(f"Tunggu **{int(sisa // 60)}m {int(sisa % 60)}d** sebelum confess lagi."),
                ephemeral=True,
            )
            return
        try:
            # Confess itu anonim: matikan SEMUA mention agar teks user tidak
            # bisa dipakai untuk nge-ping orang lain secara anonim.
            await channel.send(
                embed=embed,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException:
            await ctx.send(embed=error_embed("Gagal kirim confess (cek permission bot)."), ephemeral=True)
            return
        log.info("Confess dari %s di guild %s", ctx.author.id, ctx.guild.id)
        await ctx.send(embed=sukses_embed("Terkirim!", "Pesan anonimmu sudah diposting."), ephemeral=True)

    # ---------- CLAN ----------
    def _clan_user(self, conn, user_id: int):
        """Return (clan_id, nama, ketua_id) clan milik user, atau None."""
        return conn.execute(
            "SELECT c.id, c.nama, c.ketua_id FROM clan c "
            "JOIN clan_member m ON m.clan_id = c.id WHERE m.user_id = ?",
            (user_id,),
        ).fetchone()

    @commands.hybrid_group(name="clan", description="⚔️ Clan Finch")
    async def clan(self, ctx: commands.Context):
        """Bantuan grup clan."""
        await ctx.send(
            embed=finch_embed(
                "⚔️ Clan",
                "`/clan buat` — buat clan baru\n`/clan gabung` — gabung ke clan\n`/clan keluar` — keluar dari clan\n`/clan info` — info clan\n`/clan war` — daftar clan war (ketua)",
                warna="sosial",
            ),
            ephemeral=True,
        )
    @clan.command(name="buat", description="Buat clan baru")
    @discord.app_commands.describe(nama="Nama clan (maks 20 karakter)")
    async def clan_buat(self, ctx: commands.Context, *, nama: str):
        """Buat clan: /clan buat <nama>"""
        if ctx.guild is None:
            await ctx.send(embed=error_embed("Hanya bisa di server."), ephemeral=True)
            return
        nama = nama.strip()
        if not (1 <= len(nama) <= 20):
            await ctx.send(embed=error_embed("Nama clan 1-20 karakter."), ephemeral=True)
            return
        with get_connection() as conn:
            if self._clan_user(conn, ctx.author.id):
                await ctx.send(embed=error_embed("Kamu sudah punya clan! Keluar dulu via `/clan keluar`."), ephemeral=True)
                return
            dupe = conn.execute(
                "SELECT id FROM clan WHERE guild_id = ? AND nama = ?", (ctx.guild.id, nama)
            ).fetchone()
            if dupe:
                await ctx.send(embed=error_embed(f"Nama clan **{nama}** sudah dipakai."), ephemeral=True)
                return
            biaya = config.settings.clan_biaya
            # Satu transaksi atomik: potong koin + buat clan sekaligus.
            # Guarded UPDATE: cek & potong dalam 1 statement (anti race).
            eko.get_akun(conn, ctx.guild.id, ctx.author.id)  # pastikan row ada
            cur = conn.execute(
                "UPDATE economy SET balance = balance - ?"
                " WHERE user_id = ? AND guild_id = ? AND balance >= ?",
                (biaya, ctx.author.id, ctx.guild.id, biaya),
            )
            if cur.rowcount == 0:
                await ctx.send(
                    embed=error_embed(f"Koin tidak cukup! Buat clan butuh **{koin_text(biaya)}**."),
                    ephemeral=True,
                )
                return
            cur = conn.execute(
                "INSERT INTO clan (guild_id, nama, ketua_id, dibuat) VALUES (?, ?, ?, ?)",
                (ctx.guild.id, nama, ctx.author.id, discord.utils.utcnow().isoformat()),
            )
            conn.execute(
                "INSERT INTO clan_member (clan_id, user_id, joined) VALUES (?, ?, ?)",
                (cur.lastrowid, ctx.author.id, discord.utils.utcnow().isoformat()),
            )
            conn.commit()
        await ctx.send(
            embed=sukses_embed("Clan Dibuat!", f"**{nama}** resmi berdiri!\nKamu ketuanya. Ajak temanmu via `/clan gabung {nama}`.")
        )

    @clan.command(name="gabung", description="Gabung ke clan")
    @discord.app_commands.describe(nama="Nama clan")
    async def clan_gabung(self, ctx: commands.Context, *, nama: str):
        """Gabung clan: /clan gabung <nama>"""
        if ctx.guild is None:
            await ctx.send(embed=error_embed("Hanya bisa di server."), ephemeral=True)
            return
        with get_connection() as conn:
            if self._clan_user(conn, ctx.author.id):
                await ctx.send(embed=error_embed("Kamu sudah punya clan!"), ephemeral=True)
                return
            row = conn.execute(
                "SELECT id, nama FROM clan WHERE guild_id = ? AND nama = ?",
                (ctx.guild.id, nama.strip()),
            ).fetchone()
            if not row:
                await ctx.send(embed=error_embed(f"Clan **{nama}** tidak ditemukan."), ephemeral=True)
                return
            # INSERT OR IGNORE + rowcount: dua /clan gabung bersamaan tidak
            # IntegrityError; yang kalah race dianggap sudah punya clan.
            cur = conn.execute(
                "INSERT OR IGNORE INTO clan_member (clan_id, user_id, joined) VALUES (?, ?, ?)",
                (row[0], ctx.author.id, discord.utils.utcnow().isoformat()),
            )
            conn.commit()
            if cur.rowcount == 0:
                # Kalah race: baris sudah ada (cek di atas lolos bersamaan)
                await ctx.send(embed=error_embed("Kamu sudah punya clan!"), ephemeral=True)
                return
        await ctx.send(embed=sukses_embed("Gabung Clan!", f"Selamat datang di **{row[1]}**!"))

    @clan.command(name="keluar", description="Keluar dari clan")
    async def clan_keluar(self, ctx: commands.Context):
        """Keluar clan: /clan keluar"""
        if ctx.guild is None:
            await ctx.send(embed=error_embed("Hanya bisa di server."), ephemeral=True)
            return
        with get_connection() as conn:
            milik = self._clan_user(conn, ctx.author.id)
            if not milik:
                await ctx.send(embed=error_embed("Kamu tidak punya clan."), ephemeral=True)
                return
            clan_id, nama, ketua_id = milik
            conn.execute("DELETE FROM clan_member WHERE clan_id = ? AND user_id = ?", (clan_id, ctx.author.id))
            sisa = conn.execute(
                "SELECT user_id FROM clan_member WHERE clan_id = ? ORDER BY joined ASC LIMIT 1", (clan_id,)
            ).fetchone()
            if sisa is None:
                conn.execute("DELETE FROM clan WHERE id = ?", (clan_id,))
                conn.commit()
                await ctx.send(embed=sukses_embed("Clan Bubar", f"**{nama}** dibubarkan (tidak ada anggota)."))
                return
            if ketua_id == ctx.author.id:
                conn.execute("UPDATE clan SET ketua_id = ? WHERE id = ?", (sisa[0], clan_id))
            conn.commit()
        await ctx.send(embed=sukses_embed("Keluar Clan", f"Kamu keluar dari **{nama}**."))

    @clan.command(name="info", description="Info clan")
    @discord.app_commands.describe(nama="Nama clan (opsional, default clanmu)")
    async def clan_info(self, ctx: commands.Context, *, nama: str | None = None):
        """Info clan: /clan info [nama]"""
        if ctx.guild is None:
            await ctx.send(embed=error_embed("Hanya bisa di server."), ephemeral=True)
            return
        with get_connection() as conn:
            if nama:
                row = conn.execute(
                    "SELECT id, nama, ketua_id FROM clan WHERE guild_id = ? AND nama = ?",
                    (ctx.guild.id, nama.strip()),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT c.id, c.nama, c.ketua_id FROM clan c "
                    "JOIN clan_member m ON m.clan_id = c.id "
                    "WHERE m.user_id = ? AND c.guild_id = ?",
                    (ctx.author.id, ctx.guild.id),
                ).fetchone()
            if not row:
                await ctx.send(embed=error_embed("Clan tidak ditemukan."), ephemeral=True)
                return
            clan_id, nama_clan, ketua_id = row
            jumlah = conn.execute(
                "SELECT COUNT(*) FROM clan_member WHERE clan_id = ?", (clan_id,)
            ).fetchone()[0]
            total_level = conn.execute(
                "SELECT COALESCE(SUM(u.level), 0) FROM users u "
                "JOIN clan_member m ON m.user_id = u.user_id AND u.guild_id = ? "
                "WHERE m.clan_id = ?",
                (ctx.guild.id, clan_id),
            ).fetchone()[0]
        _mg = discord.utils.utcnow().isocalendar()[:2]
        _minggu_txt = f"{_mg[0]}-W{_mg[1]:02d}"
        with get_connection() as conn:
            ikut_war = conn.execute(
                "SELECT 1 FROM clan_war_peserta WHERE guild_id = ? AND clan_id = ? AND minggu = ?",
                (ctx.guild.id, clan_id, _minggu_txt),
            ).fetchone() is not None
        ikut = "⚔️ Ikut war minggu ini" if ikut_war else "Belum ikut war"
        embed = finch_embed(f"⚔️ Clan {nama_clan}", ikut, warna="sosial")
        embed.add_field(name="Ketua", value=f"<@{ketua_id}>", inline=True)
        embed.add_field(name="Anggota", value=f"**{jumlah}**", inline=True)
        embed.add_field(name="Total Level", value=f"**{total_level}**", inline=True)
        await ctx.send(embed=embed)

    @clan.command(name="war", description="Daftarkan clan ikut clan war (ketua)")
    async def clan_war(self, ctx: commands.Context):
        """Daftar clan war: /clan war (ketua saja)"""
        if ctx.guild is None:
            await ctx.send(embed=error_embed("Hanya bisa di server."), ephemeral=True)
            return
        with get_connection() as conn:
            milik = self._clan_user(conn, ctx.author.id)
            if not milik:
                await ctx.send(embed=error_embed("Kamu tidak punya clan."), ephemeral=True)
                return
            clan_id, nama, ketua_id = milik
            if ketua_id != ctx.author.id:
                await ctx.send(embed=error_embed("Hanya ketua clan yang bisa mendaftar war!"), ephemeral=True)
                return
        minggu = discord.utils.utcnow().isocalendar()[:2]
        minggu_txt = f"{minggu[0]}-W{minggu[1]:02d}"
        with get_connection() as conn:
            # Filter minggu berjalan — baris basi (bot down saat settlement)
            # tidak boleh memblokir pendaftaran minggu berikutnya selamanya.
            sudah = conn.execute(
                "SELECT 1 FROM clan_war_peserta WHERE guild_id = ? AND clan_id = ? AND minggu = ?",
                (ctx.guild.id, clan_id, minggu_txt),
            ).fetchone()
            if sudah:
                await ctx.send(embed=error_embed(f"**{nama}** sudah terdaftar war minggu ini."), ephemeral=True)
                return
            # INSERT OR IGNORE + rowcount: dua /clan war bersamaan tidak
            # IntegrityError; yang kalah race dianggap sudah terdaftar.
            cur = conn.execute(
                "INSERT OR IGNORE INTO clan_war_peserta (guild_id, clan_id, minggu) VALUES (?, ?, ?)",
                (ctx.guild.id, clan_id, minggu_txt),
            )
            conn.commit()
            if cur.rowcount == 0:
                await ctx.send(embed=error_embed(f"**{nama}** sudah terdaftar war minggu ini."), ephemeral=True)
                return
        await ctx.send(
            embed=sukses_embed(
                "Clan War!",
                f"**{nama}** terdaftar ikut war minggu ini!\n"
                f"Total level anggota tertinggi menang → hadiah **{koin_text(config.settings.clan_war_hadiah)}** dibagi rata.\n"
                "Pengumuman tiap Senin.",
            )
        )

    @tasks.loop(hours=1)
    async def cek_war(self):
        """Settlement clan war tiap Senin 00:00 UTC.

        Peserta persisten di DB — bila settlement gagal, peserta TIDAK dihapus
        sehingga dicoba lagi jam berikutnya (tidak hilang diam-diam).
        """
        now = discord.utils.utcnow()
        # Bersihkan baris minggu lama — kalau bot down tepat saat settlement Senin
        # 00:00 UTC, peserta basi tidak menumpuk & tidak memblokir minggu berikut.
        _mg = now.isocalendar()[:2]
        _minggu_txt = f"{_mg[0]}-W{_mg[1]:02d}"
        try:
            with get_connection() as conn:
                conn.execute(
                    "DELETE FROM clan_war_peserta WHERE minggu != ?", (_minggu_txt,)
                )
                conn.commit()
        except Exception:
            log.exception("Gagal bersihkan peserta war minggu lama")
        if not (now.weekday() == 0 and now.hour == 0):
            return
        try:
            with get_connection() as conn:
                gids = [
                    r[0]
                    for r in conn.execute(
                        "SELECT DISTINCT guild_id FROM clan_war_peserta"
                    )
                ]
        except Exception:
            log.exception("Gagal baca peserta clan war")
            return
        for gid in gids:
            try:
                with get_connection() as conn:
                    clan_ids = {
                        r[0]
                        for r in conn.execute(
                            "SELECT clan_id FROM clan_war_peserta WHERE guild_id = ?",
                            (gid,),
                        )
                    }
                if not clan_ids:
                    continue
                await self._selesaikan_war(gid, clan_ids)
                # Hapus peserta HANYA setelah settlement sukses
                with get_connection() as conn:
                    conn.execute(
                        "DELETE FROM clan_war_peserta WHERE guild_id = ?", (gid,)
                    )
                    conn.commit()
            except Exception:
                log.exception("Gagal selesaikan clan war guild %s", gid)

    @cek_war.before_loop
    async def _before_war(self):
        await self.bot.wait_until_ready()

    # ---------- VOICE LEVEL ROLES ----------
    @tasks.loop(minutes=10)
    async def cek_voice_roles(self):
        """Beri role otomatis berdasarkan total menit voice (LEVEL_ROLES_VOICE)."""
        rewards = config.settings.level_roles_voice_list()
        if not rewards:
            return
        for guild in self.bot.guilds:
            try:
                with get_connection() as conn:
                    rows = conn.execute(
                        "SELECT user_id, menit FROM voice_total WHERE guild_id = ?",
                        (guild.id,),
                    ).fetchall()
            except Exception:
                continue
            for user_id, menit in rows:
                member = guild.get_member(user_id)
                if member is None or member.bot:
                    continue
                for threshold, nama in rewards:
                    if threshold > (menit or 0):
                        break
                    role = discord.utils.get(guild.roles, name=nama)
                    if role is None or role in member.roles:
                        continue
                    try:
                        await member.add_roles(
                            role, reason=f"Reward voice {threshold} menit"
                        )
                        log.info("%s dapat role voice '%s'.", member, nama)
                    except discord.Forbidden:
                        log.warning(
                            "Gagal kasih role voice '%s' — role bot harus di atasnya.",
                            nama,
                        )
                        break
                    except discord.HTTPException:
                        break

    @cek_voice_roles.before_loop
    async def _before_voice_roles(self):
        await self.bot.wait_until_ready()

    async def _selesaikan_war(self, guild_id: int, clan_ids: set[int]):
        with get_connection() as conn:
            skor = []
            for cid in clan_ids:
                row = conn.execute("SELECT nama FROM clan WHERE id = ?", (cid,)).fetchone()
                if not row:
                    continue
                total = conn.execute(
                    "SELECT COALESCE(SUM(u.level), 0) FROM users u "
                    "JOIN clan_member m ON m.user_id = u.user_id AND u.guild_id = ? "
                    "WHERE m.clan_id = ?",
                    (guild_id, cid),
                ).fetchone()[0]
                anggota = [r[0] for r in conn.execute(
                    "SELECT user_id FROM clan_member WHERE clan_id = ?", (cid,)
                )]
                skor.append((total, cid, row[0], anggota))
        if not skor:
            return
        skor.sort(reverse=True)
        total_menang, _cid_menang, nama_menang, anggota = skor[0]
        hadiah = config.settings.clan_war_hadiah
        per_orang = hadiah // max(1, len(anggota))
        dibayar = 0
        with get_connection() as conn:
            for uid in anggota:
                try:
                    eko.tambah_koin(conn, guild_id, uid, per_orang)
                    dibayar += 1
                except Exception:
                    log.exception("Clan war: gagal bayar %s", uid)
        log.info(
            "Clan war guild %s dimenangkan %s (%d level), dibayar %d/%d anggota.",
            guild_id, nama_menang, total_menang, dibayar, len(anggota),
        )
        guild = self.bot.get_guild(guild_id)
        ch = guild.system_channel if guild else None
        if ch is None:
            return
        baris = "\n".join(f"**{i+1}.** {nama} — {total} level" for i, (total, _c, nama, _a) in enumerate(skor))
        embed = finch_embed("⚔️ Clan War Berakhir!", baris, warna="sosial")
        embed.add_field(
            name="Pemenang",
            value=f"**{nama_menang}**\nTiap anggota +**{koin_text(per_orang)}**!",
            inline=False,
        )
        try:
            await ch.send(embed=embed)
        except discord.HTTPException:
            pass

    # ---------- GELAR ----------
    @commands.hybrid_group(name="gelar", description="🎖️ Gelar Finch")
    async def gelar_grup(self, ctx: commands.Context):
        """Bantuan grup gelar."""
        await ctx.send(
            embed=finch_embed(
                "🎖️ Gelar",
                "`/gelar toko` — toko gelar/title\n`/gelar beli` — beli gelar\n`/gelar pasang` — pasang gelar di profil\n`/gelar lepas` — lepas gelar",
                warna="sosial",
            ),
            ephemeral=True,
        )
    @gelar_grup.command(name="toko", description="Toko gelar/title")
    async def gelar(self, ctx: commands.Context):
        """Toko gelar: /gelar toko"""
        gid = ctx.guild.id if ctx.guild else 0
        with get_connection() as conn:
            milik = {
                r[0] for r in conn.execute(
                    "SELECT gelar_id FROM gelar_milik WHERE user_id = ? AND guild_id = ?",
                    (ctx.author.id, gid),
                )
            }
            aktif = conn.execute(
                "SELECT gelar_id FROM gelar_aktif WHERE user_id = ? AND guild_id = ?",
                (ctx.author.id, gid),
            ).fetchone()
        aktif_id = aktif[0] if aktif else None
        embed = finch_embed("🎖️ Toko Gelar", "Beli via `/gelar beli <id>`, pasang via `/gelar pasang <id>`.", warna="info")
        for gelar_id, info in GELAR_TOKO.items():
            status = "✅ dipakai" if gelar_id == aktif_id else ("📦 punya" if gelar_id in milik else koin_text(info["harga"]))
            embed.add_field(name=info["nama"], value=f"`{gelar_id}`\n{status}", inline=True)
        await ctx.send(embed=embed)

    @gelar_grup.command(name="beli", description="Beli gelar")
    @discord.app_commands.describe(id="ID gelar: sultan, legenda, kraz")
    async def gelar_beli(self, ctx: commands.Context, id: str):
        """Beli gelar: /gelar beli <id>"""
        if ctx.guild is None:
            await ctx.send(embed=error_embed("Hanya bisa di server."), ephemeral=True)
            return
        id = id.strip().lower()
        if id not in GELAR_TOKO:
            await ctx.send(embed=error_embed("ID gelar tidak dikenal. Lihat `/gelar`."), ephemeral=True)
            return
        info = GELAR_TOKO[id]
        with get_connection() as conn:
            punya = conn.execute(
                "SELECT 1 FROM gelar_milik WHERE user_id = ? AND guild_id = ? AND gelar_id = ?",
                (ctx.author.id, ctx.guild.id, id),
            ).fetchone()
            if punya:
                await ctx.send(embed=error_embed("Kamu sudah punya gelar ini!"), ephemeral=True)
                return
            harga = info["harga"]
            # Satu transaksi atomik: potong koin + catat kepemilikan sekaligus
            eko.get_akun(conn, ctx.guild.id, ctx.author.id)  # pastikan row ada
            cur = conn.execute(
                "UPDATE economy SET balance = balance - ?"
                " WHERE user_id = ? AND guild_id = ? AND balance >= ?",
                (harga, ctx.author.id, ctx.guild.id, harga),
            )
            if cur.rowcount == 0:
                await ctx.send(
                    embed=error_embed(f"Koin tidak cukup! Butuh **{koin_text(harga)}**."),
                    ephemeral=True,
                )
                return
            conn.execute(
                "INSERT INTO gelar_milik (user_id, guild_id, gelar_id) VALUES (?, ?, ?)",
                (ctx.author.id, ctx.guild.id, id),
            )
            conn.commit()
        await ctx.send(embed=sukses_embed("Gelar Dibeli!", f"Kamu dapat gelar **{info['nama']}**!\nPasang via `/gelar pasang {id}`."))

    @gelar_grup.command(name="pasang", description="Pasang gelar di profil")
    @discord.app_commands.describe(id="ID gelar yang kamu punya")
    async def gelar_pasang(self, ctx: commands.Context, id: str):
        """Pasang gelar: /gelar pasang <id>"""
        if ctx.guild is None:
            await ctx.send(embed=error_embed("Hanya bisa di server."), ephemeral=True)
            return
        id = id.strip().lower()
        if id not in GELAR_TOKO:
            await ctx.send(embed=error_embed("ID gelar tidak dikenal."), ephemeral=True)
            return
        with get_connection() as conn:
            punya = conn.execute(
                "SELECT 1 FROM gelar_milik WHERE user_id = ? AND guild_id = ? AND gelar_id = ?",
                (ctx.author.id, ctx.guild.id, id),
            ).fetchone()
            if not punya:
                await ctx.send(embed=error_embed("Kamu belum punya gelar ini. Beli dulu via `/gelar beli`."), ephemeral=True)
                return
            conn.execute(
                "INSERT INTO gelar_aktif (user_id, guild_id, gelar_id) VALUES (?, ?, ?) "
                "ON CONFLICT(user_id, guild_id) DO UPDATE SET gelar_id = excluded.gelar_id",
                (ctx.author.id, ctx.guild.id, id),
            )
            conn.commit()
        await ctx.send(embed=sukses_embed("Gelar Dipasang!", f"Profilmu sekarang bergelar **{GELAR_TOKO[id]['nama']}**."))

    @gelar_grup.command(name="lepas", description="Lepas gelar dari profil")
    async def gelar_lepas(self, ctx: commands.Context):
        """Lepas gelar: /gelar lepas"""
        if ctx.guild is None:
            await ctx.send(embed=error_embed("Hanya bisa di server."), ephemeral=True)
            return
        with get_connection() as conn:
            cur = conn.execute(
                "DELETE FROM gelar_aktif WHERE user_id = ? AND guild_id = ?",
                (ctx.author.id, ctx.guild.id),
            )
            conn.commit()
            if cur.rowcount == 0:
                await ctx.send(embed=error_embed("Tidak ada gelar terpasang."), ephemeral=True)
                return
        await ctx.send(embed=sukses_embed("Gelar Dilepas", "Gelar di profilmu dicopot."))

    # ---------- TOP PRESTIGE ----------
    @commands.hybrid_command(name="top-prestige", description="Leaderboard prestise")
    async def top_prestige(self, ctx: commands.Context):
        """Top prestise: /top-prestige"""
        gid = ctx.guild.id if ctx.guild else 0
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT user_id, COALESCE(prestige, 0) FROM users "
                "WHERE guild_id = ? AND COALESCE(prestige, 0) > 0 "
                "ORDER BY prestige DESC, level DESC LIMIT 10",
                (gid,),
            ).fetchall()
        if not rows:
            await ctx.send(embed=error_embed("Belum ada yang prestige. `/prestige` butuh level 30!"), ephemeral=True)
            return
        medals = ["🥇", "🥈", "🥉"]
        embed = finch_embed("🎖️ Top Prestise", "", warna="info")
        for i, (uid, prest) in enumerate(rows):
            nama = medals[i] if i < 3 else f"**{i+1}.**"
            embed.add_field(name=f"{nama} Prestise {prest}", value=f"<@{uid}>", inline=True)
        await ctx.send(embed=embed)


def gelar_nama(conn, guild_id: int, user_id: int) -> str | None:
    """Helper untuk profil.py: nama gelar aktif user."""
    row = conn.execute(
        "SELECT gelar_id FROM gelar_aktif WHERE user_id = ? AND guild_id = ?",
        (user_id, guild_id),
    ).fetchone()
    if not row:
        return None
    return GELAR_TOKO.get(row[0], {}).get("nama")


async def setup(bot: commands.Bot):
    await bot.add_cog(Sosial(bot))
