"""Tes generator kartu rank & hitung peringkat. Jalanin:  python -m pytest tests/ -q"""
import io
import sqlite3
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from src import store
from src.cogs.leveling import hitung_rank
from src.utils.rankcard import W, H, make_rank_card


def _avatar_dummy() -> bytes:
    img = Image.new("RGB", (256, 256), (88, 101, 242))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestRankCard(unittest.TestCase):
    def test_kartu_valid_png_800x250(self):
        buf = make_rank_card(_avatar_dummy(), "Fauzan", 7, 320, 1050, 3)
        data = buf.getvalue()
        self.assertTrue(data.startswith(b"\x89PNG"))
        img = Image.open(io.BytesIO(data))
        self.assertEqual(img.size, (W, H))
        self.assertEqual((W, H), (800, 250))

    def test_tanpa_avatar_tidak_crash(self):
        buf = make_rank_card(None, "X", 1, 0, 150, 99)
        img = Image.open(io.BytesIO(buf.getvalue()))
        self.assertEqual(img.size, (800, 250))

    def test_nama_panjang_dipotong_tidak_crash(self):
        buf = make_rank_card(_avatar_dummy(), "A" * 100, 99, 99999, 100000, 1)
        self.assertTrue(buf.getvalue().startswith(b"\x89PNG"))

    def test_avatar_rusak_tidak_crash(self):
        buf = make_rank_card(b"bukan-gambar", "Test", 2, 10, 300, 5)
        self.assertTrue(buf.getvalue().startswith(b"\x89PNG"))


class TestHitungRank(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._old = store.DB_PATH
        store.DB_PATH = Path(self.tmp.name) / "finch.db"
        store.init_db()
        self.conn = sqlite3.connect(str(store.DB_PATH))

    def tearDown(self):
        self.conn.close()
        store.DB_PATH = self._old
        self.tmp.cleanup()

    def _isi(self, rows):
        # rows: (user_id, guild_id, level, xp)
        self.conn.executemany(
            "INSERT INTO users (user_id, guild_id, xp, level) VALUES (?, ?, ?, ?)",
            [(u, g, x, l) for u, g, l, x in rows],
        )
        self.conn.commit()

    def test_rank_1_untuk_tertinggi(self):
        self._isi([(1, 42, 5, 100), (2, 42, 3, 50), (3, 42, 5, 90)])
        self.assertEqual(hitung_rank(self.conn, 42, 5, 100), 1)
        self.assertEqual(hitung_rank(self.conn, 42, 5, 90), 2)
        self.assertEqual(hitung_rank(self.conn, 42, 3, 50), 3)

    def test_rank_per_server_terpisah(self):
        self._isi([(1, 42, 10, 0), (2, 99, 1, 0)])
        # user di server 99 level 1 tetap rank 1 di servernya sendiri
        self.assertEqual(hitung_rank(self.conn, 99, 1, 0), 1)
        self.assertEqual(hitung_rank(self.conn, 42, 10, 0), 1)

    def test_rank_user_baru_tanpa_data(self):
        self._isi([(1, 42, 2, 10)])
        self.assertEqual(hitung_rank(self.conn, 42, 1, 0), 2)


if __name__ == "__main__":
    unittest.main()
