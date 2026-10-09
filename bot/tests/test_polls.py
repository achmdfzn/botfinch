"""Tes logika polling (pure function + hitung suara). Jalanin:  python -m pytest tests/ -q"""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from src import store
from src.cogs.polls import hitung_suara, parse_opsi


class TestParseOpsi(unittest.TestCase):
    def test_dasar(self):
        self.assertEqual(parse_opsi("19.00, 20.00,21.00"), ["19.00", "20.00", "21.00"])

    def test_kosong_dibuang(self):
        self.assertEqual(parse_opsi("a,, b ,"), ["a", "b"])

    def test_kosong(self):
        self.assertEqual(parse_opsi(""), [])
        self.assertEqual(parse_opsi(" , , "), [])


class TestHitungSuara(unittest.TestCase):
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

    def _vote(self, mid, uid, idx):
        self.conn.execute(
            "INSERT INTO poll_votes (message_id, user_id, option_idx) VALUES (?, ?, ?) "
            "ON CONFLICT(message_id, user_id) DO UPDATE SET option_idx=excluded.option_idx",
            (mid, uid, idx),
        )
        self.conn.commit()

    def test_hitung_dasar(self):
        self._vote(1, 10, 0)
        self._vote(1, 11, 0)
        self._vote(1, 12, 2)
        self.assertEqual(hitung_suara(self.conn, 1, 3), [2, 0, 1])

    def test_ganti_pilihan(self):
        self._vote(1, 10, 0)
        self._vote(1, 10, 1)  # pindah pilihan
        self.assertEqual(hitung_suara(self.conn, 1, 2), [0, 1])

    def test_belum_ada_suara(self):
        self.assertEqual(hitung_suara(self.conn, 99, 3), [0, 0, 0])


if __name__ == "__main__":
    unittest.main()
