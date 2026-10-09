"""Tes logika giveaway (pure function) + regression _akhiri. Jalanin:  python -m pytest tests/ -q"""
import asyncio
import random
import unittest
from unittest.mock import AsyncMock, MagicMock

import discord

from src.cogs.giveaway import Giveaway, parse_durasi, pilih_pemenang


class TestParseDurasi(unittest.TestCase):
    def test_detik_menit_jam_hari(self):
        self.assertEqual(parse_durasi("30s"), 30)
        self.assertEqual(parse_durasi("10m"), 600)
        self.assertEqual(parse_durasi("2h"), 7200)
        self.assertEqual(parse_durasi("1d"), 86400)

    def test_case_insensitive_dan_spasi(self):
        self.assertEqual(parse_durasi(" 5M "), 300)
        self.assertEqual(parse_durasi("1H"), 3600)

    def test_format_salah(self):
        self.assertIsNone(parse_durasi("10"))
        self.assertIsNone(parse_durasi("menit"))
        self.assertIsNone(parse_durasi("10x"))
        self.assertIsNone(parse_durasi(""))
        self.assertIsNone(parse_durasi("-5m"))


class TestPilihPemenang(unittest.TestCase):
    def test_deterministik_dengan_seed(self):
        rng = random.Random(42)
        hasil = pilih_pemenang([1, 2, 3, 4, 5], 2, rng=rng)
        self.assertEqual(len(hasil), 2)
        # seed sama -> hasil sama
        self.assertEqual(hasil, pilih_pemenang([1, 2, 3, 4, 5], 2, rng=random.Random(42)))

    def test_tidak_lebih_dari_peserta(self):
        self.assertEqual(len(pilih_pemenang([1, 2], 5, rng=random.Random(1))), 2)

    def test_kosong(self):
        self.assertEqual(pilih_pemenang([], 3), [])

    def test_tidak_ada_duplikat(self):
        hasil = pilih_pemenang(list(range(100)), 10, rng=random.Random(7))
        self.assertEqual(len(set(hasil)), 10)


class TestAkhiriSelaluMengumumkan(unittest.TestCase):
    """Regression: pengumuman akhir HARUS terkirim walau pesan asli hilang
    atau tidak ada peserta (bug: sebelumnya silent tanpa pengumuman)."""

    def _cog_dengan_db(self, tmpdir, entries):
        import src.store as store

        # DB terisolasi per tes
        orig_path = store.DB_PATH
        store.DB_PATH = type(orig_path)(f"{tmpdir}/t.db")
        store.init_db()
        with store.get_connection() as conn:
            conn.execute(
                "INSERT INTO giveaways (message_id, channel_id, guild_id, ends_at,"
                " winners_count, prize, host_id) VALUES (111, 222, 1,"
                " '2000-01-01T00:00:00+00:00', 1, 'Nitro', 999)"
            )
            for uid in entries:
                conn.execute(
                    "INSERT INTO giveaway_entries (message_id, user_id) VALUES (111, ?)",
                    (uid,),
                )
            conn.commit()
        bot = MagicMock()
        channel = AsyncMock()
        channel.id = 222
        channel.send = AsyncMock()
        bot.get_channel = MagicMock(return_value=channel)
        cog = Giveaway.__new__(Giveaway)
        cog.bot = bot
        return cog, channel, orig_path

    def _kembalikan_db(self, orig_path):
        import src.store as store

        store.DB_PATH = orig_path

    def test_umumkan_walau_pesan_asli_hilang(self):
        import tempfile

        tmp = tempfile.mkdtemp()
        cog, channel, orig = self._cog_dengan_db(tmp, [1001])
        # pesan asli sudah dihapus -> fetch_message NotFound
        channel.fetch_message = AsyncMock(
            side_effect=discord.NotFound(MagicMock(), MagicMock())
        )
        asyncio.run(cog._akhiri(111, 222, 1, 1, "Nitro"))
        self._kembalikan_db(orig)
        # pengumuman TETAP dikirim walau pesan asli hilang
        self.assertTrue(channel.send.called)
        isi = channel.send.call_args[0][0]
        self.assertIn("GIVEAWAY BERAKHIR", isi)
        self.assertIn("<@1001>", isi)

    def test_umumkan_walau_tidak_ada_peserta(self):
        import tempfile

        tmp = tempfile.mkdtemp()
        cog, channel, orig = self._cog_dengan_db(tmp, [])
        msg = AsyncMock()
        channel.fetch_message = AsyncMock(return_value=msg)
        asyncio.run(cog._akhiri(111, 222, 1, 1, "Nitro"))
        self._kembalikan_db(orig)
        # tetap ada pengumuman (tidak ada peserta) — sebelumnya: sunyi total
        self.assertTrue(channel.send.called)
        isi = channel.send.call_args[0][0]
        self.assertIn("GIVEAWAY BERAKHIR", isi)
        self.assertIn("Tidak ada peserta", isi)


if __name__ == "__main__":
    unittest.main()
