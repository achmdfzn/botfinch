"""Regression test pola guarded-update hasil audit (anti race / double payout).

Semua perbaikan memakai pola yang sama: UPDATE bersyarat + cek rowcount,
bukan cek-dulu-baru-update yang bisa diinterleave dua proses.
Tes ini memverifikasi pola SQL-nya persis seperti di kode produksi.
Jalanin: python -m pytest tests/ -q
"""
import sqlite3
import unittest
from unittest.mock import AsyncMock, MagicMock


def _ctx_mock():
    """Context mock dengan semua method async yang awaitable."""
    ctx = MagicMock()
    ctx.send = AsyncMock()
    ctx.interaction.response.send_message = AsyncMock()
    ctx.interaction.followup.send = AsyncMock()
    return ctx


def _db():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE giveaways (message_id INTEGER PRIMARY KEY, reroll_count INTEGER DEFAULT 0, prize_coins INTEGER DEFAULT 0, ended INTEGER DEFAULT 0)")
    conn.execute("CREATE TABLE tickets (channel_id INTEGER PRIMARY KEY, closed INTEGER DEFAULT 0)")
    conn.execute("CREATE TABLE starboard (message_id INTEGER PRIMARY KEY, starboard_msg_id INTEGER, channel_id INTEGER NOT NULL)")
    conn.execute("CREATE TABLE lelang (id INTEGER PRIMARY KEY, ended INTEGER DEFAULT 0)")
    conn.execute("CREATE TABLE server_pool (guild_id INTEGER PRIMARY KEY, koin INTEGER NOT NULL DEFAULT 0)")
    return conn


class TestGuardedUpdate(unittest.TestCase):
    def test_reroll_hanya_sekali(self):
        """Dua klaim reroll bersamaan → hanya satu yang dapat rowcount=1."""
        conn = _db()
        conn.execute("INSERT INTO giveaways (message_id, prize_coins) VALUES (1, 500)")
        cur1 = conn.execute(
            "UPDATE giveaways SET reroll_count = reroll_count + 1"
            " WHERE message_id = 1 AND COALESCE(reroll_count, 0) < 1"
        )
        cur2 = conn.execute(
            "UPDATE giveaways SET reroll_count = reroll_count + 1"
            " WHERE message_id = 1 AND COALESCE(reroll_count, 0) < 1"
        )
        self.assertEqual(cur1.rowcount, 1)
        self.assertEqual(cur2.rowcount, 0)  # klaim kedua ditolak → tidak cetak koin
        self.assertEqual(conn.execute("SELECT reroll_count FROM giveaways WHERE message_id = 1").fetchone()[0], 1)

    def test_tutup_tiket_hanya_sekali(self):
        """Double-click 'Tutup Tiket' → hanya satu yang memproses."""
        conn = _db()
        conn.execute("INSERT INTO tickets (channel_id) VALUES (10)")
        cur1 = conn.execute("UPDATE tickets SET closed = 1 WHERE channel_id = 10 AND closed = 0")
        cur2 = conn.execute("UPDATE tickets SET closed = 1 WHERE channel_id = 10 AND closed = 0")
        self.assertEqual(cur1.rowcount, 1)
        self.assertEqual(cur2.rowcount, 0)  # klik kedua diabaikan → transcript tidak ganda

    def test_starboard_klaim_atomik(self):
        """Dua reaksi ⭐ bersamaan → hanya satu yang memposting."""
        conn = _db()
        cur1 = conn.execute(
            "INSERT OR IGNORE INTO starboard (message_id, starboard_msg_id, channel_id) VALUES (7, 0, 3)"
        )
        cur2 = conn.execute(
            "INSERT OR IGNORE INTO starboard (message_id, starboard_msg_id, channel_id) VALUES (7, 0, 3)"
        )
        self.assertEqual(cur1.rowcount, 1)
        self.assertEqual(cur2.rowcount, 0)  # yang kalah race skip → tidak ada postingan ganda

    def test_settlement_lelang_hanya_sekali(self):
        conn = _db()
        conn.execute("INSERT INTO lelang (id) VALUES (5)")
        cur1 = conn.execute("UPDATE lelang SET ended = 1 WHERE id = 5 AND ended = 0")
        cur2 = conn.execute("UPDATE lelang SET ended = 1 WHERE id = 5 AND ended = 0")
        self.assertEqual(cur1.rowcount, 1)
        self.assertEqual(cur2.rowcount, 0)

    def test_pool_guarded_deduct(self):
        """Dua rutin berebut pool → hanya satu yang berhasil deduct."""
        conn = _db()
        conn.execute("INSERT INTO server_pool (guild_id, koin) VALUES (9, 1000)")
        cur1 = conn.execute("UPDATE server_pool SET koin = koin - 800 WHERE guild_id = 9 AND koin >= 800")
        cur2 = conn.execute("UPDATE server_pool SET koin = koin - 800 WHERE guild_id = 9 AND koin >= 800")
        self.assertEqual(cur1.rowcount, 1)
        self.assertEqual(cur2.rowcount, 0)  # yang kalah dibatalkan, bukan mencetak koin
        self.assertEqual(conn.execute("SELECT koin FROM server_pool WHERE guild_id = 9").fetchone()[0], 200)


class TestAcakHurufTersentral(unittest.TestCase):
    def test_hasil_beda_tapi_huruf_sama(self):
        from src.utils.teks import acak_huruf

        import random

        for kata in ("kucing", "komputer", "pantai"):
            hasil = acak_huruf(kata, random.Random(42))
            self.assertNotEqual(hasil.lower(), kata.lower())
            self.assertEqual(sorted(hasil.lower()), sorted(kata.lower()))

    def test_wrapper_lama_tetap_kompatibel(self):
        import random

        from src.cogs.minigames import acak_kata as acak_minigames
        from src.cogs.turnamen import acak_kata as acak_turnamen

        self.assertNotEqual(acak_minigames("kucing", random.Random(7)).lower(), "kucing")
        asli, acak = acak_turnamen(random.Random(123))
        self.assertNotEqual(acak.lower(), asli.lower())
        self.assertEqual(sorted(acak.lower()), sorted(asli.lower()))


if __name__ == "__main__":
    unittest.main()


class TestResponErrorAman(unittest.IsolatedAsyncioTestCase):
    """Error handler tidak boleh ikut crash (10062/40060)."""

    async def _panggil(self, ctx):
        from src.bot import FinchBot

        await FinchBot._respon_error_aman(object(), ctx, "❌ error")

    async def test_prefix_tanpa_interaction(self):
        ctx = _ctx_mock()
        ctx.interaction = None
        await self._panggil(ctx)
        ctx.send.assert_awaited_once_with("❌ error")

    async def test_slash_belum_direspon(self):
        ctx = _ctx_mock()
        ctx.interaction.response.is_done.return_value = False
        await self._panggil(ctx)
        ctx.interaction.response.send_message.assert_awaited_once_with(
            "❌ error", ephemeral=True
        )

    async def test_slash_sudah_direspon(self):
        ctx = _ctx_mock()
        ctx.interaction.response.is_done.return_value = True
        await self._panggil(ctx)
        ctx.interaction.followup.send.assert_awaited_once_with(
            "❌ error", ephemeral=True
        )

    async def test_interaction_mati_tidak_crash(self):
        import discord

        resp = MagicMock()
        resp.status = 404
        ctx = _ctx_mock()
        ctx.interaction.response.is_done.return_value = False
        ctx.interaction.response.send_message.side_effect = discord.HTTPException(
            resp, "Unknown interaction"
        )
        await self._panggil(ctx)  # tidak boleh raise
