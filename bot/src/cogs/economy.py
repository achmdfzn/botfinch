"""Sistem koin (economy) Finch.

- `/saldo [@user]` — cek koin (UI horizontal: kolom kesamping)
- `/daily` — klaim koin harian + streak bonus (cooldown 24 jam)
- `/kerja` — kerja dapat koin acak (cooldown dari config)
- `/transfer @user <jumlah>` — kirim koin ke member lain
- `/top-koin` — 10 terkaya (2 kolom kesamping: 1–5 dan 6–10)
- `/rep @user` — kasih reputasi (cooldown 24 jam per pemberi)
- `/bank`, `/deposit`, `/withdraw` — bank + bunga harian
- `/lotre-beli`, `/lotre-info` — lotre mingguan
- Gaji otomatis tiap 7 hari untuk role di GAJI_ROLES (loop, tanpa announce)
- Bonus koin otomatis tiap naik level (di `leveling.py`).
"""
import datetime
import logging

import discord
from discord.ext import commands, tasks

from src import config
from src.store import get_connection
from src.utils import achievement as ach
from src.utils import economy as eko
from src.utils.toggle import cek_toggle
from src.utils.embeds import base_embed, tabel

log = logging.getLogger("finch")



def _minggu_ini(dt=None) -> str:
    """Minggu ISO: '2026-W41'."""
    d = (dt or discord.utils.utcnow()).date()
    iso = d.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _get_bank(conn, guild_id: int, user_id: int) -> int:
    eko.get_akun(conn, guild_id, user_id)
    row = conn.execute(
        "SELECT bank FROM economy WHERE user_id = ? AND guild_id = ?",
        (user_id, guild_id),
    ).fetchone()
    return row[0] if row and row[0] else 0


def _parse_jumlah_param(teks: str, tersedia: int) -> tuple[int | None, str | None]:
    """Parse param jumlah: angka atau 'all'/'semua'. Return (nilai, pesan_error)."""
    t = teks.strip().lower()
    if t in ("all", "semua"):
        return tersedia, None
    try:
        n = int(t)
    except (ValueError, TypeError):
        return None, "❌ Jumlah tidak valid. Contoh: `/deposit 500` atau `/deposit all`."
    if n <= 0:
        return None, "❌ Jumlah harus lebih dari 0."
    return n, None


def _update_streak(conn, guild_id: int, user_id: int, now) -> tuple[int, int]:
    """Hitung streak daily (tanggal UTC). Return (streak, bonus_koin)."""
    eko.get_akun(conn, guild_id, user_id)  # pastikan baris ada
    today = now.date().isoformat()
    yesterday = (now.date() - datetime.timedelta(days=1)).isoformat()
    row = conn.execute(
        "SELECT streak_daily, last_streak_date FROM economy WHERE user_id = ? AND guild_id = ?",
        (user_id, guild_id),
    ).fetchone()
    cur, last = (row[0] or 0, row[1]) if row else (0, None)
    if last == yesterday:
        streak = cur + 1
    elif last == today:
        streak = cur or 1
    else:
        streak = 1
    bonus = min(streak, 30) * 5
    conn.execute(
        "UPDATE economy SET streak_daily = ?, last_streak_date = ? WHERE user_id = ? AND guild_id = ?",
        (streak, today, user_id, guild_id),
    )
    conn.commit()
    return streak, bonus


