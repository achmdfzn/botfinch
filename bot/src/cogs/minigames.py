"""Mini-games koin (/game): coinflip, slot, tebakangka, trivia, blackjack, dadu, rps, maling, susunkata.

- `/game coinflip <taruhan> <kepala|ekor>` — menang 2x
- `/game slot <taruhan>` — 3 sehati bayar 5x (💎 8x, 7️⃣ 10x), 2 sehati 2x
- `/game tebakangka <taruhan> <1-10>` — tepat dapat 9x
- `/game trivia` — kuis 4 pilihan, benar +koin (cooldown dari config)
- `/game blackjack <taruhan>` — lawan bandar (blackjack 2.5x, menang 2x, seri refund)
- `/game dadu <taruhan> <1-6>` — tepat 5x
- `/game rps <taruhan> <gunting|batu|kertas>` — menang 2x, seri refund
- `/game maling <target>` — 60% curi koin target; gagal = denda
- `/game susunkata` — susun huruf, tercepat +koin
- `/game top` — top 10 pemenang trivia
"""
import random
import time
import logging

import discord
from discord.ext import commands

from src import config
from src.store import get_connection
from src.utils import achievement as ach
from src.utils import consumable as cons
from src.utils import economy as eko
from src.utils.toggle import cek_toggle
from src.utils.embeds import base_embed, finch_embed
from src.utils.teks import acak_huruf
from src.utils.views import TimeoutSafeView, bind_view_message

log = logging.getLogger("finch")

# --- logika murni (gampang dites) ---
SLOT_SIMBOL = ["🍒", "🍋", "🔔", "⭐", "💎", "7️⃣"]
TEBAK_MAX = 10
TEBAK_MULT = 9


def putar_slot(rng=None) -> list[str]:
    rng = rng or random
    return [rng.choice(SLOT_SIMBOL) for _ in range(3)]


def bayar_slot(simbol: list[str], taruhan: int) -> int:
    """Return total koin kembali (0 = kalah)."""
    a, b, c = simbol
    if a == b == c:
        mult = 10 if a == "7️⃣" else 8 if a == "💎" else 5
        return taruhan * mult
    if a == b or b == c or a == c:
        return taruhan * 2
    return 0


def lempar_koin(rng=None) -> str:
    rng = rng or random
    return rng.choice(["kepala", "ekor"])


def undi_tebak(rng=None) -> int:
    rng = rng or random
    return rng.randint(1, TEBAK_MAX)


# --- blackjack (murni) ---
BJ_RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
BJ_SUITS = ["♠", "♥", "♦", "♣"]


def buat_dek(rng=None) -> list[tuple[str, str]]:
    """52 kartu unik (rank, suit), diacak."""
    rng = rng or random
    dek = [(r, s) for s in BJ_SUITS for r in BJ_RANKS]
    rng.shuffle(dek)
    return dek


def nilai_tangan(kartu: list[tuple[str, str]]) -> int:
    """Nilai blackjack; As = 11, turun jadi 1 kalau bust."""
    total, as_ = 0, 0
    for rank, _suit in kartu:
        if rank == "A":
            as_ += 1
            total += 11
        elif rank in ("J", "Q", "K"):
            total += 10
        else:
            total += int(rank)
    while total > 21 and as_:
        total -= 10
        as_ -= 1
    return total


def fmt_kartu(kartu: list[tuple[str, str]]) -> str:
    return " ".join(f"`{r}{s}`" for r, s in kartu)


# --- susun kata (murni) ---
SUSUNKATA_BANK = [
    "kucing", "komputer", "sepeda", "jendela", "gunung", "pantai",
    "sekolah", "bulan", "bintang", "hujan", "kopi", "telepon",
    "kertas", "meja", "kursi", "pohon", "sungai", "pasar",
    "toko", "rumah",
]


def acak_kata(kata: str, rng=None) -> str:
    """Acak huruf; hasil != kata asli (huruf tetap sama)."""
    return acak_huruf(kata, rng)


# --- rps (murni) ---
RPS_PILIHAN = ["gunting", "batu", "kertas"]
RPS_MENANG = {"gunting": "kertas", "kertas": "batu", "batu": "gunting"}


