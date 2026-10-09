"""Engagement — pet, quest guild, daily question, hall of fame.

- Pet: `/pet adopsi <nama> <jenis>`, `/pet info`, `/pet ganti-nama` — +1 xp per pesan,
  level = xp // 100 + 1, umumkan naik level di channel (ringkas, sekali).
- Quest guild: `/quest-guild` — misi mingguan bareng (dibuat tiap Senin 00:00 UTC);
  tercapai → hadiah masuk pool giveaway server.
- Daily question: pertanyaan harian di channel khusus; penjawab tercepat dapat koin.
- `/hof` — hall of fame: top 5 pesan starboard (live ⭐ count, best effort).
"""
import datetime
import logging
import random
import sqlite3

import discord
from discord.ext import commands, tasks

from src import config
from src.store import get_connection
from src.utils import achievement as ach
from src.utils import economy as eko
from src.utils.embeds import (
    error_embed,
    finch_embed,
    get_progress_bar,
    koin_text,
    sukses_embed,
)

log = logging.getLogger("finch")

WIB = datetime.timezone(datetime.timedelta(hours=7))
PET_XP_PER_LEVEL = 100

JENIS_PET = {
    "kucing": "🐱",
    "anjing": "🐶",
    "burung": "🐦",
    "naga": "🐲",
}

PERTANYAAN_HARIAN = [
    "Hewan apa yang bisa tidur sambil berdiri?",
    "Planet apa yang paling dekat dengan Matahari?",
    "Berapa pemain sepak bola dalam satu tim di lapangan?",
    "Warna apa hasil campuran cat biru dan kuning?",
    "Apa nama samudra terbesar di dunia?",
    "Berapa jumlah sisi pada segitiga?",
    "Hewan apa yang dijuluki 'raja hutan'?",
    "Apa ibu kota Jepang?",
    "Buah apa yang kulitnya berduri tajam?",
    "Berapa jam dalam sehari?",
    "Apa saja warna bendera Indonesia?",
    "Hewan apa yang bertelur tapi menyusui anaknya?",
    "Apa nama sungai terpanjang di Indonesia?",
    "Berapa jumlah roda pada mobil biasa?",
    "Apa kepanjangan dari SIM?",
    "Apa makanan favorit Doraemon?",
    "Siapa penulis novel 'Laskar Pelangi'?",
    "Berapa hasil 7 x 8?",
    "Apa nama mata uang Jepang?",
    "Hewan apa yang lehernya paling panjang?",
    "Kota apa yang dijuluki 'Kota Hujan'?",
    "Apa nama candi Buddha terbesar di Indonesia?",
    "Berapa jumlah kaki laba-laba?",
    "Es batu kalau mencair jadi apa?",
    "Apa nama planet tempat kita tinggal?",
    "Alat musik apa yang dimainkan dengan cara dipetik dan punya 6 senar?",
    "Berapa jumlah provinsi di Indonesia saat ini?",
    "Hewan apa yang bisa berubah warna kulitnya?",
    "Apa nama benua terbesar di dunia?",
    "Minuman apa yang dibuat dari biji kopi yang diseduh?",
]


def pet_level(xp: int) -> int:
    """Level pet dari xp. Pure function — gampang dites."""
    return max(0, xp) // PET_XP_PER_LEVEL + 1


def pet_progress(xp: int) -> tuple[int, int]:
    """(xp dalam level berjalan, xp per level). Pure function — gampang dites."""
    return max(0, xp) % PET_XP_PER_LEVEL, PET_XP_PER_LEVEL