class Economy(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bunga_harian.start()
        self.undi_lotre.start()
        self.bayar_gaji.start()

    async def cog_check(self, ctx: commands.Context) -> bool:
        """Blokir semua command ekonomi kalau modul dimatikan per-server via dashboard."""
        return await cek_toggle(
            ctx, "economy_enabled", "Modul ekonomi dimatikan oleh admin server ini."
        )

    def cog_unload(self):
        self.bunga_harian.cancel()
        self.undi_lotre.cancel()
        self.bayar_gaji.cancel()

    @commands.hybrid_command(name="saldo", description="Cek koin kamu / member lain")
    @discord.app_commands.describe(member="Member yang mau dicek (opsional)")
    async def saldo(self, ctx: commands.Context, member: discord.Member | None = None):
        """Cek koin: /saldo [@user]"""
        target = member or ctx.author
        if target.bot:
            await ctx.send("❌ Bot tidak punya koin.", ephemeral=True)
            return
        gid = ctx.guild.id if ctx.guild else 0
        with get_connection() as conn:
            akun = eko.get_akun(conn, gid, target.id)
            rank = eko.peringkat(conn, gid, target.id)
            rep = eko.get_rep(conn, gid, target.id)
            # Hidden achievement: sultan diam-diam
            try:
                ach.cek_buka(conn, gid, target.id, {"sultan_diam": akun["balance"]})
            except Exception:
                log.exception("Gagal cek achievement sultan untuk %s", target.id)
        embed = base_embed(f"🪙 Koin — {target.display_name}")
        # UI horizontal: kolom-kolom kesamping, bukan list vertikal
        embed.add_field(name="Saldo", value=f"**{akun['balance']}** koin", inline=True)
        embed.add_field(name="Peringkat", value=f"**#{rank}** server", inline=True)
        embed.add_field(name="Total diperoleh", value=f"**{akun['total_earned']}** koin", inline=True)
        embed.add_field(name="Reputasi", value=f"**{rep}** rep", inline=True)
        try:
            embed.set_thumbnail(url=target.display_avatar.url)
        except Exception:
            log.debug("Gagal pasang thumbnail avatar untuk %s", target.id, exc_info=True)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="daily", description="Klaim koin harian (24 jam sekali)")
    async def daily(self, ctx: commands.Context):
        """Klaim koin harian: /daily"""
        if ctx.guild is None:
            await ctx.send("❌ Hanya bisa di server.", ephemeral=True)
            return
        now = discord.utils.utcnow()
        dibuka: list[tuple[str, str]] = []
        streak, bonus = 0, 0
        with get_connection() as conn:
            status, nilai = eko.klaim_daily(conn, ctx.guild.id, ctx.author.id, now)
            if status == "ok":
                from src.utils import quests as q

                q.tandai_daily(conn, ctx.guild.id, ctx.author.id)
                streak, bonus = _update_streak(conn, ctx.guild.id, ctx.author.id, now)
                if bonus:
                    eko.tambah_koin(conn, ctx.guild.id, ctx.author.id, bonus)
                akun = eko.get_akun(conn, ctx.guild.id, ctx.author.id)
                dibuka = ach.cek_buka(
                    conn, ctx.guild.id, ctx.author.id,
                    {"streak": streak, "wealth": akun["total_earned"]},
                )
        if status == "cooldown":
            await ctx.send(
                f"⏳ Daily sudah diklaim. Kembali lagi dalam **{eko.format_sisa_waktu(nilai)}**.",
                ephemeral=True,
            )
            return
        teks = f"Kamu dapat **{nilai}** 🪙 koin!"
        if streak:
            teks += f"\n🔥 Streak **{streak} hari**! Bonus +**{bonus}** 🪙"
        await ctx.send(embed=base_embed("🎁 Daily Diklaim!", teks))
        if dibuka:
            try:
                await ctx.send(ach.embed_pengumuman(ctx.author.display_name, dibuka))
            except discord.HTTPException:
                pass

    @commands.hybrid_command(name="kerja", description="Kerja untuk dapat koin")
    async def kerja(self, ctx: commands.Context):
        """Kerja dapat koin: /kerja"""
        if ctx.guild is None:
            await ctx.send("❌ Hanya bisa di server.", ephemeral=True)
            return
        with get_connection() as conn:
            status, nilai = eko.kerja(conn, ctx.guild.id, ctx.author.id, discord.utils.utcnow())
            bonus_txt = ""
            if status == "ok":
                # Bonus job Pedagang: +15% koin kerja (Tahap 12)
                try:
                    from src.utils import job as jobmod

                    bonus = jobmod.bonus_untuk(conn, ctx.guild.id, ctx.author.id)
                    if bonus.get("bonus_kerja"):
                        tambahan = int(nilai * bonus["bonus_kerja"])
                        if tambahan > 0:
                            eko.tambah_koin(conn, ctx.guild.id, ctx.author.id, tambahan)
                            nilai += tambahan
                            bonus_txt = f"\n💰 Bonus Pedagang: +**{tambahan}** 🪙"
                except Exception:
                    log.exception("Gagal baca bonus job kerja untuk %s", ctx.author.id)
        if status == "cooldown":
            await ctx.send(
                f"💼 Kamu sudah kerja. Istirahat dulu **{eko.format_sisa_waktu(nilai)}**.",
                ephemeral=True,
            )
            return
        embed = base_embed("💼 Kerja Selesai!", f"Kamu dapat **{nilai}** 🪙 koin!{bonus_txt}")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="transfer", description="Kirim koin ke member lain")
    @discord.app_commands.describe(member="Tujuan transfer", jumlah="Jumlah koin")
    async def transfer(self, ctx: commands.Context, member: discord.Member, jumlah: int):
        """Transfer koin: /transfer @user <jumlah>"""
        if ctx.guild is None:
            await ctx.send("❌ Hanya bisa di server.", ephemeral=True)
            return
        if member.bot:
            await ctx.send("❌ Tidak bisa transfer ke bot.", ephemeral=True)
            return
        if member.id == ctx.author.id:
            await ctx.send("❌ Tidak bisa transfer ke diri sendiri.", ephemeral=True)
            return
        if jumlah <= 0:
            await ctx.send("❌ Jumlah harus lebih dari 0.", ephemeral=True)
            return
        if jumlah > 1_000_000_000:
            await ctx.send("❌ Jumlah terlalu besar.", ephemeral=True)
            return
        with get_connection() as conn:
            sisa = eko.kurang_koin(conn, ctx.guild.id, ctx.author.id, jumlah)
            if sisa is None:
                await ctx.send("❌ Koin kamu tidak cukup.", ephemeral=True)
                return
            eko.tambah_koin(conn, ctx.guild.id, member.id, jumlah)
        embed = base_embed(
            "💸 Transfer Berhasil",
            f"{ctx.author.mention} mengirim **{jumlah}** 🪙 ke {member.mention}.\n"
            f"Sisa saldomu: **{sisa}** koin.",
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="rep", description="Kasih reputasi ke member (24 jam sekali)")
    @discord.app_commands.describe(member="Member yang mau dikasih reputasi")
    async def rep(self, ctx: commands.Context, member: discord.Member):
        """Kasih reputasi: /rep @user"""
        if ctx.guild is None:
            await ctx.send("❌ Hanya bisa di server.", ephemeral=True)
            return
        if member.bot:
            await ctx.send("❌ Tidak bisa kasih rep ke bot.", ephemeral=True)
            return
        if member.id == ctx.author.id:
            await ctx.send("❌ Tidak bisa kasih rep ke diri sendiri.", ephemeral=True)
            return
        with get_connection() as conn:
            status, nilai = eko.beri_rep(
                conn, ctx.guild.id, ctx.author.id, member.id, discord.utils.utcnow()
            )
        if status == "cooldown":
            await ctx.send(
                f"⏳ Kamu sudah kasih rep. Bisa lagi dalam **{eko.format_sisa_waktu(nilai)}**.",
                ephemeral=True,
            )
            return
        await ctx.send(
            embed=base_embed(
                "⭐ Reputasi Dikirim!",
                f"{ctx.author.mention} kasih reputasi ke {member.mention}!\n"
                f"Total reputasi {member.display_name}: **{nilai}** ⭐",
            )
        )

    @commands.hybrid_command(name="top-koin", description="10 pemilik koin terbanyak")
    async def top_koin(self, ctx: commands.Context):
        """Top koin: /top-koin"""
        gid = ctx.guild.id if ctx.guild else 0
        with get_connection() as conn:
            top = eko.top_koin(conn, gid, 10)
        if not top:
            await ctx.send("Belum ada data koin.", ephemeral=True)
            return
        guild = ctx.guild
        baris = []
        for i, (uid, bal) in enumerate(top):
            member = guild.get_member(uid) if guild else None
            nama = (member.display_name if member else f"ID {uid}")[:18]
            baris.append([str(i + 1), nama, f"{bal:,} 🪙".replace(",", ".")])
        embed = base_embed("Top Koin Terkaya")
        embed.description = tabel(["#", "Member", "Koin"], baris)
        await ctx.send(embed=embed)

    # ---------- Bank ----------

    @commands.hybrid_command(name="bank", description="Cek saldo bank & bunga harian")
    async def bank(self, ctx: commands.Context):
        """Cek bank: /bank"""
        if ctx.guild is None:
            await ctx.send("❌ Hanya bisa di server.", ephemeral=True)
            return
        with get_connection() as conn:
            akun = eko.get_akun(conn, ctx.guild.id, ctx.author.id)
            bank = _get_bank(conn, ctx.guild.id, ctx.author.id)
        embed = base_embed("🏦 Bank Finch")
        embed.add_field(name="Saldo", value=f"**{akun['balance']}** koin", inline=True)
        embed.add_field(name="Di Bank", value=f"**{bank}** koin", inline=True)
        embed.add_field(
            name="Bunga",
            value=f"**{config.settings.bank_bunga_harian}%**/hari",
            inline=True,
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="deposit", description="Simpan koin ke bank")
    @discord.app_commands.describe(jumlah="Jumlah koin atau 'all'")
    async def deposit(self, ctx: commands.Context, jumlah: str):
        """Deposit: /deposit <jumlah|all>"""
        if ctx.guild is None:
            await ctx.send("❌ Hanya bisa di server.", ephemeral=True)
            return
        with get_connection() as conn:
            akun = eko.get_akun(conn, ctx.guild.id, ctx.author.id)
            n, err = _parse_jumlah_param(jumlah, akun["balance"])
            if err:
                await ctx.send(err, ephemeral=True)
                return
            if n == 0:
                await ctx.send("❌ Tidak ada koin untuk disimpan.", ephemeral=True)
                return
            sisa = eko.kurang_koin(conn, ctx.guild.id, ctx.author.id, n)
            if sisa is None:
                await ctx.send("❌ Koin kamu tidak cukup.", ephemeral=True)
                return
            # Increment atomik — dua deposit konkuren tidak saling menimpa
            # (dulu: baca bank lalu SET bank+n, deposit salah satunya hilang).
            conn.execute(
                "UPDATE economy SET bank = bank + ? WHERE user_id = ? AND guild_id = ?",
                (n, ctx.author.id, ctx.guild.id),
            )
            conn.commit()
            bank_baru = _get_bank(conn, ctx.guild.id, ctx.author.id)
        await ctx.send(
            embed=base_embed(
                "🏦 Deposit Berhasil",
                f"**{n}** 🪙 masuk bank.\nDi bank: **{bank_baru}** koin | Sisa saldo: **{sisa}** koin.",
            )
        )

    @commands.hybrid_command(name="withdraw", description="Tarik koin dari bank")
    @discord.app_commands.describe(jumlah="Jumlah koin atau 'all'")
    async def withdraw(self, ctx: commands.Context, jumlah: str):
        """Withdraw: /withdraw <jumlah|all>"""
        if ctx.guild is None:
            await ctx.send("❌ Hanya bisa di server.", ephemeral=True)
            return
        with get_connection() as conn:
            bank = _get_bank(conn, ctx.guild.id, ctx.author.id)
            n, err = _parse_jumlah_param(jumlah, bank)
            if err:
                await ctx.send(err, ephemeral=True)
                return
            if n == 0:
                await ctx.send("❌ Bank kamu kosong.", ephemeral=True)
                return
            # Atomik: tarik hanya kalau bank masih cukup (anti double-withdraw
            # konkuren — dulu: baca bank dulu lalu SET, dua panggilan bersamaan
            # bisa narik 2x dari saldo yang sama).
            cur = conn.execute(
                "UPDATE economy SET bank = bank - ?"
                " WHERE user_id = ? AND guild_id = ? AND bank >= ?",
                (n, ctx.author.id, ctx.guild.id, n),
            )
            if cur.rowcount == 0:
                await ctx.send("❌ Bank kamu tidak cukup.", ephemeral=True)
                return
            conn.commit()
            sisa_bank = bank - n
            saldo_baru = eko.tambah_koin(conn, ctx.guild.id, ctx.author.id, n)
        await ctx.send(
            embed=base_embed(
                "🏦 Withdraw Berhasil",
                f"**{n}** 🪙 ditarik dari bank.\nSaldo: **{saldo_baru}** koin | Di bank: **{sisa_bank}** koin.",
            )
        )

    @tasks.loop(hours=24)
    async def bunga_harian(self):
        """Bunga bank harian untuk semua row yang bank > 0.

        Server yang mematikan modul ekonomi via dashboard (`economy_enabled=0`)
        dilewati — tidak ada bunga yang dibayar di sana.
        """
        bunga = config.settings.bank_bunga_harian
        if bunga <= 0:
            return
        try:
            with get_connection() as conn:
                mati = {
                    r[0]
                    for r in conn.execute(
                        "SELECT guild_id FROM dashboard_settings"
                        " WHERE key = 'economy_enabled' AND value = '0'"
                    ).fetchall()
                }
                if mati:
                    ph = ",".join("?" for _ in mati)
                    cur = conn.execute(
                        "UPDATE economy SET bank = bank + CAST(bank * ? / 100 AS INTEGER)"
                        # {ph} AMAN: hanya placeholder "?" yang digabung koma
                        # (pola IN (?, ?, ...) standar) — bukan input mentah.
                        f" WHERE bank > 0 AND guild_id NOT IN ({ph})",
                        (bunga, *mati),
                    )
                else:
                    cur = conn.execute(
                        "UPDATE economy SET bank = bank + CAST(bank * ? / 100 AS INTEGER) WHERE bank > 0",
                        (bunga,),
                    )
                n = cur.rowcount
                conn.commit()
            log.info("Bunga bank harian %d%% diterapkan ke %d akun.", bunga, n)
        except Exception:
            log.exception("Gagal terapkan bunga bank harian")

    @bunga_harian.before_loop
    async def _before_bunga(self):
        await self.bot.wait_until_ready()

    # ---------- Lotre ----------

    @commands.hybrid_command(name="lotre-beli", description="Beli tiket lotre mingguan")
    @discord.app_commands.describe(jumlah="Jumlah tiket (1-50)")
    async def lotre_beli(self, ctx: commands.Context, jumlah: int = 1):
        """Beli tiket lotre: /lotre-beli [jumlah]"""
        if ctx.guild is None:
            await ctx.send("❌ Hanya bisa di server.", ephemeral=True)
            return
        if not 1 <= jumlah <= 50:
            await ctx.send("❌ Jumlah tiket 1–50.", ephemeral=True)
            return
        harga = config.settings.lotre_harga_tiket
        total = harga * jumlah
        minggu = _minggu_ini()
        with get_connection() as conn:
            sisa = eko.kurang_koin(conn, ctx.guild.id, ctx.author.id, total)
            if sisa is None:
                await ctx.send(
                    f"❌ Koin tidak cukup. Butuh **{total}** 🪙 untuk {jumlah} tiket.",
                    ephemeral=True,
                )
                return
            for _ in range(jumlah):
                conn.execute(
                    "INSERT INTO lotre_tiket (guild_id, user_id, minggu) VALUES (?, ?, ?)",
                    (ctx.guild.id, ctx.author.id, minggu),
                )
            conn.commit()
        await ctx.send(
            embed=base_embed(
                "🎟️ Tiket Lotre Dibeli!",
                f"**{jumlah}** tiket minggu **{minggu}** — **{total}** 🪙.\n"
                f"Undian tiap Senin 00:00 UTC. Semoga beruntung!",
            )
        )

    @commands.hybrid_command(name="lotre-info", description="Info lotre minggu ini")
    async def lotre_info(self, ctx: commands.Context):
        """Info lotre: /lotre-info"""
        gid = ctx.guild.id if ctx.guild else 0
        minggu = _minggu_ini()
        harga = config.settings.lotre_harga_tiket
        with get_connection() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM lotre_tiket WHERE guild_id = ? AND minggu = ?",
                (gid, minggu),
            ).fetchone()[0]
            saya = 0
            if ctx.guild:
                saya = conn.execute(
                    "SELECT COUNT(*) FROM lotre_tiket WHERE guild_id = ? AND minggu = ? AND user_id = ?",
                    (gid, minggu, ctx.author.id),
                ).fetchone()[0]
        embed = base_embed(f"🎰 Lotre Minggu {minggu}")
        embed.add_field(name="Tiket Terjual", value=f"**{total}**", inline=True)
        embed.add_field(name="Pool Hadiah", value=f"**{total * harga}** 🪙", inline=True)
        embed.add_field(name="Undian", value="Senin 00:00 UTC", inline=True)
        embed.description = f"Harga tiket: **{harga}** 🪙 | Tiketmu: **{saya}**"
        await ctx.send(embed=embed)

    @tasks.loop(hours=1)
    async def undi_lotre(self):
        """Undi lotre tiap jam untuk minggu yang sudah lewat."""
        minggu = _minggu_ini()
        harga = config.settings.lotre_harga_tiket
        try:
            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT DISTINCT guild_id, minggu FROM lotre_tiket WHERE minggu < ?",
                    (minggu,),
                ).fetchall()
        except Exception:
            log.exception("Gagal baca tiket lotre")
            return
        from src.cogs.dashboard_sync import modul_aktif

        for gid, mg in rows:
            if not modul_aktif(gid, "economy_enabled"):
                continue  # modul ekonomi dimatikan di server ini
            try:
                await self._undi_minggu(gid, mg, harga)
            except Exception:
                log.exception("Gagal undi lotre %s/%s", gid, mg)

    @undi_lotre.before_loop
    async def _before_lotre(self):
        await self.bot.wait_until_ready()

    async def _undi_minggu(self, guild_id: int, minggu: str, harga: int) -> None:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT user_id FROM lotre_tiket WHERE guild_id = ? AND minggu = ?"
                " ORDER BY RANDOM() LIMIT 1",
                (guild_id, minggu),
            ).fetchone()
            jumlah = conn.execute(
                "SELECT COUNT(*) FROM lotre_tiket WHERE guild_id = ? AND minggu = ?",
                (guild_id, minggu),
            ).fetchone()[0]
            # Hapus tiket DULU baru kredit — crash di tengah = hadiah hilang
            # (aman), bukan diundi 2x
            conn.execute(
                "DELETE FROM lotre_tiket WHERE guild_id = ? AND minggu = ?",
                (guild_id, minggu),
            )
            conn.commit()
            if row:
                pemenang = row[0]
                hadiah = jumlah * harga
                eko.tambah_koin(conn, guild_id, pemenang, hadiah)
            else:
                pemenang, hadiah = None, 0
        if pemenang is None:
            return
        guild = self.bot.get_guild(guild_id)
        ch = guild.system_channel if guild else None
        if ch is None:
            log.info("Lotre %s/%s: system channel tidak ada; pemenang %s.", guild_id, minggu, pemenang)
            return
        try:
            await ch.send(
                f"🎰 **LOTRE {minggu} DIUNDI!**\n"
                f"🎉 Selamat <@{pemenang}> memenangkan **{hadiah}** 🪙 dari {jumlah} tiket!"
            )
        except discord.HTTPException:
            pass

    # ---------- Gaji ----------

    @tasks.loop(hours=24)
    async def bayar_gaji(self):
        """Gaji tiap 7 hari untuk role di GAJI_ROLES. Tanpa announce, hanya log."""
        daftar = config.settings.gaji_roles_list()
        if not daftar:
            return
        from src.cogs.dashboard_sync import modul_aktif

        now = discord.utils.utcnow()
        for guild in self.bot.guilds:
            if not modul_aktif(guild.id, "economy_enabled"):
                continue  # modul ekonomi dimatikan di server ini
            try:
                with get_connection() as conn:
                    row = conn.execute(
                        "SELECT terakhir FROM gaji_state WHERE guild_id = ?",
                        (guild.id,),
                    ).fetchone()
                    if row and row[0]:
                        try:
                            terakhir = datetime.datetime.fromisoformat(row[0])
                        except ValueError:
                            terakhir = None
                        if terakhir is not None and (now - terakhir).total_seconds() < 7 * 86400:
                            continue
                    # Tandai periode gaji DULU sebelum membayar — crash di tengah
                    # loop = sebagian member kelewat gaji, bukan dibayar 2x.
                    conn.execute(
                        "INSERT INTO gaji_state (guild_id, terakhir) VALUES (?, ?)"
                        " ON CONFLICT(guild_id) DO UPDATE SET terakhir = excluded.terakhir",
                        (guild.id, now.isoformat()),
                    )
                    conn.commit()
                    dibayar = 0
                    for nama_role, jumlah in daftar:
                        role = discord.utils.get(guild.roles, name=nama_role)
                        if role is None:
                            continue
                        for m in role.members:
                            if m.bot:
                                continue
                            eko.tambah_koin(conn, guild.id, m.id, jumlah)
                            dibayar += 1
                    conn.commit()
                if dibayar:
                    log.info("Gaji dibayar di %s: %d member.", guild.name, dibayar)
            except Exception:
                log.exception("Gagal bayar gaji di guild %s", guild.id)

    @bayar_gaji.before_loop
    async def _before_gaji(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Economy(bot))