def hasil_rps(pemain: str, bot: str) -> str:
    """'menang' | 'kalah' | 'seri' dari sudut pandang pemain."""
    if pemain == bot:
        return "seri"
    return "menang" if RPS_MENANG[pemain] == bot else "kalah"


# --- state in-memory (cooldown & game aktif) ---
_maling_cd: dict[int, float] = {}
_susunkata_cd: dict[int, float] = {}
_susunkata_aktif: dict[int, tuple[str, float]] = {}  # channel_id -> (jawaban, ends_at)


def _evict_terbatas(d: dict, batas: int = 1000) -> None:
    while len(d) > batas:
        d.pop(next(iter(d)))


TRIVIA_SOAL: list[tuple[str, list[str], int]] = [
    ("Apa ibukota Indonesia?", ["Jakarta", "Bandung", "Surabaya", "Medan"], 0),
    ("Tanggal berapa Hari Kemerdekaan Indonesia?", ["17 Agustus", "20 Mei", "1 Juni", "10 November"], 0),
    ("Planet terdekat dari Matahari?", ["Merkurius", "Venus", "Mars", "Bumi"], 0),
    ("Rumus kimia air?", ["H2O", "CO2", "O2", "NaCl"], 0),
    ("Sila pertama Pancasila?", ["Ketuhanan Yang Maha Esa", "Kemanusiaan yang adil", "Persatuan Indonesia", "Keadilan sosial"], 0),
    ("Mata uang Jepang?", ["Yen", "Won", "Dolar", "Euro"], 0),
    ("Benua terbesar di dunia?", ["Asia", "Afrika", "Amerika", "Eropa"], 0),
    ("Jumlah pemain sepak bola satu tim?", ["11", "9", "10", "12"], 0),
    ("Siapa presiden pertama RI?", ["Soekarno", "Soeharto", "Jokowi", "Habibie"], 0),
    ("Berapakah 2 + 2 × 3?", ["8", "10", "12", "6"], 0),
    ("Hewan darat tercepat?", ["Cheetah", "Kuda", "Singa", "Kijang"], 0),
    ("Ibukota Jawa Barat?", ["Bandung", "Bogor", "Depok", "Bekasi"], 0),
    ("Satu windu berapa tahun?", ["8", "5", "10", "12"], 0),
    ("Lambang sila ke-3 Pancasila?", ["Pohon beringin", "Banteng", "Padi dan kapas", "Bintang"], 0),
    ("Game buatan Mojang?", ["Minecraft", "Fortnite", "Roblox", "GTA"], 0),
    ("Warna bendera Indonesia dari atas ke bawah?", ["Merah-Putih", "Putih-Merah", "Merah-Biru", "Hijau-Putih"], 0),
]


