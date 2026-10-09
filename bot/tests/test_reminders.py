"""Tes query pengingat. Jalanin:  python -m pytest tests/ -q"""
import datetime
import sqlite3
import tempfile
import unittest
from pathlib import Path

from src import store
from src.cogs.reminders import ambil_jatuh_tempo


class TestAmbilJatuhTempo(unittest.TestCase):
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

    def _tambah(self, pesan, remind_at, done=0):
        self.conn.execute(
            "INSERT INTO reminders (user_id, guild_id, channel_id, message, remind_at, done) "
            "VALUES (1, 1, 1, ?, ?, ?)",
            (pesan, remind_at, done),
        )
        self.conn.commit()

    def test_hanya_yang_jatuh_tempo_dan_belum_done(self):
        lampau = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=1)).isoformat()
        depan = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)).isoformat()
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self._tambah("sudah waktunya", lampau)
        self._tambah("belum waktunya", depan)
        self._tambah("sudah dikirim", lampau, done=1)

        rows = ambil_jatuh_tempo(self.conn, now)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][3], "sudah waktunya")

    def test_kosong(self):
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self.assertEqual(ambil_jatuh_tempo(self.conn, now), [])


if __name__ == "__main__":
    unittest.main()
