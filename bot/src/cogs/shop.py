"""Shop — beli role pakai koin.

Config `.env`: SHOP_ITEMS="VIP:5000,Warna Emas:2500" (nama role:harga, pisah koma).
- `/shop` — lihat daftar barang (field kesamping)
- `/buy <nama>` — beli role
- `/lelang <nama_role> <harga_awal> <durasi>` (mod) — lelang role
- `/bid <jumlah>` — tawar lelang aktif di channel ini
"""
import datetime
import logging

import discord
from discord.ext import commands, tasks

from src import config
from src.store import get_connection
from src.utils import economy as eko
from src.utils.embeds import base_embed
from src.utils.filters import parse_durasi

log = logging.getLogger("finch")



class Shop(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cek_lelang.start()

    def cog_unload(self):
        self.cek_lelang.cancel()

    async def cog_check(self, ctx: commands.Context) -> bool:
        """Shop adalah bagian modul Ekonomi — ikut toggle `economy_enabled`.

        Lelang yang sudah berjalan tetap diselesaikan loop agar tidak menggantung.
        """
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

    @commands.hybrid_command(name="shop", description="Lihat barang yang bisa dibeli pakai koin")
    async def shop(self, ctx: commands.Context):
        """Lihat shop: /shop"""
        items = config.settings.shop_items_list()
        if not items:
            await ctx.send(
                "🛒 Shop masih kosong. Mod bisa isi `SHOP_ITEMS` di `.env` "
                '(format: `"VIP:5000,Warna Emas:2500"`).',
                ephemeral=True,
            )
            return
        embed = base_embed("🛒 Shop Koin", "Beli dengan `/buy <nama>`:")
        # UI horizontal: item-item kesamping
        for nama, harga in items:
            embed.add_field(name=f"{nama}", value=f"**{harga}** 🪙", inline=True)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="buy", description="Beli role dari shop pakai koin")
    @discord.app_commands.describe(nama="Nama barang persis seperti di /shop")
    async def buy(self, ctx: commands.Context, nama: str):
        """Beli: /buy <nama>"""
        if ctx.guild is None:
            await ctx.send("❌ Hanya bisa di server.", ephemeral=True)
            return
        items = {n.lower(): (n, h) for n, h in config.settings.shop_items_list()}
        kunci = nama.strip().lower()
        if kunci not in items:
            await ctx.send(
                f"❌ Barang **{nama}** tidak ada di shop. Cek `/shop`.",
                ephemeral=True,
            )
            return
        nama_asli, harga = items[kunci]
        role = discord.utils.get(ctx.guild.roles, name=nama_asli)
        if role is None:
            await ctx.send(
                f"❌ Role **{nama_asli}** belum dibuat di server. Hubungi mod.",
                ephemeral=True,
            )
            return
        if role in ctx.author.roles:
            await ctx.send(f"❌ Kamu sudah punya role **{nama_asli}**.", ephemeral=True)
            return
        with get_connection() as conn:
            sisa = eko.kurang_koin(conn, ctx.guild.id, ctx.author.id, harga)
            if sisa is None:
                await ctx.send(
                    f"❌ Koin tidak cukup. Butuh **{harga}** 🪙.",
                    ephemeral=True,
                )
                return
        try:
            await ctx.author.add_roles(role, reason=f"Beli dari shop ({harga} koin)")
        except discord.Forbidden:
            # Kembalikan koin kalau gagal kasih role
            with get_connection() as conn:
                eko.tambah_koin(conn, ctx.guild.id, ctx.author.id, harga)
            log.warning("Gagal kasih role shop '%s' — role bot harus di atasnya.", nama_asli)
            await ctx.send(
                "❌ Gagal pasang role (posisi role bot kurang tinggi). Koin dikembalikan.",
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            with get_connection() as conn:
                eko.tambah_koin(conn, ctx.guild.id, ctx.author.id, harga)
            await ctx.send("❌ Gagal pasang role. Koin dikembalikan.", ephemeral=True)
            return
        await ctx.send(
            embed=base_embed(
                "🛒 Pembelian Berhasil!",
                f"Kamu membeli **{nama_asli}** seharga **{harga}** 🪙.\nSisa saldo: **{sisa}** koin.",
            )
        )

    # ---------- Lelang ----------

    @commands.hybrid_command(name="lelang", description="Lelang role (khusus mod)")
    @commands.has_permissions(manage_messages=True)
    @discord.app_commands.describe(
        nama_role="Nama role yang dilelang",
        harga_awal="Harga awal dalam koin",
        durasi="Contoh: 10m, 1h, 1d",
    )
    async def lelang(
        self, ctx: commands.Context, nama_role: str, harga_awal: int, durasi: str
    ):
        """Mulai lelang: /lelang VIP 1000 1h"""
        if ctx.guild is None:
            await ctx.send("❌ Hanya bisa di server.", ephemeral=True)
            return
        role = discord.utils.get(ctx.guild.roles, name=nama_role.strip())
        if role is None:
            await ctx.send(
                f"❌ Role **{nama_role}** tidak ketemu di server.", ephemeral=True
            )
            return
        if harga_awal <= 0:
            await ctx.send("❌ Harga awal harus lebih dari 0.", ephemeral=True)
            return
        detik = parse_durasi(durasi)
        if detik is None or detik < 60:
            await ctx.send(
                "❌ Durasi minimal 1 menit. Contoh: `10m`, `1h`, `1d`.",
                ephemeral=True,
            )
            return
        if detik > 7 * 86400:
            await ctx.send("❌ Durasi maksimal 7 hari.", ephemeral=True)
            return
        ends = discord.utils.utcnow() + datetime.timedelta(seconds=detik)
        with get_connection() as conn:
            cur = conn.execute(
                "INSERT INTO lelang (guild_id, channel_id, message_id, nama_role,"
                " harga_awal, ends_at) VALUES (?, ?, ?, ?, ?, ?)",
                (ctx.guild.id, ctx.channel.id, 0, role.name, harga_awal, ends.isoformat()),
            )
            lelang_id = cur.lastrowid
            conn.commit()
        embed = base_embed(
            "🔨 Lelang Dimulai!",
            f"Role: **{role.name}**\n"
            f"💰 Harga awal: **{harga_awal}** 🪙\n"
            f"⏰ Berakhir: <t:{int(ends.timestamp())}:R>\n\n"
            f"Tawar dengan `/bid <jumlah>` — harus lebih tinggi dari tawaran saat ini!",
        )
        try:
            msg = await ctx.send(embed=embed)
        except discord.HTTPException:
            with get_connection() as conn:
                conn.execute("DELETE FROM lelang WHERE id = ?", (lelang_id,))
                conn.commit()
            await ctx.send("❌ Gagal memposting lelang.", ephemeral=True)
            return
        if msg is not None:
            with get_connection() as conn:
                conn.execute(
                    "UPDATE lelang SET message_id = ? WHERE id = ?",
                    (msg.id, lelang_id),
                )
                conn.commit()
        log.info("Lelang dimulai: %s (%d koin, %ds)", role.name, harga_awal, detik)

    @commands.hybrid_command(name="bid", description="Tawar lelang yang aktif di channel ini")
    @discord.app_commands.describe(jumlah="Tawaran koin (harus tertinggi)")
    async def bid(self, ctx: commands.Context, jumlah: int):
        """Tawar lelang: /bid <jumlah>"""
        if ctx.guild is None:
            await ctx.send("❌ Hanya bisa di server.", ephemeral=True)
            return
        if jumlah <= 0:
            await ctx.send("❌ Tawaran harus lebih dari 0.", ephemeral=True)
            return
        with get_connection() as conn:
            row = conn.execute(
                "SELECT id, nama_role, harga_awal, tawaran_tertinggi, penawar_id FROM lelang"
                " WHERE guild_id = ? AND channel_id = ? AND ended = 0"
                " ORDER BY id DESC LIMIT 1",
                (ctx.guild.id, ctx.channel.id),
            ).fetchone()
            if not row:
                await ctx.send("❌ Tidak ada lelang aktif di channel ini.", ephemeral=True)
                return
            lid, nama_role, harga_awal, tertinggi, penawar = row
            minimal = max(harga_awal, tertinggi) + 1
            if jumlah < minimal:
                await ctx.send(
                    f"❌ Tawaran harus ≥ **{minimal}** 🪙.", ephemeral=True
                )
                return
            if ctx.author.id == penawar:
                await ctx.send("❌ Kamu sudah penawar tertinggi.", ephemeral=True)
                return
            akun = eko.get_akun(conn, ctx.guild.id, ctx.author.id)
            if akun["balance"] < jumlah:
                await ctx.send(
                    "❌ Koin kamu tidak cukup untuk tawaran ini.", ephemeral=True
                )
                return
            # Escrow: potong penawar baru, kembalikan tawaran penawar lama
            # (bug lama: tanpa escrow, pemenang bisa habiskan koin sebelum settlement)
            sisa = eko.kurang_koin(conn, ctx.guild.id, ctx.author.id, jumlah)
            if sisa is None:
                await ctx.send("❌ Koin kamu tidak cukup.", ephemeral=True)
                return
            if penawar and tertinggi:
                eko.tambah_koin(conn, ctx.guild.id, penawar, tertinggi)
            conn.execute(
                "UPDATE lelang SET tawaran_tertinggi = ?, penawar_id = ? WHERE id = ?",
                (jumlah, ctx.author.id, lid),
            )
            conn.execute(
                "INSERT INTO lelang_bid (lelang_id, user_id, jumlah, waktu) VALUES (?, ?, ?, ?)",
                (lid, ctx.author.id, jumlah, discord.utils.utcnow().isoformat()),
            )
            conn.commit()
        await ctx.send(
            f"🔨 {ctx.author.mention} menawar **{jumlah}** 🪙 untuk **{nama_role}**!"
        )

    @tasks.loop(minutes=1)
    async def cek_lelang(self):
        now = discord.utils.utcnow().isoformat()
        try:
            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT id, guild_id, channel_id, nama_role, tawaran_tertinggi, penawar_id"
                    " FROM lelang WHERE ended = 0 AND ends_at <= ?",
                    (now,),
                ).fetchall()
        except Exception:
            log.exception("Gagal baca lelang")
            return
        for lid, gid, cid, nama_role, tertinggi, penawar in rows:
            try:
                await self._selesaikan_lelang(lid, gid, cid, nama_role, tertinggi, penawar)
            except Exception:
                log.exception("Gagal selesaikan lelang %s", lid)

    @cek_lelang.before_loop
    async def _before_lelang(self):
        await self.bot.wait_until_ready()

    async def _selesaikan_lelang(
        self, lid: int, gid: int, cid: int, nama_role: str, tertinggi: int, penawar: int | None
    ) -> None:
        with get_connection() as conn:
            # Guarded: hanya satu settlement yang jalan (anti panggilan ganda)
            cur = conn.execute("UPDATE lelang SET ended = 1 WHERE id = ? AND ended = 0", (lid,))
            if cur.rowcount == 0:
                return
            # Baca ulang tawaran tertinggi TERBARU — /bid bisa masuk di antara
            # SELECT loop dan UPDATE di atas (data basi = escrow pemenang hangus).
            row = conn.execute(
                "SELECT tawaran_tertinggi, penawar_id FROM lelang WHERE id = ?", (lid,)
            ).fetchone()
            conn.commit()
        if row:
            tertinggi, penawar = row[0], row[1]
        channel = self.bot.get_channel(cid)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(cid)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                log.warning("Lelang %s: channel %s hilang.", lid, cid)
                return
        if not penawar:
            try:
                await channel.send(f"🔨 Lelang **{nama_role}** berakhir tanpa peminat. 😢")
            except discord.HTTPException:
                pass
            return
        guild = getattr(channel, "guild", None) or self.bot.get_guild(gid)
        member = guild.get_member(penawar) if guild else None
        role = discord.utils.get(guild.roles, name=nama_role) if guild else None
        ok = False
        # Pemenang sudah membayar via escrow saat /bid — tinggal pasang role
        if member and role and not member.bot:
            try:
                await member.add_roles(role, reason=f"Menang lelang ({tertinggi} koin)")
                ok = True
            except (discord.Forbidden, discord.HTTPException) as e:
                log.warning("Lelang %s: gagal pasang role (%s); escrow dikembalikan.", lid, e)
                with get_connection() as conn:
                    eko.tambah_koin(conn, gid, penawar, tertinggi)
        elif penawar and tertinggi:
            # Pemenang/role tidak valid (keluar server / role dihapus) —
            # escrow JANGAN hangus, kembalikan ke penawar.
            log.warning("Lelang %s: pemenang tidak valid; escrow %s dikembalikan.", lid, penawar)
            with get_connection() as conn:
                eko.tambah_koin(conn, gid, penawar, tertinggi)
        try:
            if ok:
                await channel.send(
                    f"🎉 Lelang **{nama_role}** dimenangkan <@{penawar}> dengan **{tertinggi}** 🪙!"
                )
            else:
                await channel.send(
                    f"😢 Lelang **{nama_role}** gagal — pemenang tidak valid."
                )
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Shop(bot))