class TriviaView(TimeoutSafeView):
    def __init__(self, author_id: int, kunci: int, hadiah: int):
        super().__init__(timeout=30)
        self.author_id = author_id
        self.kunci = kunci
        self.hadiah = hadiah
        self.selesai = False

    async def _jawab(self, interaction: discord.Interaction, pilih: int):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "❌ Ini kuis orang lain.", ephemeral=True
            )
            return
        if self.selesai:
            return
        self.selesai = True
        for item in self.children:
            item.disabled = True
        benar = pilih == self.kunci
        dibuka: list[tuple[str, str]] = []
        hadiah_diberi = 0
        if benar and self.hadiah > 0:
            from src.cogs.dashboard_sync import modul_aktif

            gid = interaction.guild.id if interaction.guild else 0
            if modul_aktif(gid, "economy_enabled"):
                with get_connection() as conn:
                    eko.tambah_koin(conn, gid, self.author_id, self.hadiah)
                    row = conn.execute(
                        "SELECT COALESCE(trivia_menang, 0) FROM economy WHERE user_id = ? AND guild_id = ?",
                        (self.author_id, gid),
                    ).fetchone()
                    n = (row[0] if row else 0) + 1
                    conn.execute(
                        "UPDATE economy SET trivia_menang = ? WHERE user_id = ? AND guild_id = ?",
                        (n, self.author_id, gid),
                    )
                    conn.commit()
                    dibuka = ach.cek_buka(conn, gid, self.author_id, {"trivia": n})
                hadiah_diberi = self.hadiah
        if benar:
            teks = (
                f"✅ **Benar!** +{hadiah_diberi} 🪙"
                if hadiah_diberi
                else "✅ **Benar!** (modul ekonomi dimatikan — tanpa hadiah)"
            )
        else:
            teks = f"❌ Salah! Jawaban benar: **{chr(65 + self.kunci)}**"
        try:
            await interaction.response.edit_message(content=teks, view=self)
        except discord.HTTPException:
            pass
        if dibuka:
            try:
                await interaction.channel.send(
                    ach.embed_pengumuman(interaction.user.display_name, dibuka)
                )
            except (discord.HTTPException, AttributeError):
                pass
        self.stop()

    @discord.ui.button(label="A", style=discord.ButtonStyle.primary)
    async def btn_a(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._jawab(interaction, 0)

    @discord.ui.button(label="B", style=discord.ButtonStyle.primary)
    async def btn_b(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._jawab(interaction, 1)

    @discord.ui.button(label="C", style=discord.ButtonStyle.primary)
    async def btn_c(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._jawab(interaction, 2)

    @discord.ui.button(label="D", style=discord.ButtonStyle.primary)
    async def btn_d(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._jawab(interaction, 3)


class BlackjackView(TimeoutSafeView):
    def __init__(self, author_id: int, taruhan: int, guild_id: int):
        super().__init__(timeout=60)
        self.author_id = author_id
        self.taruhan = taruhan
        self.guild_id = guild_id
        self.dek = buat_dek()
        self.player = [self.dek.pop(), self.dek.pop()]
        self.dealer = [self.dek.pop(), self.dek.pop()]
        self.selesai = False

    def _embed_jalan(self, buka_dealer: bool = False) -> discord.Embed:
        if buka_dealer:
            ket = f"Bandar: {fmt_kartu(self.dealer)} = **{nilai_tangan(self.dealer)}**\n"
        else:
            r, s = self.dealer[0]
            ket = f"Bandar: `{r}{s}` `❓`\n"
        return base_embed(
            "🃏 Blackjack",
            f"{ket}Kamu: {fmt_kartu(self.player)} = **{nilai_tangan(self.player)}**\n"
            f"Taruhan: **{self.taruhan}** 🪙",
        )

    def _main_dealer(self) -> None:
        while nilai_tangan(self.dealer) < 17:
            self.dealer.append(self.dek.pop())

    def _selesaikan(self) -> tuple[str, int]:
        """Return (hasil, payout)."""
        self._main_dealer()
        np, nd = nilai_tangan(self.player), nilai_tangan(self.dealer)
        if len(self.player) == 2 and np == 21:
            return "blackjack", int(self.taruhan * 2.5)
        if np > 21:
            return "kalah", 0
        if nd > 21:
            return "menang", self.taruhan * 2
        if np > nd:
            return "menang", self.taruhan * 2
        if np < nd:
            return "kalah", 0
        return "seri", self.taruhan

    async def _tutup(self, target, via_interaction: bool = True) -> None:
        if self.selesai:
            return
        self.selesai = True
        for item in self.children:
            item.disabled = True
        hasil, payout = self._selesaikan()
        from src.cogs.dashboard_sync import modul_aktif

        ekonomi_mati = not modul_aktif(self.guild_id, "economy_enabled")
        if ekonomi_mati and hasil in ("blackjack", "menang"):
            # Modul dimatikan di tengah permainan: kemenangan tidak dibayar.
            # (Seri tetap refund — itu koin pemain sendiri, bukan hadiah.)
            payout = 0
        if payout > 0:
            with get_connection() as conn:
                eko.tambah_koin(conn, self.guild_id, self.author_id, payout)
        teks_hasil = {
            "blackjack": f"🎉 **BLACKJACK!** +**{payout}** 🪙!",
            "menang": f"🎉 Menang! +**{payout}** 🪙!",
            "kalah": f"😅 Kalah... -**{self.taruhan}** 🪙",
            "seri": "🤝 Seri! Taruhan kembali.",
        }[hasil]
        if ekonomi_mati and hasil in ("blackjack", "menang"):
            teks_hasil += "\n_(modul ekonomi dimatikan — kemenangan tanpa hadiah)_"
        embed = self._embed_jalan(buka_dealer=True)
        embed.description += f"\n{teks_hasil}"
        try:
            if via_interaction:
                await target.response.edit_message(embed=embed, view=self)
            else:
                await target.edit(embed=embed, view=self)
        except discord.HTTPException:
            pass
        self.stop()

    async def _cek_user(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "❌ Ini permainan orang lain.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary)
    async def hit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._cek_user(interaction) or self.selesai:
            return
        self.player.append(self.dek.pop())
        if nilai_tangan(self.player) >= 21:
            await self._tutup(interaction)
        else:
            try:
                await interaction.response.edit_message(embed=self._embed_jalan(), view=self)
            except discord.HTTPException:
                pass

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.success)
    async def stand(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._cek_user(interaction):
            return
        await self._tutup(interaction)

    async def on_timeout(self) -> None:
        if self.selesai:
            await super().on_timeout()
            return
        if self.message is not None:
            # timeout = stand otomatis
            await self._tutup(self.message, via_interaction=False)
        else:
            await super().on_timeout()



def _cek_taruhan(balance: int, taruhan: int) -> str | None:
    """Return pesan error, atau None kalau taruhan valid."""
    s = config.settings
    if taruhan < s.economy_min_bet:
        return f"❌ Taruhan minimal **{s.economy_min_bet}** koin."
    if taruhan > s.economy_max_bet:
        return f"❌ Taruhan maksimal **{s.economy_max_bet}** koin."
    if taruhan > balance:
        return "❌ Koin kamu tidak cukup."
    return None


class MiniGames(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_check(self, ctx: commands.Context) -> bool:
        """Minigames memakai koin — bagian modul Ekonomi, ikut `economy_enabled`."""
        return await cek_toggle(
            ctx, "economy_enabled", "Modul ekonomi dimatikan oleh admin server ini."
        )

    @commands.hybrid_group(name="game", description="🎮 Game Finch")
    async def game(self, ctx: commands.Context):
        """Bantuan grup game."""
        await ctx.send(
            embed=finch_embed(
                "🎮 Game",
                "`/game coinflip` — tebak koin 2x\n`/game slot` — mesin slot\n`/game tebakangka` — tebak 1-10 (9x)\n`/game trivia` — kuis berhadiah\n`/game top` — top 10 trivia\n`/game blackjack` — blackjack 2.5x\n`/game dadu` — tebak dadu 5x\n`/game rps` — gunting-batu-kertas\n`/game maling` — curi koin (60%)\n`/game susunkata` — susun huruf tercepat",
                warna="game",
            ),
            ephemeral=True,
        )
    @game.command(name="coinflip", description="Tebak koin: kepala atau ekor (menang 2x)")
    @discord.app_commands.describe(taruhan="Jumlah koin taruhan", pilihan="kepala atau ekor")
    @discord.app_commands.choices(pilihan=[
        discord.app_commands.Choice(name="kepala", value="kepala"),
        discord.app_commands.Choice(name="ekor", value="ekor"),
    ])
    async def coinflip(self, ctx: commands.Context, taruhan: int, pilihan: str):
        """Coinflip: /game coinflip <taruhan> <kepala|ekor>"""
        if ctx.guild is None:
            await ctx.send("❌ Hanya bisa di server.", ephemeral=True)
            return
        with get_connection() as conn:
            akun = eko.get_akun(conn, ctx.guild.id, ctx.author.id)
            err = _cek_taruhan(akun["balance"], taruhan)
            if err:
                await ctx.send(err, ephemeral=True)
                return
            if eko.kurang_koin(conn, ctx.guild.id, ctx.author.id, taruhan) is None:
                await ctx.send("❌ Koin kamu tidak cukup.", ephemeral=True)
                return
        hasil = lempar_koin()
        menang = hasil == pilihan
        if menang:
            with get_connection() as conn:
                eko.tambah_koin(conn, ctx.guild.id, ctx.author.id, taruhan * 2)
        embed = base_embed(
            "🪙 Coinflip",
            f"Hasil: **{hasil}**\n"
            + (f"🎉 Menang! +**{taruhan * 2}** koin!" if menang else f"😅 Kalah... -**{taruhan}** koin."),
        )
        await ctx.send(embed=embed)

    @game.command(name="slot", description="Mesin slot koin")
    @discord.app_commands.describe(taruhan="Jumlah koin taruhan")
    async def slot(self, ctx: commands.Context, taruhan: int):
        """Slot: /game slot <taruhan>"""
        if ctx.guild is None:
            await ctx.send("❌ Hanya bisa di server.", ephemeral=True)
            return
        with get_connection() as conn:
            akun = eko.get_akun(conn, ctx.guild.id, ctx.author.id)
            err = _cek_taruhan(akun["balance"], taruhan)
            if err:
                await ctx.send(err, ephemeral=True)
                return
            if eko.kurang_koin(conn, ctx.guild.id, ctx.author.id, taruhan) is None:
                await ctx.send("❌ Koin kamu tidak cukup.", ephemeral=True)
                return
        simbol = putar_slot()
        bayar = bayar_slot(simbol, taruhan)
        if bayar:
            with get_connection() as conn:
                eko.tambah_koin(conn, ctx.guild.id, ctx.author.id, bayar)
        tampilan = " | ".join(simbol)
        embed = base_embed(
            "🎰 Slot",
            f"**{tampilan}**\n"
            + (f"🎉 JACKPOT! +**{bayar}** koin!" if bayar else f"😅 Zonk... -**{taruhan}** koin."),
        )
        await ctx.send(embed=embed)

    @game.command(name="tebakangka", description="Tebak angka 1-10 (tepat = 9x)")
    @discord.app_commands.describe(taruhan="Jumlah koin taruhan", angka="Tebakanmu (1-10)")
    async def tebak_angka(self, ctx: commands.Context, taruhan: int, angka: int):
        """Tebak angka: /game tebakangka <taruhan> <1-10>"""
        if ctx.guild is None:
            await ctx.send("❌ Hanya bisa di server.", ephemeral=True)
            return
        if not 1 <= angka <= TEBAK_MAX:
            await ctx.send(f"❌ Angka harus 1–{TEBAK_MAX}.", ephemeral=True)
            return
        with get_connection() as conn:
            akun = eko.get_akun(conn, ctx.guild.id, ctx.author.id)
            err = _cek_taruhan(akun["balance"], taruhan)
            if err:
                await ctx.send(err, ephemeral=True)
                return
            if eko.kurang_koin(conn, ctx.guild.id, ctx.author.id, taruhan) is None:
                await ctx.send("❌ Koin kamu tidak cukup.", ephemeral=True)
                return
        rahasia = undi_tebak()
        if angka == rahasia:
            hadiah = taruhan * TEBAK_MULT
            with get_connection() as conn:
                eko.tambah_koin(conn, ctx.guild.id, ctx.author.id, hadiah)
            teks = f"🎉 **TEPAT!** Angkanya {rahasia}. +**{hadiah}** koin!"
        else:
            teks = f"😅 Salah! Angkanya **{rahasia}**, tebakanmu {angka}. -**{taruhan}** koin."
        await ctx.send(embed=base_embed("🔢 Tebak Angka", teks))

    @game.command(name="trivia", description="Kuis berhadiah koin")
    async def trivia(self, ctx: commands.Context):
        """Trivia: /game trivia"""
        if ctx.guild is None:
            await ctx.send("❌ Hanya bisa di server.", ephemeral=True)
            return
        s = config.settings
        now = discord.utils.utcnow()
        with get_connection() as conn:
            boleh, sisa = eko.bisa_trivia(conn, ctx.guild.id, ctx.author.id, now, s.economy_trivia_cooldown)
        if not boleh:
            await ctx.send(
                f"⏳ Tunggu **{eko.format_sisa_waktu(sisa)}** untuk trivia berikutnya.",
                ephemeral=True,
            )
            return
        # Catat cooldown SEBELUM await kirim pesan — cegah double-invoke
        # cepat yang sama-sama lolos cek lalu klaim reward 2x.
        with get_connection() as conn:
            eko.catat_trivia(conn, ctx.guild.id, ctx.author.id, now)
        soal, opsi, kunci = random.choice(TRIVIA_SOAL)
        view = TriviaView(ctx.author.id, kunci, s.economy_trivia_reward)
        teks_opsi = "\n".join(f"**{chr(65 + i)}.** {o}" for i, o in enumerate(opsi))
        msg = await ctx.send(
            embed=base_embed("🧠 Trivia", f"{soal}\n\n{teks_opsi}\n\n*30 detik!*"),
            view=view,
        )
        await bind_view_message(ctx, view, msg)

    @game.command(name="top", description="Top 10 pemenang trivia")
    async def trivia_top(self, ctx: commands.Context):
        """Top trivia: /game top"""
        gid = ctx.guild.id if ctx.guild else 0
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT user_id, COALESCE(trivia_menang, 0) FROM economy"
                " WHERE guild_id = ? AND COALESCE(trivia_menang, 0) > 0"
                " ORDER BY trivia_menang DESC, user_id ASC LIMIT 10",
                (gid,),
            ).fetchall()
        if not rows:
            await ctx.send("Belum ada pemenang trivia.", ephemeral=True)
            return
        medals = ["🥇", "🥈", "🥉"]
        baris = []
        for i, (uid, n) in enumerate(rows):
            medal = medals[i] if i < 3 else f"`{i + 1}.`"
            baris.append(f"{medal} <@{uid}> — **{n}**x 🧠")
        embed = base_embed("🏆 Top Trivia")
        embed.add_field(name="Peringkat 1–5", value="\n".join(baris[:5]) or "-", inline=True)
        embed.add_field(name="Peringkat 6–10", value="\n".join(baris[5:]) or "-", inline=True)
        await ctx.send(embed=embed)

    @game.command(name="blackjack", description="Blackjack lawan bandar (blackjack 2.5x)")
    @discord.app_commands.describe(taruhan="Jumlah koin taruhan")
    async def blackjack(self, ctx: commands.Context, taruhan: int):
        """Blackjack: /game blackjack <taruhan>"""
        if ctx.guild is None:
            await ctx.send("❌ Hanya bisa di server.", ephemeral=True)
            return
        with get_connection() as conn:
            akun = eko.get_akun(conn, ctx.guild.id, ctx.author.id)
            err = _cek_taruhan(akun["balance"], taruhan)
            if err:
                await ctx.send(err, ephemeral=True)
                return
            if eko.kurang_koin(conn, ctx.guild.id, ctx.author.id, taruhan) is None:
                await ctx.send("❌ Koin kamu tidak cukup.", ephemeral=True)
                return
        view = BlackjackView(ctx.author.id, taruhan, ctx.guild.id)
        msg = await ctx.send(embed=view._embed_jalan(), view=view)
        await bind_view_message(ctx, view, msg)

    @game.command(name="dadu", description="Tebak dadu 1-6 (tepat = 5x)")
    @discord.app_commands.describe(taruhan="Jumlah koin taruhan", angka="Tebakanmu (1-6)")
    async def dadu(self, ctx: commands.Context, taruhan: int, angka: int):
        """Dadu: /game dadu <taruhan> <1-6>"""
        if ctx.guild is None:
            await ctx.send("❌ Hanya bisa di server.", ephemeral=True)
            return
        if not 1 <= angka <= 6:
            await ctx.send("❌ Angka harus 1–6.", ephemeral=True)
            return
        with get_connection() as conn:
            akun = eko.get_akun(conn, ctx.guild.id, ctx.author.id)
            err = _cek_taruhan(akun["balance"], taruhan)
            if err:
                await ctx.send(err, ephemeral=True)
                return
            if eko.kurang_koin(conn, ctx.guild.id, ctx.author.id, taruhan) is None:
                await ctx.send("❌ Koin kamu tidak cukup.", ephemeral=True)
                return
        hasil = random.randint(1, 6)
        if angka == hasil:
            hadiah = taruhan * 5
            with get_connection() as conn:
                eko.tambah_koin(conn, ctx.guild.id, ctx.author.id, hadiah)
            teks = f"🎲 Dadu: **{hasil}**\n🎉 **TEPAT!** +**{hadiah}** 🪙!"
        else:
            teks = f"🎲 Dadu: **{hasil}**\n😅 Tebakanmu {angka}. -**{taruhan}** 🪙"
        await ctx.send(embed=base_embed("🎲 Dadu", teks))

    @game.command(name="rps", description="Gunting-batu-kertas vs bot (menang 2x)")
    @discord.app_commands.describe(taruhan="Jumlah koin taruhan", pilihan="gunting, batu, atau kertas")
    @discord.app_commands.choices(pilihan=[
        discord.app_commands.Choice(name="gunting", value="gunting"),
        discord.app_commands.Choice(name="batu", value="batu"),
        discord.app_commands.Choice(name="kertas", value="kertas"),
    ])
    async def rps(self, ctx: commands.Context, taruhan: int, pilihan: str):
        """RPS: /game rps <taruhan> <gunting|batu|kertas>"""
        if ctx.guild is None:
            await ctx.send("❌ Hanya bisa di server.", ephemeral=True)
            return
        if pilihan not in RPS_PILIHAN:
            await ctx.send("❌ Pilihan: gunting, batu, atau kertas.", ephemeral=True)
            return
        with get_connection() as conn:
            akun = eko.get_akun(conn, ctx.guild.id, ctx.author.id)
            err = _cek_taruhan(akun["balance"], taruhan)
            if err:
                await ctx.send(err, ephemeral=True)
                return
            if eko.kurang_koin(conn, ctx.guild.id, ctx.author.id, taruhan) is None:
                await ctx.send("❌ Koin kamu tidak cukup.", ephemeral=True)
                return
        bot_pilih = random.choice(RPS_PILIHAN)
        hasil = hasil_rps(pilihan, bot_pilih)
        emoji = {"gunting": "✌️", "batu": "✊", "kertas": "✋"}
        if hasil == "menang":
            hadiah = taruhan * 2
            with get_connection() as conn:
                eko.tambah_koin(conn, ctx.guild.id, ctx.author.id, hadiah)
            teks = f"{emoji[pilihan]} vs {emoji[bot_pilih]}\n🎉 Kamu menang! +**{hadiah}** 🪙!"
        elif hasil == "seri":
            with get_connection() as conn:
                eko.tambah_koin(conn, ctx.guild.id, ctx.author.id, taruhan)
            teks = f"{emoji[pilihan]} vs {emoji[bot_pilih]}\n🤝 Seri! Taruhan kembali."
        else:
            teks = f"{emoji[pilihan]} vs {emoji[bot_pilih]}\n😅 Kamu kalah... -**{taruhan}** 🪙"
        await ctx.send(embed=base_embed("✌️ Gunting Batu Kertas", teks))

    @game.command(name="maling", description="Coba curi koin member (60% sukses)")
    @discord.app_commands.describe(target="Target curian")
    async def maling(self, ctx: commands.Context, target: discord.Member):
        """Maling: /game maling @user"""
        if ctx.guild is None:
            await ctx.send("❌ Hanya bisa di server.", ephemeral=True)
            return
        if target.bot:
            await ctx.send("❌ Tidak bisa maling dari bot.", ephemeral=True)
            return
        if target.id == ctx.author.id:
            await ctx.send("❌ Tidak bisa maling dari diri sendiri.", ephemeral=True)
            return
        # Perisai Anti-Maling (Tahap 12): target kebal
        with get_connection() as conn:
            if cons.punya_aktif(conn, ctx.guild.id, target.id, "perisai"):
                await ctx.send(
                    f"🛡️ {target.mention} dilindungi **Perisai Anti-Maling**!"
                    " Cari target lain.",
                    ephemeral=True,
                )
                return
        now = time.time()
        cd = config.settings.maling_cooldown
        sisa = cd - (now - _maling_cd.get(ctx.author.id, 0))
        if sisa > 0:
            await ctx.send(
                f"🥷 Tunggu **{eko.format_sisa_waktu(int(sisa))}** sebelum maling lagi.",
                ephemeral=True,
            )
            return
        with get_connection() as conn:
            akun_t = eko.get_akun(conn, ctx.guild.id, target.id)
            if akun_t["balance"] < 100:
                await ctx.send(
                    "❌ Target terlalu miskin untuk dicuri (min 100 koin).",
                    ephemeral=True,
                )
                return
            # Bonus job maling: +10% peluang (fitur job, sebelumnya tidak dipakai)
            try:
                from src.utils import job as jobmod
                peluang = 0.6 + jobmod.bonus_untuk(conn, ctx.guild.id, ctx.author.id).get(
                    "bonus_maling", 0
                )
            except Exception:
                log.exception("Gagal baca bonus job maling untuk %s", ctx.author.id)
                peluang = 0.6
            sukses = random.random() < peluang
            curi = 0
            if sukses:
                curi = min(max(10, akun_t["balance"] * 10 // 100), 1000)
                # Cek return: koin target bisa habis tepat di tengah (race
                # dengan pencurian/pengeluaran lain) — jangan cetak koin gratis.
                if eko.kurang_koin(conn, ctx.guild.id, target.id, curi) is None:
                    sukses = False  # target keburu miskin → pencurian gagal
                    curi = 0
                else:
                    eko.tambah_koin(conn, ctx.guild.id, ctx.author.id, curi)
        _maling_cd[ctx.author.id] = now
        _evict_terbatas(_maling_cd)
        if sukses:
            await ctx.send(
                embed=base_embed(
                    "🥷 Maling Berhasil!",
                    f"Kamu mencuri **{curi}** 🪙 dari {target.mention}! Kabur! 🏃",
                )
            )
            return
        denda = 0
        with get_connection() as conn:
            if eko.kurang_koin(conn, ctx.guild.id, ctx.author.id, 150) is not None:
                eko.tambah_koin(conn, ctx.guild.id, target.id, 150)
                denda = 150
        teks = f"🚨 Ketahuan! {target.mention} memergokimu!"
        if denda:
            teks += f"\nKamu didenda **{denda}** 🪙."
        else:
            teks += "\nUntung kamu tidak punya 150 koin untuk didenda. 😅"
        await ctx.send(embed=base_embed("🚨 Maling Gagal!", teks))

    @game.command(name="susunkata", description="Susun huruf acak, tercepat dapat koin")
    async def susun_kata(self, ctx: commands.Context):
        """Susun kata: /game susunkata"""
        if ctx.guild is None:
            await ctx.send("❌ Hanya bisa di server.", ephemeral=True)
            return
        now = time.time()
        cd = config.settings.susunkata_cooldown
        sisa = cd - (now - _susunkata_cd.get(ctx.author.id, 0))
        if sisa > 0:
            await ctx.send(
                f"⏳ Tunggu **{eko.format_sisa_waktu(int(sisa))}** untuk main lagi.",
                ephemeral=True,
            )
            return
        st = _susunkata_aktif.get(ctx.channel.id)
        if st and st[1] > now:
            await ctx.send("❌ Sudah ada permainan aktif di channel ini.", ephemeral=True)
            return
        kata = random.choice(SUSUNKATA_BANK)
        acak = acak_kata(kata)
        _susunkata_aktif[ctx.channel.id] = (kata.lower(), now + 60)
        _susunkata_cd[ctx.author.id] = now
        _evict_terbatas(_susunkata_cd)
        _evict_terbatas(_susunkata_aktif, 500)
        await ctx.send(
            embed=base_embed(
                "🔤 Susun Kata",
                f"Susun huruf ini jadi kata yang benar:\n# **{acak}**\n\n"
                f"*60 detik! Hadiah: **{config.settings.susunkata_reward}** 🪙*",
            )
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        st = _susunkata_aktif.get(message.channel.id)
        if not st:
            return
        from src.cogs.dashboard_sync import modul_aktif

        if not modul_aktif(message.guild.id, "economy_enabled"):
            # Modul ekonomi dimatikan di tengah permainan: hentikan tanpa
            # memberi koin agar toggle dashboard benar-benar berlaku.
            _susunkata_aktif.pop(message.channel.id, None)
            try:
                await message.channel.send(
                    "🔤 Permainan dihentikan: modul ekonomi dimatikan oleh admin server ini."
                )
            except discord.HTTPException:
                pass
            return
        jawaban, ends_at = st
        now = time.time()
        if now > ends_at:
            _susunkata_aktif.pop(message.channel.id, None)
            try:
                await message.channel.send(f"⏰ Waktu habis! Jawabannya: **{jawaban}**")
            except discord.HTTPException:
                pass
            return
        if message.content.strip().lower() == jawaban:
            _susunkata_aktif.pop(message.channel.id, None)
            hadiah = config.settings.susunkata_reward
            if hadiah > 0:
                with get_connection() as conn:
                    eko.tambah_koin(conn, message.guild.id, message.author.id, hadiah)
            try:
                await message.channel.send(
                    f"🎉 {message.author.mention} benar! +**{hadiah}** 🪙"
                )
            except discord.HTTPException:
                pass


async def setup(bot: commands.Bot):
    await bot.add_cog(MiniGames(bot))
