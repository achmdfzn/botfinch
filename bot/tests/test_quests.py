"""Tes quest harian. Jalanin:  python -m pytest tests/ -q"""
import datetime
import sqlite3
import unittest

from src.utils import quests as q


def _conn_baru():
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE quest_progress (
            user_id INTEGER NOT NULL,
            guild_id INTEGER NOT NULL,
            tanggal TEXT NOT NULL,
            pesan INTEGER NOT NULL DEFAULT 0,
            voice_menit INTEGER NOT NULL DEFAULT 0,
            daily_ok INTEGER NOT NULL DEFAULT 0,
            klaim_pesan INTEGER NOT NULL DEFAULT 0,
            klaim_voice INTEGER NOT NULL DEFAULT 0,
            klaim_daily INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, guild_id, tanggal)
        )
    """)
    return conn


class TestQuest(unittest.TestCase):
    def setUp(self):
        self.conn = _conn_baru()

    def tearDown(self):
        self.conn.close()

    def test_status_awal(self):
        status = q.status_quest(self.conn, 1, 100)
        self.assertEqual(len(status), 3)
        for s in status:
            self.assertEqual(s["progress"], 0)
            self.assertFalse(s["selesai"])
            self.assertFalse(s["diklaim"])

    def test_pesan_dan_klaim(self):
        for _ in range(25):
            q.tambah_pesan(self.conn, 1, 100)
        status = q.status_quest(self.conn, 1, 100)
        pesan = [s for s in status if s["id"] == "pesan"][0]
        self.assertTrue(pesan["selesai"])
        self.assertFalse(pesan["diklaim"])
        total, nama = q.klaim_quest(self.conn, 1, 100)
        self.assertEqual(total, pesan["hadiah"])
        self.assertEqual(len(nama), 1)
        # klaim kedua kali -> 0
        total2, _ = q.klaim_quest(self.conn, 1, 100)
        self.assertEqual(total2, 0)

    def test_voice_dan_daily(self):
        q.tambah_voice(self.conn, 1, 100, 30)
        q.tandai_daily(self.conn, 1, 100)
        total, nama = q.klaim_quest(self.conn, 1, 100)
        status = {s["id"]: s for s in q.status_quest(self.conn, 1, 100)}
        self.assertEqual(total, status["voice"]["hadiah"] + status["daily"]["hadiah"])
        self.assertEqual(len(nama), 2)

    def test_belum_selesai_tidak_terklaim(self):
        q.tambah_pesan(self.conn, 1, 100)
        total, nama = q.klaim_quest(self.conn, 1, 100)
        self.assertEqual(total, 0)
        self.assertEqual(nama, [])


if __name__ == "__main__":
    unittest.main()
