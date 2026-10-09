"""Ekonomi+ Tahap 12 — trade, toko item, pinjaman, deposito, saham, peti misteri.

- `/dagang trade @user <koin>` — tukar koin P2P dengan escrow + tombol Terima/Tolak
- `/dagang toko`, `/dagang tas`, `/dagang pakai` — consumable (perisai, xpboost, tiket lotre)
- `/dagang pinjam`, `/dagang lunasi`, `/dagang info-pinjaman` — pinjaman berbunga + auto-debit harian
- `/dagang deposito`, `/dagang info-deposito` — kunci koin, panen pokok + bunga saat jatuh tempo
- `/dagang saham`, `/dagang beli`, `/dagang jual` — saham mainan, harga fluktuatif
- `/dagang peti` — peti misteri harian
"""
import datetime
import logging
import random

import discord
from discord.ext import commands, tasks

from src import config
from src.cogs.economy import _minggu_ini
from src.store import get_connection
from src.utils import consumable as cons
from src.utils.waktu import parse_iso
from src.utils import economy as eko
from src.utils.embeds import finch_embed, koin_text, error_embed, sukses_embed

log = logging.getLogger("finch")

SAHAM_AWAL = {"FINC": 100, "PION": 250, "NUSA": 500, "OUTP": 1000}


# ---------- fungsi murni (ada unit test) ----------
def hitung_bunga(sisa: int, bunga_pct: int) -> int:
    """Bunga harian pinjaman (pembulatan ke bawah)."""
    return sisa * bunga_pct // 100


def bunga_deposito(jumlah: int, bunga_pct: int) -> int:
    """Bunga deposito sekali panen."""
    return jumlah * bunga_pct // 100


def harga_saham_baru(harga: int, faktor: float) -> int:
    """Harga saham setelah fluktuasi; minimal 10 koin."""
    return max(10, int(harga * faktor))


def roll_peti(rng=None) -> tuple[str, int | str]:
    """Roll peti misteri: ('koin', jumlah) atau ('item', item_id)."""
    rng = rng or random
    r = rng.random()
    if r < 0.60:
        return ("koin", rng.randint(50, 300))
    if r < 0.85:
        return ("koin", rng.randint(300, 800))
    return ("item", rng.choice(list(cons.ITEMS.keys())))


def hari_valid_deposito(hari: int, pilihan: list[tuple[int, int]]) -> bool:
    """True bila durasi deposito tersedia."""
    return any(h == hari for h, _ in pilihan)