def senin_depan_utc(dari: datetime.datetime | None = None) -> datetime.datetime:
    """Senin 00:00 UTC berikutnya. Pure function — gampang dites."""
    now = dari or discord.utils.utcnow()
    if now.tzinfo is None:
        now = now.replace(tzinfo=datetime.timezone.utc)
    hari_ke_senin = (7 - now.weekday()) % 7
    senin = (now + datetime.timedelta(days=hari_ke_senin)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    if senin <= now:
        senin += datetime.timedelta(days=7)
    return senin


def pertanyaan_tanggal(tanggal: str, guild_id: int) -> str:
    """Pilih 1 pertanyaan deterministik per tanggal+guild. Pure function."""
    rng = random.Random(f"{guild_id}-{tanggal}")
    return rng.choice(PERTANYAAN_HARIAN)


class Engagement(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.loop_quest_mingguan.start()
        self.loop_dailyq.start()

    def cog_unload(self):
        self.loop_quest_mingguan.cancel()
        self.loop_dailyq.cancel()

    # ---------- Pet ----------

    @commands.hybrid_group(name="pet", description="🐾 Pet Finch")
    async def pet_grup(self, ctx: commands.Context):
        """Bantuan grup pet."""
        await ctx.send(
            embed=finch_embed(
                "🐾 Pet",
                "`/pet adopsi` — adopsi hewan peliharaan\n`/pet info` — lihat pet milikmu\n`/pet ganti-nama` — ganti nama pet",
                warna="sosial",
            ),
            ephemeral=True,
        )
    @pet_grup.command(name="adopsi", description="Adopsi hewan peliharaan")
    @discord.app_commands.describe(
        nama="Nama pet kamu",
        jenis="Jenis hewan",
    )
    @discord.app_commands.choices(
        jenis=[
            discord.app_commands.Choice(name="Kucing", value="kucing"),
            discord.app_commands.Choice(name="Anjing", value="anjing"),
            discord.app_commands.Choice(name="Burung", value="burung"),
            discord.app_commands.Choice(name="Naga", value="naga"),
        ]
    )
    async def pet_adopsi(self, ctx: commands.Context, nama: str, jenis: str):
        """Adopsi pet: /pet adopsi <nama> <jenis>"""
        if ctx.guild is None:
            await ctx.send(embed=error_embed("Hanya bisa di server."), ephemeral=True)
            return
        jenis = (jenis or "").lower()
        if jenis not in JENIS_PET:
            await ctx.send(
                embed=error_embed("Jenis tidak valid. Pilih: kucing, anjing, burung, naga."),
                ephemeral=True,
            )
            return
        nama = (nama or "").strip()[:20]
        if not nama:
            await ctx.send(embed=error_embed("Nama pet tidak boleh kosong."), ephemeral=True)
            return
        harga = config.settings.pet_harga
        with get_connection() as conn:
            ada = conn.execute(
                "SELECT 1 FROM pet WHERE user_id = ? AND guild_id = ?",
                (ctx.author.id, ctx.guild.id),
            ).fetchone()
            if ada:
                await ctx.send(
                    embed=error_embed("Kamu sudah punya pet! Lihat dengan `/pet info`."),
                    ephemeral=True,
                )
                return
            sisa = eko.kurang_koin(conn, ctx.guild.id, ctx.author.id, harga)
            if sisa is None:
                await ctx.send(
                    embed=error_embed(
                        f"Koin tidak cukup. Adopsi pet butuh {koin_text(harga)}."
                    ),
                    ephemeral=True,
                )
                return
            # INSERT OR IGNORE + rowcount: klaim atomik. Double-click yang
            # lolos cek `ada` di atas tidak bisa bikin 2 pet — dan koin
            # dikembalikan kalau ternyata sudah punya (dulu: IntegrityError
            # → koin hangus).
            cur = conn.execute(
                "INSERT OR IGNORE INTO pet (user_id, guild_id, nama, jenis, xp, dibuat)"
                " VALUES (?, ?, ?, ?, 0, ?)",
                (
                    ctx.author.id, ctx.guild.id, nama, jenis,
                    discord.utils.utcnow().isoformat(),
                ),
            )
            if cur.rowcount == 0:
                eko.tambah_koin(conn, ctx.guild.id, ctx.author.id, harga)
                await ctx.send(
                    embed=error_embed("Kamu sudah punya pet! Lihat dengan `/pet info`."),
                    ephemeral=True,
                )
                return
            conn.commit()
        await ctx.send(
            embed=sukses_embed(
                "Pet diadopsi!",
                f"{JENIS_PET[jenis]} **{nama}** resmi jadi temanmu!\n"
                "Ajak ngobrol di channel — tiap pesan = +1 XP pet.",
            )
        )

    @pet_grup.command(name="info", description="Lihat hewan peliharaanmu")
    async def pet(self, ctx: commands.Context):
        """Info pet: /pet info"""
        if ctx.guild is None:
            await ctx.send(embed=error_embed("Hanya bisa di server."), ephemeral=True)
            return
        with get_connection() as conn:
            row = conn.execute(
                "SELECT nama, jenis, xp FROM pet WHERE user_id = ? AND guild_id = ?",
                (ctx.author.id, ctx.guild.id),
            ).fetchone()
        if not row:
            await ctx.send(
                embed=error_embed("Kamu belum punya pet. Adopsi dulu dengan `/pet adopsi`."),
                ephemeral=True,
            )
            return
        nama, jenis, xp = row
        lvl = pet_level(xp)
        cur, total = pet_progress(xp)
        bar = get_progress_bar(cur, total)
        embed = finch_embed(
            f"{JENIS_PET.get(jenis, '🐾')} {nama}",
            f"Pet kesayangan **{ctx.author.display_name}**",
            warna="game",
            thumbnail=ctx.author.avatar.url if ctx.author.avatar else None,
        )
        embed.add_field(name="Jenis", value=jenis.capitalize(), inline=True)
        embed.add_field(name="Level", value=f"**{lvl}**", inline=True)
        embed.add_field(name="XP", value=f"**{cur} / {total}**", inline=True)
        embed.add_field(name="Progress", value=f"`{bar}`", inline=False)
        await ctx.send(embed=embed)

    @pet_grup.command(name="ganti-nama", description="Ganti nama pet")
    @discord.app_commands.describe(nama="Nama baru pet")
    async def pet_nama(self, ctx: commands.Context, nama: str):
        """Ganti nama pet: /pet ganti-nama <nama baru>"""
        if ctx.guild is None:
            await ctx.send(embed=error_embed("Hanya bisa di server."), ephemeral=True)
            return
        nama = (nama or "").strip()[:20]
        if not nama:
            await ctx.send(embed=error_embed("Nama baru tidak boleh kosong."), ephemeral=True)
            return
        with get_connection() as conn:
            cur = conn.execute(
                "UPDATE pet SET nama = ? WHERE user_id = ? AND guild_id = ?",
                (nama, ctx.author.id, ctx.guild.id),
            )
            conn.commit()
            if cur.rowcount == 0:
                await ctx.send(
                    embed=error_embed("Kamu belum punya pet. Adopsi dulu dengan `/pet adopsi`."),
                    ephemeral=True,
                )
                return
        await ctx.send(embed=sukses_embed("Nama diganti!", f"Pet-mu sekarang bernama **{nama}**. 🎉"))

    # ---------- Quest guild ----------

    @commands.hybrid_command(
        name="quest-guild", description="Lihat misi mingguan server"
    )
    async def quest_guild(self, ctx: commands.Context):
        """Info quest guild: /quest-guild"""
        if ctx.guild is None:
            await ctx.send(embed=error_embed("Hanya bisa di server."), ephemeral=True)
            return
        now_iso = discord.utils.utcnow().isoformat()
        with get_connection() as conn:
            row = conn.execute(
                "SELECT nama, target, progres, hadiah, berakhir FROM quest_guild"
                " WHERE guild_id = ? AND selesai = 0 AND berakhir > ?"
                " ORDER BY id DESC LIMIT 1",
                (ctx.guild.id, now_iso),
            ).fetchone()
        if not row:
            await ctx.send(
                embed=finch_embed(
                    "🗺️ Quest Guild", "Belum ada quest aktif. Coba lagi nanti!", warna="event"
                ),
                ephemeral=True,
            )
            return
        nama, target, progres, hadiah, berakhir = row
        bar = get_progress_bar(progres, target)
        try:
            ts = int(datetime.datetime.fromisoformat(berakhir).timestamp())
            berakhir_txt = f"<t:{ts}:R>"
        except ValueError:
            berakhir_txt = berakhir
        embed = finch_embed("🗺️ Quest Guild", nama, warna="event")
        embed.add_field(
            name="Progres",
            value=f"**{progres:,}** / **{target:,}**".replace(",", "."),
            inline=True,
        )
        embed.add_field(name="Hadiah Pool", value=koin_text(hadiah), inline=True)
        embed.add_field(name="Berakhir", value=berakhir_txt, inline=True)
        embed.add_field(name="Progress", value=f"`{bar}`", inline=False)
        await ctx.send(embed=embed)

    @tasks.loop(hours=1)
    async def loop_quest_mingguan(self):
        """Tutup quest kedaluwarsa & buat quest baru tiap Senin 00:00 UTC."""
        try:
            now_iso = discord.utils.utcnow().isoformat()
            with get_connection() as conn:
                conn.execute(
                    "UPDATE quest_guild SET selesai = 1 WHERE selesai = 0 AND berakhir <= ?",
                    (now_iso,),
                )
                conn.commit()
            for guild in self.bot.guilds:
                try:
                    with get_connection() as conn:
                        aktif = conn.execute(
                            "SELECT 1 FROM quest_guild WHERE guild_id = ? AND selesai = 0"
                            " AND berakhir > ?",
                            (guild.id, now_iso),
                        ).fetchone()
                        if not aktif:
                            target = config.settings.quest_guild_target
                            hadiah = config.settings.quest_guild_hadiah
                            berakhir = senin_depan_utc().isoformat()
                            conn.execute(
                                "INSERT INTO quest_guild (guild_id, nama, target, progres,"
                                " hadiah, berakhir, selesai) VALUES (?, ?, ?, 0, ?, ?, 0)",
                                (
                                    guild.id,
                                    f"Kirim {target:,} pesan minggu ini!".replace(",", "."),
                                    target, hadiah, berakhir,
                                ),
                            )
                            conn.commit()
                            log.info("Quest guild baru dibuat untuk guild %s", guild.id)
                except Exception:
                    log.exception("Gagal buat quest guild %s", guild.id)
        except Exception:
            log.exception("Gagal loop quest mingguan")

    @loop_quest_mingguan.before_loop
    async def _before_quest(self):
        await self.bot.wait_until_ready()

    # ---------- Daily question ----------

    @tasks.loop(hours=1)
    async def loop_dailyq(self):
        """Kirim pertanyaan harian (idempoten per tanggal)."""
        ch_id = config.settings.dailyq_channel_id
        if not ch_id:
            return
        channel = self.bot.get_channel(ch_id)
        if channel is None:
            return
        gid = channel.guild.id if channel.guild else 0
        tanggal = discord.utils.utcnow().strftime("%Y-%m-%d")
        try:
            with get_connection() as conn:
                ada = conn.execute(
                    "SELECT 1 FROM dailyq WHERE guild_id = ? AND tanggal = ?",
                    (gid, tanggal),
                ).fetchone()
                if ada:
                    return
                tanya = pertanyaan_tanggal(tanggal, gid)
                conn.execute(
                    "INSERT OR IGNORE INTO dailyq (guild_id, tanggal, pertanyaan)"
                    " VALUES (?, ?, ?)",
                    (gid, tanggal, tanya),
                )
                conn.commit()
            embed = finch_embed("❓ Pertanyaan Hari Ini", tanya, warna="game")
            embed.add_field(
                name="Hadiah",
                value=f"{koin_text(config.settings.dailyq_reward)} untuk "
                      f"**{config.settings.dailyq_maks}** penjawab pertama!",
                inline=True,
            )
            await channel.send(embed=embed)
            log.info("Daily question dikirim ke channel %s", ch_id)
        except Exception:
            log.exception("Gagal kirim daily question")

    @loop_dailyq.before_loop
    async def _before_dailyq(self):
        await self.bot.wait_until_ready()

    async def _proses_dailyq(self, message: discord.Message, gid: int, uid: int) -> None:
        """Reward penjawab daily question (maks N pertama per hari)."""
        if message.content.startswith(config.settings.prefix):
            return
        tanggal = discord.utils.utcnow().strftime("%Y-%m-%d")
        with get_connection() as conn:
            # BEGIN IMMEDIATE: serialkan cek-cap + INSERT. Tanpa ini dua penjawab
            # bersamaan bisa sama-sama lolos cek `jumlah < maks` lalu keduanya
            # dapat reward (melebihi kuota).
            try:
                conn.execute("BEGIN IMMEDIATE")
            except sqlite3.OperationalError:
                pass
            try:
                row = conn.execute(
                    "SELECT pertanyaan FROM dailyq WHERE guild_id = ? AND tanggal = ?",
                    (gid, tanggal),
                ).fetchone()
                if not row:
                    conn.execute(
                        "INSERT OR IGNORE INTO dailyq (guild_id, tanggal, pertanyaan)"
                        " VALUES (?, ?, ?)",
                        (gid, tanggal, pertanyaan_tanggal(tanggal, gid)),
                    )
                sudah = conn.execute(
                    "SELECT 1 FROM dailyq_jawab WHERE guild_id = ? AND tanggal = ? AND user_id = ?",
                    (gid, tanggal, uid),
                ).fetchone()
                if sudah:
                    conn.rollback()
                    return
                jumlah = conn.execute(
                    "SELECT COUNT(*) FROM dailyq_jawab WHERE guild_id = ? AND tanggal = ?",
                    (gid, tanggal),
                ).fetchone()[0]
                if jumlah >= config.settings.dailyq_maks:
                    conn.rollback()
                    return
                conn.execute(
                    "INSERT INTO dailyq_jawab (guild_id, tanggal, user_id) VALUES (?, ?, ?)",
                    (gid, tanggal, uid),
                )
                conn.commit()
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise
            reward = config.settings.dailyq_reward
            if reward > 0:
                eko.tambah_koin(conn, gid, uid, reward)
                log.info("DailyQ: +%d koin untuk user %s", reward, uid)

    # ---------- Hall of fame ----------

    @commands.hybrid_command(
        name="hof", description="Hall of fame: pesan terbanyak ⭐"
    )
    async def hof(self, ctx: commands.Context):
        """Hall of fame starboard: /hof"""
        if ctx.guild is None:
            await ctx.send(embed=error_embed("Hanya bisa di server."), ephemeral=True)
            return
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT message_id, channel_id FROM starboard LIMIT 50"
            ).fetchall()
        kandidat: list[tuple[int, discord.Message]] = []
        for msg_id, ch_id in rows:
            try:
                ch = self.bot.get_channel(ch_id)
                if ch is None or getattr(ch, "guild", None) != ctx.guild:
                    continue
                msg = await ch.fetch_message(msg_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                continue
            except Exception:
                continue
            bintang = 0
            try:
                for r in msg.reactions:
                    if str(r.emoji) == "⭐":
                        bintang = r.count
                        break
            except Exception:
                continue
            kandidat.append((bintang, msg))
        kandidat.sort(key=lambda x: x[0], reverse=True)
        top = [k for k in kandidat if k[0] > 0][:5]
        if not top:
            await ctx.send(
                embed=finch_embed(
                    "🏆 Hall of Fame",
                    "Belum ada pesan berbintang minggu ini.\nKasih ⭐ ke pesan keren biar masuk sini!",
                    warna="event",
                ),
                ephemeral=True,
            )
            return
        embed = finch_embed(
            "🏆 Hall of Fame", "Pesan paling bersinar di server! ✨", warna="event"
        )
        medali = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
        for i, (bintang, msg) in enumerate(top):
            isi = (msg.content or "[lampiran/embed]").strip().replace("\n", " ")[:80]
            embed.add_field(
                name=f"{medali[i]} {bintang}⭐",
                value=f"{msg.author.mention}\n> {isi}",
                inline=True,
            )
        await ctx.send(embed=embed)

    # ---------- Listener gabungan ----------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        gid = message.guild.id
        uid = message.author.id

        # 1) Pet XP (+1 per pesan), umumkan naik level sekali & ringkas
        try:
            with get_connection() as conn:
                row = conn.execute(
                    "SELECT nama, jenis, xp FROM pet WHERE user_id = ? AND guild_id = ?",
                    (uid, gid),
                ).fetchone()
                naik = False
                nama_pet, emoji_pet, lvl_baru = "", "", 0
                if row:
                    nama_pet, jenis, xp = row
                    emoji_pet = JENIS_PET.get(jenis, "🐾")
                    lvl_lama = pet_level(xp)
                    # Increment atomik: dua pesan bersamaan tidak saling menimpa
                    # (dulu: baca xp lalu SET xp+1 — satu XP hilang).
                    conn.execute(
                        "UPDATE pet SET xp = xp + 1 WHERE user_id = ? AND guild_id = ?",
                        (uid, gid),
                    )
                    conn.commit()
                    lvl_baru = pet_level(xp + 1)
                    naik = lvl_baru > lvl_lama
            if naik:
                await message.channel.send(
                    f"🎉 Pet **{nama_pet}** {emoji_pet} naik ke level **{lvl_baru}**!"
                )
        except Exception:
            log.exception("Gagal tambah pet xp")

        # 2) Quest guild: progres +1, selesaikan & umumkan bila tercapai
        try:
            selesai_info = None
            with get_connection() as conn:
                now_iso = discord.utils.utcnow().isoformat()
                row = conn.execute(
                    "SELECT id, target, progres, hadiah FROM quest_guild"
                    " WHERE guild_id = ? AND selesai = 0 AND berakhir > ?"
                    " ORDER BY id DESC LIMIT 1",
                    (gid, now_iso),
                ).fetchone()
                if row:
                    qid = row[0]
                    # Increment atomik: dua pesan bersamaan tidak saling menimpa
                    # progres (dulu: baca progres lalu SET progres+1 — satu hitungan hilang).
                    cur = conn.execute(
                        "UPDATE quest_guild SET progres = progres + 1"
                        " WHERE id = ? AND selesai = 0",
                        (qid,),
                    )
                    if not cur.rowcount:
                        conn.rollback()
                    else:
                        baru, target, hadiah = conn.execute(
                            "SELECT progres, target, hadiah FROM quest_guild WHERE id = ?",
                            (qid,),
                        ).fetchone()
                        if baru >= target:
                            cur2 = conn.execute(
                                "UPDATE quest_guild SET selesai = 1"
                                " WHERE id = ? AND selesai = 0",
                                (qid,),
                            )
                            if cur2.rowcount:
                                conn.execute(
                                    "INSERT INTO server_pool (guild_id, koin) VALUES (?, ?)"
                                    " ON CONFLICT(guild_id) DO UPDATE SET koin = koin + ?",
                                    (gid, hadiah, hadiah),
                                )
                                selesai_info = hadiah
                        conn.commit()
            if selesai_info:
                await message.channel.send(
                    f"🎉 **Quest guild selesai!** Kerja sama keren!\n"
                    f"🎁 Pool giveaway bertambah {koin_text(selesai_info)}."
                )
        except Exception:
            log.exception("Gagal update quest guild")

        # 3) Daily question: reward penjawab di channel khusus
        try:
            ch_id = config.settings.dailyq_channel_id
            if ch_id and message.channel.id == ch_id:
                await self._proses_dailyq(message, gid, uid)
        except Exception:
            log.exception("Gagal proses daily question")

        # 4) Achievement hidden "hantu": chat jam 00:00–04:00 WIB
        try:
            if 0 <= datetime.datetime.now(WIB).hour < 4:
                with get_connection() as conn:
                    dibuka = ach.cek_buka(conn, gid, uid, {"hantu": 1})
                if dibuka:
                    await message.channel.send(
                        ach.embed_pengumuman(message.author.display_name, dibuka)
                    )
        except Exception:
            log.exception("Gagal cek achievement hantu")


async def setup(bot: commands.Bot):
    await bot.add_cog(Engagement(bot))
