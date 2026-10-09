"""Giveaway — undian hadiah otomatis.

- `/giveaway <durasi> <pemenang> <hadiah>` (mod): posting giveaway + tombol "Ikut".
- Background task tiap 30 detik: undi pemenang otomatis saat waktu habis.
- Tombol "Reroll" setelah selesai untuk undi ulang.
- Data tersimpan di SQLite sehingga survive restart.
"""
import datetime
import logging
import random

import discord
from discord.ext import commands, tasks

from src.store import get_connection
from src.utils import economy as eko
from src.utils.embeds import base_embed
from src.utils.filters import parse_durasi  # re-export: dipakai polls/reminders & test

log = logging.getLogger("finch")

JOIN_ID = "finch:giveaway-join"
REROLL_ID = "finch:giveaway-reroll"

def pilih_pemenang(peserta: list[int], jumlah: int, rng=None) -> list[int]:
    """Pilih pemenang acak. Pure function — `rng` bisa di-seed untuk tes."""
    rng = rng or random
    if not peserta:
        return []
    return rng.sample(peserta, min(jumlah, len(peserta)))


def _embed_jalan(prize: str, host_mention: str, ends_ts: int, winners: int, syarat: str = "") -> discord.Embed:
    desc = (
        f"**Hadiah:** {prize}\n\n"
        f"Berakhir <t:{ends_ts}:R> (<t:{ends_ts}:f>)\n"
        f"Pemenang: **{winners}** orang\n"
        f"Host: {host_mention}\n"
    )
    if syarat:
        desc += f"\n📌 Syarat ikut: {syarat}\n"
    desc += "\nKlik tombol **Ikut** di bawah!"
    return base_embed("🎉 GIVEAWAY!", desc)


def _cek_syarat(
    level_user: int,
    koin_user: int,
    role_ids_user: set[int],
    min_level: int,
    min_koin: int,
    role_syarat: int,
) -> str | None:
    """Cek syarat ikut giveaway. Return alasan penolakan, atau None jika lolos.

    Pure function — gampang di-unit-test.
    """
    if min_level and level_user < min_level:
        return (
            f"❌ Syarat level **{min_level}** belum terpenuhi "
            f"(levelmu **{level_user}**)."
        )
    if min_koin and koin_user < min_koin:
        return (
            f"❌ Syarat koin **{min_koin}** 🪙 belum terpenuhi "
            f"(saldomu **{koin_user}** 🪙)."
        )
    if role_syarat and role_syarat not in role_ids_user:
        return "❌ Kamu tidak punya role yang disyaratkan giveaway ini."
    return None


def _embed_selesai(prize: str, pemenang: list[int]) -> discord.Embed:
    if pemenang:
        mentions = " ".join(f"<@{u}>" for u in pemenang)
        desc = f"**Hadiah:** {prize}\n\n🎉 Pemenang: {mentions}\nSelamat! Hubungi host untuk klaim hadiahmu."
    else:
        desc = f"**Hadiah:** {prize}\n\n😢 Tidak ada peserta."
    return base_embed("🎉 GIVEAWAY BERAKHIR", desc)