# ---------- view trade ----------
class TradeView(discord.ui.View):
    """Tombol Terima/Tolak untuk /dagang trade.

    Tanpa escrow di muka (anti hangus saat restart): koin pengirim dipotong
    tepat saat target klik Terima. Guard `selesai` di awal tiap handler
    mencegah double-click mencetak koin.
    """

    def __init__(self, guild_id: int, pengirim_id: int, target_id: int, jumlah: int):
        super().__init__(timeout=config.settings.trade_timeout)
        self.guild_id = guild_id
        self.pengirim_id = pengirim_id
        self.target_id = target_id
        self.jumlah = jumlah
        self.selesai = False
        self.message: discord.Message | None = None

    async def _tutup(self, interaction: discord.Interaction, embed: discord.Embed):
        for item in self.children:
            item.disabled = True
        try:
            await interaction.response.edit_message(embed=embed, view=self)
        except discord.HTTPException:
            pass
        self.stop()

    @discord.ui.button(label="Terima", style=discord.ButtonStyle.success)
    async def terima(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.selesai:
            return
        if interaction.user.id != self.target_id:
            await interaction.response.send_message(
                "❌ Tawaran trade ini bukan untukmu.", ephemeral=True
            )
            return
        self.selesai = True  # kunci dulu, baru operasi DB (anti double-click)
        with get_connection() as conn:
            if eko.kurang_koin(conn, self.guild_id, self.pengirim_id, self.jumlah) is None:
                await self._tutup(
                    interaction,
                    error_embed(
                        f"Koin <@{self.pengirim_id}> tidak cukup. Trade dibatalkan."
                    ),
                )
                return
            eko.tambah_koin(conn, self.guild_id, self.target_id, self.jumlah)
        await self._tutup(
            interaction,
            sukses_embed(
                "Trade Berhasil",
                f"<@{self.target_id}> menerima **{koin_text(self.jumlah)}**"
                f" dari <@{self.pengirim_id}>. 🤝",
            ),
        )

    @discord.ui.button(label="Tolak", style=discord.ButtonStyle.danger)
    async def tolak(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.selesai:
            return
        if interaction.user.id != self.target_id:
            await interaction.response.send_message(
                "❌ Tawaran trade ini bukan untukmu.", ephemeral=True
            )
            return
        self.selesai = True
        await self._tutup(
            interaction,
            finch_embed(
                "🚫 Trade Ditolak",
                f"Tawaran **{koin_text(self.jumlah)}** ditolak.",
                warna="info",
            ),
        )

    async def on_timeout(self):
        if self.selesai:
            return
        self.selesai = True
        if self.message is not None:
            for item in self.children:
                item.disabled = True
            try:
                await self.message.edit(
                    embed=finch_embed(
                        "⏰ Trade Kedaluwarsa",
                        f"Tidak ada respons dalam {config.settings.trade_timeout} detik.",
                        warna="info",
                    ),
                    view=self,
                )
            except discord.HTTPException:
                pass


# ---------- view toko ----------
class TokoView(discord.ui.View):
    """Tombol Beli per item di /dagang toko."""

    def __init__(self):
        super().__init__(timeout=120)
        for item_id, info in cons.ITEMS.items():
            btn = discord.ui.Button(
                label=f"Beli {info['nama']}",
                style=discord.ButtonStyle.primary,
                custom_id=f"finch:beli-item:{item_id}",
            )

            async def _cb(interaction: discord.Interaction, iid=item_id):
                await self._beli(interaction, iid)

            btn.callback = _cb
            self.add_item(btn)

    async def _beli(self, interaction: discord.Interaction, item_id: str):
        if interaction.guild_id is None:
            await interaction.response.send_message(
                embed=error_embed("Hanya bisa di server."), ephemeral=True
            )
            return
        info = cons.ITEMS[item_id]
        with get_connection() as conn:
            sisa = eko.kurang_koin(
                conn, interaction.guild_id, interaction.user.id, info["harga"]
            )
            if sisa is None:
                await interaction.response.send_message(
                    embed=error_embed(
                        f"Koin tidak cukup. {info['nama']} harganya"
                        f" **{koin_text(info['harga'])}**."
                    ),
                    ephemeral=True,
                )
                return
            cons.beri_item(conn, interaction.guild_id, interaction.user.id, item_id)
            # Hidden achievement: kolektor (punya 3 consumable berbeda)
            try:
                from src.utils import achievement as ach
                unik = {r[0] for r in cons.daftar_item(conn, interaction.guild_id, interaction.user.id)}
                ach.cek_buka(conn, interaction.guild_id, interaction.user.id, {"kolektor": len(unik)})
            except Exception:
                pass
        await interaction.response.send_message(
            embed=sukses_embed(
                "Item Dibeli",
                f"{info['nama']} masuk inventory. Lihat dengan `/dagang tas`.",
            ),
            ephemeral=True,
        )


# ---------- cog ----------
class EkonomiPlus(commands.Cog):
    """Ekonomi+ Tahap 12."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._harga_lama: dict[str, int] = {}
        self._loop_harian.start()
        self._loop_saham.start()

    def cog_unload(self):
        self._loop_harian.cancel()
        self._loop_saham.cancel()

    async def cog_check(self, ctx: commands.Context) -> bool:
        """Ekonomi+ adalah bagian modul Ekonomi — ikut toggle `economy_enabled`."""
        if ctx.guild is None:
            return True
        from src.cogs.dashboard_sync import modul_aktif

        if modul_aktif(ctx.guild.id, "economy_enabled"):
            return True
        pesan = "Modul ekonomi dimatikan oleh admin server ini."
        try:
            if ctx.interaction is None:
                await ctx.send(pesan)
            elif ctx.interaction.response.is_done():
                await ctx.interaction.followup.send(pesan, ephemeral=True)
            else:
                await ctx.interaction.response.send_message(pesan, ephemeral=True)
        except discord.HTTPException:
            pass
        return False

    # ----- saham: seed & helper -----
    def _pastikan_saham_seed(self):
        """Seed harga awal bila tabel kosong. Aman dipanggil berulang."""
        try:
            with get_connection() as conn:
                kosong = (
                    conn.execute("SELECT COUNT(*) FROM saham_harga").fetchone()[0] == 0
                )
                if kosong:
                    now = discord.utils.utcnow().isoformat()
                    for simbol, harga in SAHAM_AWAL.items():
                        conn.execute(
                            "INSERT OR IGNORE INTO saham_harga (simbol, harga, updated_at)"
                            " VALUES (?, ?, ?)",
                            (simbol, harga, now),
                        )
                    conn.commit()
                    log.info("Seed harga saham awal.")
                for simbol, harga in conn.execute(
                    "SELECT simbol, harga FROM saham_harga"
                ):
                    self._harga_lama.setdefault(simbol, harga)
        except Exception:
            log.exception("Gagal seed harga saham")

    def _harga_saham(self) -> dict[str, int]:
        with get_connection() as conn:
            return dict(conn.execute("SELECT simbol, harga FROM saham_harga"))

    # ----- trade -----
    @commands.hybrid_group(name="dagang", description="💰 Dagang Finch")
    async def dagang(self, ctx: commands.Context):
        """Bantuan grup dagang."""
        await ctx.send(
            embed=finch_embed(
                "💰 Dagang",
                "`/dagang trade` — tukar koin P2P\n`/dagang toko` — beli item consumable\n`/dagang tas` — lihat item milikmu\n`/dagang pakai` — pakai item\n`/dagang pinjam` — pinjam koin berbunga\n`/dagang lunasi` — bayar pinjaman\n`/dagang info-pinjaman` — info pinjaman aktif\n`/dagang deposito` — kunci koin + bunga\n`/dagang info-deposito` — info depositomu\n`/dagang saham` — harga saham\n`/dagang beli` — beli saham\n`/dagang jual` — jual saham\n`/dagang peti` — peti misteri harian",
                warna="ekonomi",
            ),
            ephemeral=True,
        )
    @dagang.command(name="trade", description="Tawar tukar koin ke user lain")
    @discord.app_commands.describe(
        user="Penerima koin", koin="Jumlah koin yang ditawarkan"
    )
    async def trade(self, ctx: commands.Context, user: discord.Member, koin: int):
        """Trade koin: /dagang trade @user 500"""
        if ctx.guild is None:
            await ctx.send(embed=error_embed("Hanya bisa di server."), ephemeral=True)
            return
        if user.id == ctx.author.id:
            await ctx.send(
                embed=error_embed("Tidak bisa trade ke diri sendiri."), ephemeral=True
            )
            return
        if user.bot:
            await ctx.send(
                embed=error_embed("Tidak bisa trade ke bot."), ephemeral=True
            )
            return
        if koin <= 0:
            await ctx.send(
                embed=error_embed("Jumlah koin harus lebih dari 0."), ephemeral=True
            )
            return
        with get_connection() as conn:
            # Validasi saldo saja (tanpa potong): potong saat target klik Terima.
            # Ini anti hangus bila bot restart dalam window tawaran.
            if eko.get_akun(conn, ctx.guild.id, ctx.author.id)["balance"] < koin:
                await ctx.send(
                    embed=error_embed("Koin kamu tidak cukup."), ephemeral=True
                )
                return
        view = TradeView(ctx.guild.id, ctx.author.id, user.id, koin)
        embed = finch_embed(
            "🔄 Tawaran Trade",
            f"{ctx.author.mention} menawarkan **{koin_text(koin)}** ke {user.mention}.\n"
            f"{user.mention}, terima atau tolak dalam"
            f" **{config.settings.trade_timeout}** detik.",
            warna="ekonomi",
        )
        try:
            view.message = await ctx.send(embed=embed, view=view)
        except discord.HTTPException:
            await ctx.send(embed=error_embed("Gagal mengirim tawaran."), ephemeral=True)

    # ----- toko item -----
    @dagang.command(name="toko", description="Beli item consumable")
    async def toko_item(self, ctx: commands.Context):
        """Toko item: /dagang toko"""
        embed = finch_embed(
            "🛒 Toko Item",
            "Klik tombol Beli di bawah. Efek item aktif otomatis setelah dibeli.",
            warna="ekonomi",
        )
        for item_id, info in cons.ITEMS.items():
            embed.add_field(
                name=info["nama"],
                value=f"**{koin_text(info['harga'])}**\n{info['deskripsi']}",
                inline=True,
            )
        await ctx.send(embed=embed, view=TokoView())

    @dagang.command(name="tas", description="Lihat item milikmu")
    async def inventory(self, ctx: commands.Context):
        """Inventory: /dagang tas"""
        if ctx.guild is None:
            await ctx.send(embed=error_embed("Hanya bisa di server."), ephemeral=True)
            return
        with get_connection() as conn:
            items = cons.daftar_item(conn, ctx.guild.id, ctx.author.id)
        if not items:
            await ctx.send(
                embed=finch_embed(
                    "🎒 Inventory Kosong",
                    "Belum punya item. Beli di `/dagang toko`.",
                    warna="ekonomi",
                ),
                ephemeral=True,
            )
            return
        embed = finch_embed("🎒 Inventory", "", warna="ekonomi")
        for item_id, jumlah, berakhir in items:
            info = cons.ITEMS.get(item_id, {"nama": item_id})
            ket = ""
            if berakhir:
                dt = parse_iso(berakhir)
                if dt:
                    ket = f"\n⏳ <t:{int(dt.timestamp())}:R>"
            embed.add_field(
                name=info["nama"], value=f"**{jumlah}x**{ket}", inline=True
            )
        await ctx.send(embed=embed, ephemeral=True)

    @dagang.command(name="pakai", description="Pakai item consumable")
    @discord.app_commands.describe(item="perisai / xpboost / tiket")
    async def pakai(self, ctx: commands.Context, item: str):
        """Pakai item: /dagang pakai tiket"""
        if ctx.guild is None:
            await ctx.send(embed=error_embed("Hanya bisa di server."), ephemeral=True)
            return
        item = item.lower().strip()
        if item not in cons.ITEMS:
            await ctx.send(
                embed=error_embed(
                    f"Item tidak dikenal. Pilihan: {', '.join(cons.ITEMS.keys())}."
                ),
                ephemeral=True,
            )
            return
        gid, uid = ctx.guild.id, ctx.author.id
        if item == "tiket":
            with get_connection() as conn:
                if not cons.konsumsi_satu(conn, gid, uid, "tiket"):
                    await ctx.send(
                        embed=error_embed(
                            "Kamu tidak punya 🎟️ Tiket Lotre. Beli di `/dagang toko`."
                        ),
                        ephemeral=True,
                    )
                    return
                minggu = _minggu_ini()
                conn.execute(
                    "INSERT INTO lotre_tiket (guild_id, user_id, minggu) VALUES (?, ?, ?)",
                    (gid, uid, minggu),
                )
                conn.commit()
            await ctx.send(
                embed=sukses_embed(
                    "Tiket Ditukar",
                    f"🎟️ 1 tiket lotre minggu **{minggu}** masuk undian. Semoga beruntung!",
                ),
                ephemeral=True,
            )
            return
        # perisai / xpboost: aktif sejak dibeli, /dagang pakai = cek status
        with get_connection() as conn:
            aktif = cons.punya_aktif(conn, gid, uid, item)
            row = conn.execute(
                "SELECT berakhir FROM inventory WHERE user_id = ? AND guild_id = ? AND item_id = ?",
                (uid, gid, item),
            ).fetchone()
        info = cons.ITEMS[item]
        if aktif and row and row[0]:
            dt = parse_iso(row[0])
            ket = f"Berlaku sampai <t:{int(dt.timestamp())}:F>." if dt else ""
        elif aktif:
            ket = "Aktif."
        else:
            await ctx.send(
                embed=error_embed(
                    f"{info['nama']} tidak aktif. Beli di `/dagang toko`."
                ),
                ephemeral=True,
            )
            return
        await ctx.send(
            embed=sukses_embed(f"{info['nama']} Aktif", ket), ephemeral=True
        )

    # ----- pinjaman -----
    @dagang.command(name="pinjam", description="Pinjam koin berbunga harian")
    @discord.app_commands.describe(jumlah="Jumlah koin yang dipinjam")
    async def pinjam(self, ctx: commands.Context, jumlah: int):
        """Pinjam koin: /dagang pinjam 1000"""
        if ctx.guild is None:
            await ctx.send(embed=error_embed("Hanya bisa di server."), ephemeral=True)
            return
        if jumlah <= 0:
            await ctx.send(
                embed=error_embed("Jumlah harus lebih dari 0."), ephemeral=True
            )
            return
        maks = config.settings.pinjaman_maks
        if jumlah > maks:
            await ctx.send(
                embed=error_embed(f"Maksimal pinjaman **{koin_text(maks)}**."),
                ephemeral=True,
            )
            return
        gid, uid = ctx.guild.id, ctx.author.id
        with get_connection() as conn:
            aktif = conn.execute(
                "SELECT id FROM pinjaman WHERE user_id = ? AND guild_id = ? AND sisa > 0",
                (uid, gid),
            ).fetchone()
            if aktif:
                await ctx.send(
                    embed=error_embed(
                        "Kamu masih punya pinjaman aktif. Lunasi dulu dengan `/dagang lunasi`."
                    ),
                    ephemeral=True,
                )
                return
            bunga = config.settings.pinjaman_bunga_harian
            tenor = config.settings.pinjaman_tenor_hari
            now = discord.utils.utcnow()
            jt = (now + datetime.timedelta(days=tenor)).isoformat()
            conn.execute(
                "INSERT INTO pinjaman (user_id, guild_id, pokok, sisa, bunga_harian, dibuat, jatuh_tempo)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (uid, gid, jumlah, jumlah, bunga, now.isoformat(), jt),
            )
            conn.commit()
            eko.tambah_koin(conn, gid, uid, jumlah)
        await ctx.send(
            embed=sukses_embed(
                "Pinjaman Cair",
                f"**{koin_text(jumlah)}** masuk ke saldo.\n"
                f"📈 Bunga **{bunga}%/hari** • tenor **{tenor}** hari.\n"
                f"Lunasi dengan `/dagang lunasi`.",
            )
        )

    @dagang.command(name="lunasi", description="Bayar pinjaman (default: lunas)")
    @discord.app_commands.describe(jumlah="Jumlah yang dibayar (kosongkan = lunas)")
    async def lunasi(self, ctx: commands.Context, jumlah: int | None = None):
        """Lunasi pinjaman: /dagang lunasi [jumlah]"""
        if ctx.guild is None:
            await ctx.send(embed=error_embed("Hanya bisa di server."), ephemeral=True)
            return
        gid, uid = ctx.guild.id, ctx.author.id
        with get_connection() as conn:
            row = conn.execute(
                "SELECT id, sisa FROM pinjaman WHERE user_id = ? AND guild_id = ? AND sisa > 0"
                " ORDER BY id LIMIT 1",
                (uid, gid),
            ).fetchone()
            if not row:
                await ctx.send(
                    embed=error_embed("Kamu tidak punya pinjaman aktif."),
                    ephemeral=True,
                )
                return
            pid, sisa = row
            bayar = sisa if jumlah is None else jumlah
            if bayar <= 0:
                await ctx.send(
                    embed=error_embed("Jumlah harus lebih dari 0."), ephemeral=True
                )
                return
            bayar = min(bayar, sisa)
            if eko.kurang_koin(conn, gid, uid, bayar) is None:
                await ctx.send(
                    embed=error_embed("Koin tidak cukup untuk membayar."),
                    ephemeral=True,
                )
                return
            sisa_baru = sisa - bayar
            conn.execute("UPDATE pinjaman SET sisa = ? WHERE id = ?", (sisa_baru, pid))
            conn.commit()
        if sisa_baru == 0:
            await ctx.send(
                embed=sukses_embed("Lunas!", "Pinjaman sudah lunas. Sampai jumpa lagi! 🎉")
            )
        else:
            await ctx.send(
                embed=sukses_embed(
                    "Pembayaran Diterima",
                    f"Dibayar **{koin_text(bayar)}**. Sisa: **{koin_text(sisa_baru)}**.",
                )
            )

    @dagang.command(name="info-pinjaman", description="Info pinjaman aktifmu")
    async def pinjaman_info(self, ctx: commands.Context):
        """Info pinjaman: /dagang info-pinjaman"""
        if ctx.guild is None:
            await ctx.send(embed=error_embed("Hanya bisa di server."), ephemeral=True)
            return
        with get_connection() as conn:
            row = conn.execute(
                "SELECT pokok, sisa, bunga_harian, jatuh_tempo FROM pinjaman"
                " WHERE user_id = ? AND guild_id = ? AND sisa > 0 ORDER BY id LIMIT 1",
                (ctx.author.id, ctx.guild.id),
            ).fetchone()
        if not row:
            await ctx.send(
                embed=finch_embed(
                    "🏦 Pinjaman",
                    "Tidak ada pinjaman aktif. Pinjam dengan `/dagang pinjam <jumlah>`.",
                    warna="ekonomi",
                ),
                ephemeral=True,
            )
            return
        pokok, sisa, bunga, jt = row
        jt_dt = parse_iso(jt)
        status = "🟢 Lancar"
        if jt_dt and discord.utils.utcnow() > jt_dt:
            status = "🔴 MENUNGGAK — lunasi segera!"
        embed = finch_embed("🏦 Pinjaman Aktif", f"Status: **{status}**", warna="ekonomi")
        embed.add_field(name="Pokok", value=koin_text(pokok), inline=True)
        embed.add_field(name="Sisa", value=koin_text(sisa), inline=True)
        embed.add_field(name="Bunga", value=f"{bunga}%/hari", inline=True)
        if jt_dt:
            embed.add_field(
                name="Jatuh Tempo", value=f"<t:{int(jt_dt.timestamp())}:F>", inline=True
            )
        await ctx.send(embed=embed, ephemeral=True)

    # ----- deposito -----
    @dagang.command(name="deposito", description="Kunci koin, panen + bunga")
    @discord.app_commands.describe(
        jumlah="Jumlah koin yang dikunci", hari="Durasi (hari)"
    )
    async def deposito(self, ctx: commands.Context, jumlah: int, hari: int):
        """Deposito: /dagang deposito 1000 30"""
        if ctx.guild is None:
            await ctx.send(embed=error_embed("Hanya bisa di server."), ephemeral=True)
            return
        pilihan = config.settings.deposito_pilihan_list()
        if not hari_valid_deposito(hari, pilihan):
            daftar = ", ".join(f"{h} hari ({b}%)" for h, b in pilihan)
            await ctx.send(
                embed=error_embed(f"Pilihan durasi: {daftar}."), ephemeral=True
            )
            return
        if jumlah <= 0:
            await ctx.send(
                embed=error_embed("Jumlah harus lebih dari 0."), ephemeral=True
            )
            return
        bunga_pct = next(b for h, b in pilihan if h == hari)
        gid, uid = ctx.guild.id, ctx.author.id
        with get_connection() as conn:
            if eko.kurang_koin(conn, gid, uid, jumlah) is None:
                await ctx.send(
                    embed=error_embed("Koin tidak cukup."), ephemeral=True
                )
                return
            now = discord.utils.utcnow().isoformat()
            conn.execute(
                "INSERT INTO deposito (user_id, guild_id, jumlah, mulai, durasi_hari, bunga_pct, selesai)"
                " VALUES (?, ?, ?, ?, ?, ?, 0)",
                (uid, gid, jumlah, now, hari, bunga_pct),
            )
            conn.commit()
        panen = jumlah + bunga_deposito(jumlah, bunga_pct)
        await ctx.send(
            embed=sukses_embed(
                "Deposito Dibuka",
                f"**{koin_text(jumlah)}** dikunci **{hari}** hari.\n"
                f"💰 Panen: **{koin_text(panen)}** (+{bunga_pct}%).",
            )
        )

    @dagang.command(name="info-deposito", description="Info depositomu")
    async def deposito_info(self, ctx: commands.Context):
        """Info deposito: /dagang info-deposito"""
        if ctx.guild is None:
            await ctx.send(embed=error_embed("Hanya bisa di server."), ephemeral=True)
            return
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT jumlah, mulai, durasi_hari, bunga_pct FROM deposito"
                " WHERE user_id = ? AND guild_id = ? AND selesai = 0",
                (ctx.author.id, ctx.guild.id),
            ).fetchall()
        if not rows:
            await ctx.send(
                embed=finch_embed(
                    "🏛️ Deposito",
                    "Tidak ada deposito aktif. Buka dengan `/dagang deposito <jumlah> <hari>`.",
                    warna="ekonomi",
                ),
                ephemeral=True,
            )
            return
        embed = finch_embed("🏛️ Deposito Aktif", "", warna="ekonomi")
        for jumlah, mulai, durasi, bunga in rows:
            dt = parse_iso(mulai)
            jt_ts = ""
            if dt:
                jt_ts = f" → <t:{int((dt + datetime.timedelta(days=durasi)).timestamp())}:R>"
            panen = jumlah + bunga_deposito(jumlah, bunga)
            embed.add_field(
                name=f"{koin_text(jumlah)} / {durasi} hari",
                value=f"Panen **{koin_text(panen)}** (+{bunga}%){jt_ts}",
                inline=True,
            )
        await ctx.send(embed=embed, ephemeral=True)

    # ----- saham -----
    @dagang.command(name="saham", description="Lihat harga saham")
    async def saham(self, ctx: commands.Context):
        """Harga saham: /dagang saham"""
        harga = self._harga_saham()
        if not harga:
            await ctx.send(
                embed=error_embed("Data saham belum tersedia."), ephemeral=True
            )
            return
        embed = finch_embed(
            "📈 Bursa Finch",
            "Harga bergerak tiap jam. Beli murah, jual mahal! `/dagang beli`, `/dagang jual`.",
            warna="ekonomi",
        )
        for simbol in sorted(harga):
            h = harga[simbol]
            lama = self._harga_lama.get(simbol, h)
            if lama and lama != h:
                pct = (h - lama) / lama * 100
                tren = f"{'📈' if pct >= 0 else '📉'} {pct:+.1f}%"
            else:
                tren = "➖ 0.0%"
            embed.add_field(
                name=f"${simbol}", value=f"**{koin_text(h)}**\n{tren}", inline=True
            )
        await ctx.send(embed=embed)

    @dagang.command(name="beli", description="Beli saham")
    @discord.app_commands.describe(simbol="FINC/PION/NUSA/OUTP", lembar="Jumlah lembar")
    async def saham_beli(self, ctx: commands.Context, simbol: str, lembar: int):
        """Beli saham: /dagang beli FINC 10"""
        if ctx.guild is None:
            await ctx.send(embed=error_embed("Hanya bisa di server."), ephemeral=True)
            return
        simbol = simbol.upper().strip()
        harga = self._harga_saham()
        if simbol not in harga:
            await ctx.send(
                embed=error_embed(
                    f"Simbol tidak dikenal. Pilihan: {', '.join(sorted(harga))}."
                ),
                ephemeral=True,
            )
            return
        if lembar <= 0:
            await ctx.send(
                embed=error_embed("Jumlah lembar harus lebih dari 0."), ephemeral=True
            )
            return
        total = harga[simbol] * lembar
        gid, uid = ctx.guild.id, ctx.author.id
        with get_connection() as conn:
            if eko.kurang_koin(conn, gid, uid, total) is None:
                await ctx.send(
                    embed=error_embed(
                        f"Butuh **{koin_text(total)}**, koin tidak cukup."
                    ),
                    ephemeral=True,
                )
                return
            conn.execute(
                "INSERT INTO saham_milik (user_id, guild_id, simbol, jumlah)"
                " VALUES (?, ?, ?, ?)"
                " ON CONFLICT(user_id, guild_id, simbol) DO UPDATE SET jumlah = jumlah + ?",
                (uid, gid, simbol, lembar, lembar),
            )
            conn.commit()
        await ctx.send(
            embed=sukses_embed(
                "Saham Dibeli",
                f"**{lembar}** lembar ${simbol} seharga **{koin_text(total)}**.",
            )
        )

    @dagang.command(name="jual", description="Jual saham")
    @discord.app_commands.describe(simbol="FINC/PION/NUSA/OUTP", lembar="Jumlah lembar")
    async def saham_jual(self, ctx: commands.Context, simbol: str, lembar: int):
        """Jual saham: /dagang jual FINC 5"""
        if ctx.guild is None:
            await ctx.send(embed=error_embed("Hanya bisa di server."), ephemeral=True)
            return
        simbol = simbol.upper().strip()
        harga = self._harga_saham()
        if simbol not in harga:
            await ctx.send(
                embed=error_embed(
                    f"Simbol tidak dikenal. Pilihan: {', '.join(sorted(harga))}."
                ),
                ephemeral=True,
            )
            return
        if lembar <= 0:
            await ctx.send(
                embed=error_embed("Jumlah lembar harus lebih dari 0."), ephemeral=True
            )
            return
        gid, uid = ctx.guild.id, ctx.author.id
        with get_connection() as conn:
            row = conn.execute(
                "SELECT jumlah FROM saham_milik WHERE user_id = ? AND guild_id = ? AND simbol = ?",
                (uid, gid, simbol),
            ).fetchone()
            punya = row[0] if row else 0
            if punya < lembar:
                await ctx.send(
                    embed=error_embed(f"Kamu cuma punya **{punya}** lembar ${simbol}."),
                    ephemeral=True,
                )
                return
            hasil = harga[simbol] * lembar
            conn.execute(
                "UPDATE saham_milik SET jumlah = jumlah - ?"
                " WHERE user_id = ? AND guild_id = ? AND simbol = ?",
                (lembar, uid, gid, simbol),
            )
            conn.commit()
            eko.tambah_koin(conn, gid, uid, hasil)
        await ctx.send(
            embed=sukses_embed(
                "Saham Terjual",
                f"**{lembar}** lembar ${simbol} → **{koin_text(hasil)}**.",
            )
        )

    # ----- peti misteri -----
    @dagang.command(name="peti", description="Buka peti misteri harian")
    async def peti(self, ctx: commands.Context):
        """Peti misteri: /dagang peti (sekali sehari)"""
        if ctx.guild is None:
            await ctx.send(embed=error_embed("Hanya bisa di server."), ephemeral=True)
            return
        gid, uid = ctx.guild.id, ctx.author.id
        hari_ini = discord.utils.utcnow().date().isoformat()
        with get_connection() as conn:
            eko.get_akun(conn, gid, uid)  # pastikan row economy ada
            row = conn.execute(
                "SELECT peti_terakhir FROM economy WHERE user_id = ? AND guild_id = ?",
                (uid, gid),
            ).fetchone()
            if row and row[0] == hari_ini:
                await ctx.send(
                    embed=error_embed(
                        "Peti hari ini sudah dibuka. Kembali besok! 🎁"
                    ),
                    ephemeral=True,
                )
                return
            jenis, nilai = roll_peti()
            if jenis == "koin":
                eko.tambah_koin(conn, gid, uid, nilai)
                hadiah_txt = f"**{koin_text(nilai)}**"
            else:
                cons.beri_item(conn, gid, uid, nilai)
                hadiah_txt = cons.ITEMS[nilai]["nama"]
            conn.execute(
                "UPDATE economy SET peti_terakhir = ? WHERE user_id = ? AND guild_id = ?",
                (hari_ini, uid, gid),
            )
            conn.commit()
        await ctx.send(
            embed=finch_embed(
                "🎁 Peti Misteri Dibuka!",
                f"{ctx.author.mention} mendapatkan...\n\n# {hadiah_txt}\n\nBesok ada lagi!",
                warna="ekonomi",
            )
        )

    # ----- loop harian: pinjaman + deposito -----
    @tasks.loop(hours=24)
    async def _loop_harian(self):
        from src.cogs.dashboard_sync import modul_aktif

        now = discord.utils.utcnow()
        # Pinjaman: bunga harian + auto-debit saat jatuh tempo
        try:
            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT id, user_id, guild_id, sisa, bunga_harian, jatuh_tempo"
                    " FROM pinjaman WHERE sisa > 0"
                ).fetchall()
        except Exception:
            log.exception("Gagal baca pinjaman")
            rows = []
        for pid, uid, gid, sisa, pct, jt_iso in rows:
            if not modul_aktif(gid, "economy_enabled"):
                continue  # modul ekonomi dimatikan di server ini — bekukan
            try:
                sisa_baru = sisa + hitung_bunga(sisa, pct)
                jt = parse_iso(jt_iso)
                if jt is not None and now >= jt:
                    # Auto-debit: lunasi paksa bila saldo cukup
                    with get_connection() as conn:
                        if eko.kurang_koin(conn, gid, uid, sisa_baru) is not None:
                            sisa_baru = 0
                            log.info("Pinjaman #%s lunas via auto-debit.", pid)
                        else:
                            log.warning(
                                "Pinjaman #%s MENUNGGAK (user %s, sisa %s).",
                                pid, uid, sisa_baru,
                            )
                with get_connection() as conn:
                    conn.execute(
                        "UPDATE pinjaman SET sisa = ? WHERE id = ?", (sisa_baru, pid)
                    )
                    conn.commit()
            except Exception:
                log.exception("Gagal proses pinjaman #%s", pid)
        # Deposito: panen yang jatuh tempo
        try:
            with get_connection() as conn:
                deps = conn.execute(
                    "SELECT id, user_id, guild_id, jumlah, mulai, durasi_hari, bunga_pct"
                    " FROM deposito WHERE selesai = 0"
                ).fetchall()
        except Exception:
            log.exception("Gagal baca deposito")
            deps = []
        for did, uid, gid, jumlah, mulai_iso, durasi, pct in deps:
            if not modul_aktif(gid, "economy_enabled"):
                continue  # modul ekonomi dimatikan di server ini — bekukan
            try:
                mulai = parse_iso(mulai_iso)
                if mulai is None:
                    continue
                if now >= mulai + datetime.timedelta(days=durasi):
                    panen = jumlah + bunga_deposito(jumlah, pct)
                    # Tandai selesai DULU baru kredit — crash di tengah = hadiah
                    # hilang (aman), bukan panen 2x
                    with get_connection() as conn:
                        cur = conn.execute(
                            "UPDATE deposito SET selesai = 1 WHERE id = ? AND selesai = 0",
                            (did,),
                        )
                        if cur.rowcount == 0:
                            continue  # sudah dipanen (race antar loop)
                        conn.commit()
                    with get_connection() as conn:
                        eko.tambah_koin(conn, gid, uid, panen)
                    log.info("Deposito #%s panen: %s koin.", did, panen)
            except Exception:
                log.exception("Gagal panen deposito #%s", did)

    @_loop_harian.before_loop
    async def _before_harian(self):
        await self.bot.wait_until_ready()

    # ----- loop saham -----
    @tasks.loop(minutes=config.settings.saham_update_menit)
    async def _loop_saham(self):
        self._pastikan_saham_seed()
        try:
            with get_connection() as conn:
                rows = conn.execute("SELECT simbol, harga FROM saham_harga").fetchall()
                if not rows:
                    return
                now = discord.utils.utcnow().isoformat()
                for simbol, harga in rows:
                    self._harga_lama[simbol] = harga
                    baru = harga_saham_baru(harga, random.uniform(0.85, 1.15))
                    conn.execute(
                        "UPDATE saham_harga SET harga = ?, updated_at = ? WHERE simbol = ?",
                        (baru, now, simbol),
                    )
                conn.commit()
        except Exception:
            log.exception("Gagal update harga saham")

    @_loop_saham.before_loop
    async def _before_saham(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(EkonomiPlus(bot))