class GiveawayView(discord.ui.View):
    """Persistent — tombol 'Ikut'."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Ikut",
        style=discord.ButtonStyle.primary,
        custom_id=JOIN_ID,
    )
    async def ikut(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.bot:
            await interaction.response.send_message("❌ Bot tidak boleh pakai tombol ini.", ephemeral=True)
            return
        mid = interaction.message.id
        uid = interaction.user.id
        with get_connection() as conn:
            row = conn.execute(
                "SELECT ended, COALESCE(min_level, 0), COALESCE(min_koin, 0),"
                " COALESCE(role_syarat, 0), guild_id FROM giveaways WHERE message_id = ?",
                (mid,),
            ).fetchone()
            if row is None or row[0]:
                await interaction.response.send_message(
                    "❌ Giveaway ini sudah berakhir.", ephemeral=True
                )
                return
            _ended, min_level, min_koin, role_syarat, gid = row
            ada = conn.execute(
                "SELECT 1 FROM giveaway_entries WHERE message_id = ? AND user_id = ?",
                (mid, uid),
            ).fetchone()
            if ada:
                conn.execute(
                    "DELETE FROM giveaway_entries WHERE message_id = ? AND user_id = ?",
                    (mid, uid),
                )
                conn.commit()
                await interaction.response.send_message(
                    "❌ Kamu keluar dari giveaway.", ephemeral=True
                )
                return
            # Cek syarat ikut (level, koin, role)
            lvl_row = conn.execute(
                "SELECT level FROM users WHERE user_id = ? AND guild_id = ?",
                (uid, gid or 0),
            ).fetchone()
            koin_row = conn.execute(
                "SELECT balance FROM economy WHERE user_id = ? AND guild_id = ?",
                (uid, gid or 0),
            ).fetchone()
            level_user = lvl_row[0] if lvl_row else 1
            koin_user = koin_row[0] if koin_row and koin_row[0] else 0
            member = interaction.user
            role_ids = {r.id for r in getattr(member, "roles", []) or []}
            alasan = _cek_syarat(
                level_user, koin_user, role_ids, min_level, min_koin, role_syarat
            )
            if alasan:
                await interaction.response.send_message(alasan, ephemeral=True)
                return
            conn.execute(
                "INSERT INTO giveaway_entries (message_id, user_id) VALUES (?, ?)",
                (mid, uid),
            )
            conn.commit()
        await interaction.response.send_message(
            "🎉 Kamu ikut giveaway! Semoga beruntung!", ephemeral=True
        )


class RerollView(discord.ui.View):
    """Persistent — tombol 'Reroll' setelah giveaway selesai."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Reroll",
        style=discord.ButtonStyle.secondary,
        custom_id=REROLL_ID,
    )
    async def reroll(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.user
        if not (
            isinstance(member, discord.Member)
            and member.guild_permissions.manage_messages
        ):
            await interaction.response.send_message(
                "❌ Hanya moderator yang bisa reroll.", ephemeral=True
            )
            return
        mid = interaction.message.id
        with get_connection() as conn:
            row = conn.execute(
                "SELECT winners_count, prize, guild_id, COALESCE(prize_coins, 0),"
                " COALESCE(reroll_count, 0), COALESCE(hadiah_role, 0)"
                " FROM giveaways WHERE message_id = ?",
                (mid,),
            ).fetchone()
            if not row:
                await interaction.response.send_message(
                    "❌ Data giveaway tidak ketemu.", ephemeral=True
                )
                return
            winners_count, prize, guild_id, prize_coins, reroll_count, hadiah_role = row
            if prize_coins and reroll_count >= 1:
                # Cegah cetak koin: giveaway koin hanya boleh di-reroll 1x
                await interaction.response.send_message(
                    "❌ Giveaway koin hanya bisa di-reroll 1x.", ephemeral=True
                )
                return
            entries = [
                r[0]
                for r in conn.execute(
                    "SELECT user_id FROM giveaway_entries WHERE message_id = ?",
                    (mid,),
                )
            ]
        pemenang = pilih_pemenang(entries, winners_count)
        try:
            await interaction.message.edit(embed=_embed_selesai(prize, pemenang))
        except discord.HTTPException:
            pass
        if pemenang:
            mentions = " ".join(f"<@{u}>" for u in pemenang)
            ekstra = ""
            if prize_coins:
                with get_connection() as conn:
                    # Guarded increment: klaim jatah reroll atomik DULU.
                    # Double-click / dua mod bersamaan → hanya satu yang dapat rowcount=1.
                    cur = conn.execute(
                        "UPDATE giveaways SET reroll_count = reroll_count + 1"
                        " WHERE message_id = ? AND COALESCE(reroll_count, 0) < 1",
                        (mid,),
                    )
                    if cur.rowcount == 0:
                        conn.rollback()
                        await interaction.response.send_message(
                            "❌ Giveaway koin hanya bisa di-reroll 1x.", ephemeral=True
                        )
                        return
                    for uid in pemenang:
                        eko.tambah_koin(conn, guild_id or 0, uid, prize_coins)
                    conn.commit()
                ekstra = f" (masing-masing +**{prize_coins}** 🪙)"
            # Hadiah role untuk pemenang baru
            cog = interaction.client.get_cog("Giveaway")
            if cog is not None and hadiah_role:
                await cog._kasih_role_hadiah(guild_id or 0, hadiah_role, pemenang, mid)
            await interaction.response.send_message(
                f"🔁 Reroll! Pemenang baru: {mentions}{ekstra}"
            )
        else:
            await interaction.response.send_message(
                "😢 Tidak ada peserta untuk di-reroll.", ephemeral=True
            )


class Giveaway(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Guard anti-overlap: message_id yang sedang diproses _akhiri.
        # Mencegah iterasi loop 30-detik berikutnya memproses row yang sama
        # (double payout + pengumuman ganda) saat satu iterasi lambat.
        self._memproses: set[int] = set()
        self.cek_giveaway.start()
        self.cek_rutin.start()

    def cog_unload(self):
        self.cek_giveaway.cancel()
        self.cek_rutin.cancel()

    @tasks.loop(seconds=30)
    async def cek_giveaway(self):
        now = discord.utils.utcnow().isoformat()
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT message_id, channel_id, guild_id, winners_count, prize, "
                "host_id, COALESCE(prize_coins, 0), COALESCE(hadiah_role, 0) "
                "FROM giveaways WHERE ended = 0 AND ends_at <= ?",
                (now,),
            ).fetchall()
        for message_id, channel_id, guild_id, winners_count, prize, host_id, prize_coins, hadiah_role in rows:
            if message_id in self._memproses:
                continue  # sedang diproses iterasi sebelumnya — skip
            self._memproses.add(message_id)
            try:
                await self._akhiri(
                    message_id, channel_id, guild_id, winners_count, prize,
                    host_id or 0, prize_coins or 0, hadiah_role or 0,
                )
            except Exception:
                log.exception("Gagal mengakhiri giveaway %s", message_id)
            finally:
                self._memproses.discard(message_id)

    @cek_giveaway.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()

    def _tandai_selesai(self, message_id: int) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE giveaways SET ended = 1 WHERE message_id = ?", (message_id,)
            )
            conn.commit()

    def _teks_syarat(
        self, guild_id: int, min_level: int, min_koin: int, role_syarat: int
    ) -> str:
        """Teks syarat untuk ditampilkan di embed. Pure-ish (lookup role best effort)."""
        bagian = []
        if min_level:
            bagian.append(f"level {min_level}+")
        if min_koin:
            bagian.append(f"{min_koin} 🪙")
        if role_syarat:
            nama_role = None
            guild = self.bot.get_guild(guild_id)
            if guild is not None:
                role = guild.get_role(role_syarat)
                if role is not None:
                    nama_role = role.name
            bagian.append(f"role {nama_role}" if nama_role else "role khusus")
        return ", ".join(bagian)

    async def _posting_giveaway(
        self,
        channel,
        guild_id: int,
        host_id: int,
        detik: int,
        pemenang_count: int,
        hadiah_teks: str,
        prize_coins: int = 0,
        min_level: int = 0,
        min_koin: int = 0,
        role_syarat: int = 0,
        hadiah_role: int = 0,
    ) -> int | None:
        """Posting pesan giveaway + simpan row DB. Return message_id atau None bila gagal."""
        ends = discord.utils.utcnow() + datetime.timedelta(seconds=detik)
        ends_ts = int(ends.timestamp())
        syarat_teks = self._teks_syarat(guild_id, min_level, min_koin, role_syarat)
        try:
            msg = await channel.send(
                embed=_embed_jalan(
                    hadiah_teks, f"<@{host_id}>", ends_ts, pemenang_count, syarat_teks
                ),
                view=GiveawayView(),
            )
        except discord.HTTPException:
            return None
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO giveaways "
                "(message_id, channel_id, guild_id, ends_at, winners_count, prize,"
                " host_id, prize_coins, min_level, min_koin, role_syarat, hadiah_role) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    msg.id,
                    channel.id,
                    guild_id,
                    ends.isoformat(),
                    pemenang_count,
                    hadiah_teks,
                    host_id,
                    prize_coins,
                    min_level,
                    min_koin,
                    role_syarat,
                    hadiah_role,
                ),
            )
            conn.commit()
        return msg.id

    async def _kasih_role_hadiah(
        self, guild_id: int, hadiah_role: int, pemenang: list[int], message_id: int
    ) -> None:
        """Kasih role hadiah ke pemenang (best effort per member)."""
        if not hadiah_role or not pemenang:
            return
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            log.warning("Giveaway %s: guild %s tidak ketemu.", message_id, guild_id)
            return
        role = guild.get_role(hadiah_role)
        if role is None:
            log.warning(
                "Giveaway %s: role hadiah %s tidak ketemu.", message_id, hadiah_role
            )
            return
        for uid in pemenang:
            member = guild.get_member(uid)
            if member is None:
                continue
            try:
                await member.add_roles(role, reason=f"Hadiah giveaway {message_id}")
            except (discord.Forbidden, discord.HTTPException) as e:
                log.warning(
                    "Giveaway %s: gagal kasih role ke %s (%s).", message_id, uid, e
                )

    async def _umumkan_koin(
        self,
        channel,
        guild_id: int,
        pemenang: list[int],
        prize_coins: int,
        winners_count: int,
        host_id: int,
    ) -> None:
        """Distribusi hadiah koin + pengumuman. Refund ke host kalau tanpa peserta."""
        if pemenang:
            with get_connection() as conn:
                for uid in pemenang:
                    eko.tambah_koin(conn, guild_id, uid, prize_coins)
            mentions = " ".join(f"<@{u}>" for u in pemenang)
            await channel.send(
                f"🎉 **GIVEAWAY BERAKHIR!**\nSelamat {mentions}! "
                f"Masing-masing dapat **{prize_coins}** 🪙!"
            )
        else:
            refund = prize_coins * winners_count
            if host_id:
                with get_connection() as conn:
                    eko.tambah_koin(conn, guild_id, host_id, refund)
            await channel.send(
                f"🎉 **GIVEAWAY BERAKHIR!**\n😢 Tidak ada peserta — "
                f"**{refund}** 🪙 dikembalikan ke host."
            )

    async def _akhiri(
        self,
        message_id: int,
        channel_id: int,
        guild_id: int,
        winners_count: int,
        prize: str,
        host_id: int = 0,
        prize_coins: int = 0,
        hadiah_role: int = 0,
    ) -> None:
        # Ambil pemenang DULU — tidak tergantung pesan asli masih ada atau tidak.
        with get_connection() as conn:
            entries = [
                r[0]
                for r in conn.execute(
                    "SELECT user_id FROM giveaway_entries WHERE message_id = ?",
                    (message_id,),
                )
            ]
        pemenang = pilih_pemenang(entries, winners_count)

        # Hadiah role: kasih ke pemenang (best effort).
        await self._kasih_role_hadiah(guild_id, hadiah_role, pemenang, message_id)

        # Cari channel (cache dulu, fallback ke API).
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException) as e:
                log.warning(
                    "Giveaway %s: channel %s tidak bisa diakses (%s) — escrow dikembalikan, ditandai selesai.",
                    message_id,
                    channel_id,
                    e,
                )
                # Kembalikan escrow ke host (channel dihapus sebelum timer habis)
                refund = (prize_coins or 0) * (winners_count or 0)
                if host_id and refund > 0:
                    with get_connection() as conn:
                        eko.tambah_koin(conn, guild_id, host_id, refund)
                        conn.commit()
                self._tandai_selesai(message_id)
                return

        # Tandai selesai DULU sebelum pengumuman — kalau pengumuman gagal
        # (API error), loop berikutnya tidak akan memproses ulang (anti double payout).
        self._tandai_selesai(message_id)

        # Edit pesan asli (best effort — kegagalan dicatat, bukan ditelan).
        try:
            msg = await channel.fetch_message(message_id)
            await msg.edit(embed=_embed_selesai(prize, pemenang), view=RerollView())
        except (discord.NotFound, discord.Forbidden, discord.HTTPException) as e:
            log.warning("Giveaway %s: gagal edit pesan asli (%s).", message_id, e)

        # SELALU kirim pengumuman saat timer habis — termasuk kalau tidak ada peserta.
        try:
            if prize_coins > 0:
                await self._umumkan_koin(
                    channel, guild_id, pemenang, prize_coins, winners_count, host_id
                )
            elif pemenang:
                mentions = " ".join(f"<@{u}>" for u in pemenang)
                await channel.send(
                    f"🎉 **GIVEAWAY BERAKHIR!**\nSelamat {mentions}! Kamu memenangkan **{prize}**!"
                )
            else:
                await channel.send(
                    f"🎉 **GIVEAWAY BERAKHIR!**\n😢 Tidak ada peserta untuk **{prize}**."
                )
        except discord.HTTPException as e:
            log.warning("Giveaway %s: gagal kirim pengumuman (%s).", message_id, e)

    @commands.hybrid_command(
        name="giveaway", description="Mulai giveaway (khusus mod)"
    )
    @commands.has_permissions(manage_messages=True)
    @discord.app_commands.describe(
        durasi="Contoh: 30s, 10m, 2h, 1d",
        pemenang="Jumlah pemenang",
        hadiah="Hadiah yang diundi",
        min_level="Syarat level minimum (0 = tanpa syarat)",
        min_koin="Syarat saldo koin minimum (0 = tanpa syarat)",
        role="Syarat role (opsional)",
    )
    async def giveaway(
        self,
        ctx: commands.Context,
        durasi: str,
        pemenang: int,
        *,
        hadiah: str,
        min_level: int = 0,
        min_koin: int = 0,
        role: discord.Role | None = None,
    ):
        """Mulai giveaway: !giveaway 10m 1 Nitro sebulan / /giveaway"""
        if ctx.guild is None:
            await ctx.send("❌ Hanya bisa di server.", ephemeral=True)
            return
        MAKS_DETIK = 30 * 86400
        detik = parse_durasi(durasi)
        if detik is None or detik < 10:
            await ctx.send(
                "❌ Format durasi salah. Contoh: `30s`, `10m`, `2h`, `1d` (minimal 10 detik).",
                ephemeral=True,
            )
            return
        if detik > MAKS_DETIK:
            await ctx.send("❌ Durasi maksimal 30 hari.", ephemeral=True)
            return
        pemenang = max(1, min(pemenang, 20))
        min_level = max(0, min_level)
        min_koin = max(0, min_koin)

        # Ack interaksi slash biar tidak "not respond" (posting via channel biasa)
        await ctx.defer()
        message_id = await self._posting_giveaway(
            ctx.channel,
            ctx.guild.id,
            ctx.author.id,
            detik,
            pemenang,
            hadiah,
            min_level=min_level,
            min_koin=min_koin,
            role_syarat=role.id if role else 0,
        )
        if message_id is None:
            await ctx.send("❌ Gagal memposting giveaway.", ephemeral=True)
            return
        log.info("Giveaway dimulai: %s (%ds)", hadiah, detik)
        await ctx.send("🎉 Giveaway diposting!", ephemeral=True)

    @commands.hybrid_command(
        name="g-koin", description="Giveaway berhadiah koin (khusus mod)"
    )
    @commands.has_permissions(manage_messages=True)
    @discord.app_commands.describe(
        durasi="Contoh: 30s, 10m, 2h, 1d",
        jumlah="Koin per pemenang",
        pemenang="Jumlah pemenang",
        min_level="Syarat level minimum (0 = tanpa syarat)",
        min_koin="Syarat saldo koin minimum (0 = tanpa syarat)",
        role="Syarat role (opsional)",
    )
    async def g_koin(
        self,
        ctx: commands.Context,
        durasi: str,
        jumlah: int,
        pemenang: int = 1,
        min_level: int = 0,
        min_koin: int = 0,
        role: discord.Role | None = None,
    ):
        """Giveaway koin: /g-koin 10m 500 2 (2 pemenang @500 koin)"""
        if ctx.guild is None:
            await ctx.send("❌ Hanya bisa di server.", ephemeral=True)
            return
        MAKS_DETIK = 30 * 86400
        detik = parse_durasi(durasi)
        if detik is None or detik < 10:
            await ctx.send(
                "❌ Format durasi salah. Contoh: `30s`, `10m`, `2h`, `1d` (minimal 10 detik).",
                ephemeral=True,
            )
            return
        if detik > MAKS_DETIK:
            await ctx.send("❌ Durasi maksimal 30 hari.", ephemeral=True)
            return
        if jumlah <= 0:
            await ctx.send("❌ Jumlah koin harus lebih dari 0.", ephemeral=True)
            return
        pemenang = max(1, min(pemenang, 20))
        min_level = max(0, min_level)
        min_koin = max(0, min_koin)
        total = jumlah * pemenang
        # Escrow: koin host dipotong di awal (tetap di command)
        with get_connection() as conn:
            sisa = eko.kurang_koin(conn, ctx.guild.id, ctx.author.id, total)
            if sisa is None:
                await ctx.send(
                    f"❌ Koin kamu tidak cukup. Butuh **{total}** 🪙 "
                    f"({jumlah} × {pemenang} pemenang).",
                    ephemeral=True,
                )
                return

        def _refund_escrow():
            with get_connection() as conn:
                eko.tambah_koin(conn, ctx.guild.id, ctx.author.id, total)

        hadiah_teks = f"{jumlah} 🪙 koin"
        await ctx.defer()
        try:
            message_id = await self._posting_giveaway(
                ctx.channel,
                ctx.guild.id,
                ctx.author.id,
                detik,
                pemenang,
                hadiah_teks,
                prize_coins=jumlah,
                min_level=min_level,
                min_koin=min_koin,
                role_syarat=role.id if role else 0,
            )
        except Exception:
            # Crash/error di antara potong escrow & simpan row → kembalikan escrow
            _refund_escrow()
            log.exception("g-koin: posting gagal, escrow dikembalikan")
            await ctx.send("❌ Gagal memposting giveaway. Koin dikembalikan.", ephemeral=True)
            return
        if message_id is None:
            _refund_escrow()
            await ctx.send("❌ Gagal memposting giveaway. Koin dikembalikan.", ephemeral=True)
            return
        log.info("Giveaway koin dimulai: %d koin x%d (%ds)", jumlah, pemenang, detik)
        await ctx.send(
            f"🎉 Giveaway diposting! **{total}** 🪙 ditahan sebagai hadiah.",
            ephemeral=True,
        )

    @commands.hybrid_command(
        name="g-role", description="Giveaway berhadiah role (khusus mod)"
    )
    @commands.has_permissions(manage_messages=True)
    @discord.app_commands.describe(
        durasi="Contoh: 30s, 10m, 2h, 1d",
        role="Role yang dihadiahkan",
        pemenang="Jumlah pemenang",
    )
    async def g_role(
        self, ctx: commands.Context, durasi: str, role: discord.Role, pemenang: int = 1
    ):
        """Giveaway role: /g-role 10m @VIP 2"""
        if ctx.guild is None:
            await ctx.send("❌ Hanya bisa di server.", ephemeral=True)
            return
        MAKS_DETIK = 30 * 86400
        detik = parse_durasi(durasi)
        if detik is None or detik < 10:
            await ctx.send(
                "❌ Format durasi salah. Contoh: `30s`, `10m`, `2h`, `1d` (minimal 10 detik).",
                ephemeral=True,
            )
            return
        if detik > MAKS_DETIK:
            await ctx.send("❌ Durasi maksimal 30 hari.", ephemeral=True)
            return
        pemenang = max(1, min(pemenang, 20))
        hadiah_teks = f"🎖️ Role {role.name}"
        await ctx.defer()
        message_id = await self._posting_giveaway(
            ctx.channel,
            ctx.guild.id,
            ctx.author.id,
            detik,
            pemenang,
            hadiah_teks,
            hadiah_role=role.id,
        )
        if message_id is None:
            await ctx.send("❌ Gagal memposting giveaway.", ephemeral=True)
            return
        log.info("Giveaway role dimulai: %s x%d (%ds)", role.name, pemenang, detik)
        await ctx.send("🎉 Giveaway diposting!", ephemeral=True)

    @commands.hybrid_command(
        name="donasi-koin", description="Donasi koin ke pool server (untuk giveaway rutin)"
    )
    @discord.app_commands.describe(jumlah="Jumlah koin yang didonasikan")
    async def donasi_koin(self, ctx: commands.Context, jumlah: int):
        """Donasi koin: /donasi-koin 500"""
        if ctx.guild is None:
            await ctx.send("❌ Hanya bisa di server.", ephemeral=True)
            return
        if jumlah <= 0:
            await ctx.send("❌ Jumlah harus lebih dari 0.", ephemeral=True)
            return
        with get_connection() as conn:
            sisa = eko.kurang_koin(conn, ctx.guild.id, ctx.author.id, jumlah)
            if sisa is None:
                await ctx.send("❌ Koin kamu tidak cukup.", ephemeral=True)
                return
            conn.execute(
                "INSERT INTO server_pool (guild_id, koin) VALUES (?, ?) "
                "ON CONFLICT(guild_id) DO UPDATE SET koin = koin + ?",
                (ctx.guild.id, jumlah, jumlah),
            )
            conn.commit()
            total = conn.execute(
                "SELECT koin FROM server_pool WHERE guild_id = ?", (ctx.guild.id,)
            ).fetchone()[0]
        await ctx.send(
            embed=base_embed(
                "💰 Donasi Diterima!",
                f"{ctx.author.mention} donasi **{jumlah}** 🪙 ke pool server.\n"
                f"Total pool sekarang: **{total}** 🪙",
            )
        )

    @commands.hybrid_command(
        name="g-rutin", description="Buat giveaway rutin otomatis (khusus mod)"
    )
    @commands.has_permissions(manage_messages=True)
    @discord.app_commands.describe(
        interval="Seberapa sering (minimal 1 jam). Contoh: 1h, 12h, 1d",
        pemenang="Jumlah pemenang",
        hadiah="Hadiah yang diundi",
        koin="Koin per pemenang (0 = tanpa koin, diambil dari pool)",
    )
    async def g_rutin(
        self,
        ctx: commands.Context,
        interval: str,
        pemenang: int,
        hadiah: str,
        koin: int = 0,
    ):
        """Giveaway rutin: /g-rutin 1d 1 Nitro 0"""
        if ctx.guild is None:
            await ctx.send("❌ Hanya bisa di server.", ephemeral=True)
            return
        detik = parse_durasi(interval)
        if detik is None or detik < 3600:
            await ctx.send(
                "❌ Interval minimal **1 jam**. Contoh: `1h`, `12h`, `1d`.",
                ephemeral=True,
            )
            return
        if koin < 0:
            await ctx.send("❌ Koin tidak boleh negatif.", ephemeral=True)
            return
        pemenang = max(1, min(pemenang, 20))
        with get_connection() as conn:
            cur = conn.execute(
                "INSERT INTO giveaway_rutin "
                "(guild_id, channel_id, interval_detik, pemenang, hadiah, koin, host_id, terakhir) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
                (
                    ctx.guild.id,
                    ctx.channel.id,
                    detik,
                    pemenang,
                    hadiah,
                    koin,
                    ctx.author.id,
                ),
            )
            rid = cur.lastrowid
            conn.commit()
        koin_teks = f" + **{koin}** 🪙/pemenang (dari pool)" if koin else ""
        await ctx.send(
            f"✅ Giveaway rutin **#{rid}** dibuat di {ctx.channel.mention}: "
            f"tiap **{interval}**, **{pemenang}** pemenang, hadiah **{hadiah}**{koin_teks}."
        )

    @commands.hybrid_command(
        name="g-rutin-list", description="Lihat daftar giveaway rutin"
    )
    async def g_rutin_list(self, ctx: commands.Context):
        """List giveaway rutin: /g-rutin-list"""
        if ctx.guild is None:
            await ctx.send("❌ Hanya bisa di server.", ephemeral=True)
            return
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT id, channel_id, interval_detik, pemenang, hadiah, koin, terakhir "
                "FROM giveaway_rutin WHERE guild_id = ? ORDER BY id",
                (ctx.guild.id,),
            ).fetchall()
        if not rows:
            await ctx.send("Belum ada giveaway rutin.", ephemeral=True)
            return
        embed = base_embed("🔁 Giveaway Rutin")
        for rid, ch_id, interval, pemenang, hadiah, koin, terakhir in rows:
            jam = interval // 3600
            interval_teks = f"{jam} jam" if interval % 3600 == 0 else f"{interval} dtk"
            nilai = (
                f"📍 <#{ch_id}>\n⏱️ Tiap {interval_teks} • 🏆 {pemenang} pemenang\n"
                f"🎁 {hadiah}" + (f" + {koin} 🪙" if koin else "")
            )
            embed.add_field(name=f"#{rid}", value=nilai, inline=True)
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="g-rutin-hapus", description="Hapus giveaway rutin (khusus mod)"
    )
    @commands.has_permissions(manage_messages=True)
    @discord.app_commands.describe(id="ID rutin (lihat /g-rutin-list)")
    async def g_rutin_hapus(self, ctx: commands.Context, id: int):
        """Hapus giveaway rutin: /g-rutin-hapus 3"""
        if ctx.guild is None:
            await ctx.send("❌ Hanya bisa di server.", ephemeral=True)
            return
        with get_connection() as conn:
            cur = conn.execute(
                "DELETE FROM giveaway_rutin WHERE id = ? AND guild_id = ?",
                (id, ctx.guild.id),
            )
            conn.commit()
        if cur.rowcount:
            await ctx.send(f"✅ Giveaway rutin **#{id}** dihapus.")
        else:
            await ctx.send(f"❌ Rutin **#{id}** tidak ketemu.", ephemeral=True)

    @tasks.loop(minutes=5)
    async def cek_rutin(self):
        now = discord.utils.utcnow()
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT id, guild_id, channel_id, interval_detik, pemenang, hadiah,"
                " koin, host_id, terakhir FROM giveaway_rutin"
            ).fetchall()
        for rid, gid, ch_id, interval, pemenang, hadiah, koin, host_id, terakhir in rows:
            try:
                await self._proses_rutin(now, rid, gid, ch_id, interval, pemenang, hadiah, koin, host_id, terakhir)
            except Exception:
                # Jangan biarkan satu rutin yang error membunuh loop 5-menit selamanya.
                log.exception("Gagal proses giveaway rutin #%s", rid)

    async def _proses_rutin(
        self, now, rid: int, gid: int, ch_id: int, interval: int,
        pemenang: int, hadiah: str, koin: int, host_id: int, terakhir: str | None,
    ) -> None:
        # Sudah waktunya?
        jatuh_tempo = True
        if terakhir:
            try:
                last = datetime.datetime.fromisoformat(terakhir)
                if last.tzinfo is None:
                    last = last.replace(tzinfo=datetime.timezone.utc)
                jatuh_tempo = (now - last).total_seconds() >= interval
            except ValueError:
                jatuh_tempo = True
        if not jatuh_tempo:
            return
        channel = self.bot.get_channel(ch_id)
        if channel is None:
            return  # channel hilang — skip, coba lagi interval berikut
            # Hadiah koin diambil dari pool server — cek dulu, potong SETELAH posting sukses
            # (bug lama: dipotong sebelum posting → pool terkuras tanpa giveaway)
            koin_pakai = koin or 0
            perlu = koin_pakai * pemenang
            if koin_pakai > 0:
                with get_connection() as conn:
                    pool = conn.execute(
                        "SELECT koin FROM server_pool WHERE guild_id = ?", (gid,)
                    ).fetchone()
                    if not pool or (pool[0] or 0) < perlu:
                        log.warning(
                            "Giveaway rutin #%s: pool tidak cukup (%s), hadiah koin dinonaktifkan.",
                            rid,
                            pool[0] if pool else 0,
                        )
                        koin_pakai = 0
                        perlu = 0
            hadiah_teks = hadiah + (f" + {koin_pakai} 🪙" if koin_pakai else "")
            message_id = await self._posting_giveaway(
                channel, gid, host_id, interval, pemenang, hadiah_teks,
                prize_coins=koin_pakai,
            )
            if message_id:
                with get_connection() as conn:
                    batal = False
                    if perlu > 0:
                        # Guarded deduct: hanya potong bila pool masih cukup
                        cur = conn.execute(
                            "UPDATE server_pool SET koin = koin - ?"
                            " WHERE guild_id = ? AND koin >= ?",
                            (perlu, gid, perlu),
                        )
                        if cur.rowcount == 0:
                            # Pool kalah race: BATALKAN giveaway yang baru diposting
                            # (jangan biarkan prize_coins>0 — nanti _akhiri mencetak koin dari udara).
                            batal = True
                            conn.execute(
                                "UPDATE giveaways SET ended = 1, prize_coins = 0 WHERE message_id = ?",
                                (message_id,),
                            )
                            log.error(
                                "Giveaway rutin #%s: pool habis saat settlement — giveaway dibatalkan.",
                                rid,
                            )
                    conn.execute(
                        "UPDATE giveaway_rutin SET terakhir = ? WHERE id = ?",
                        (now.isoformat(), rid),
                    )
                    conn.commit()
                if batal:
                    try:
                        msg_batal = await channel.fetch_message(message_id)
                        await msg_batal.edit(
                            embed=_embed_selesai(hadiah_teks + " (DIBATALKAN — pool koin tidak cukup)", []),
                            view=None,
                        )
                    except discord.HTTPException:
                        pass
                    return
                log.info("Giveaway rutin #%s diposting (msg %s).", rid, message_id)

    @cek_rutin.before_loop
    async def _before_rutin(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Giveaway(bot))
    bot.add_view(GiveawayView())
    bot.add_view(RerollView())
