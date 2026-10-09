"""Tes skema & migrasi SQLite (src/store.py). Jalanin:  python -m pytest tests/ -q"""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from src import store


class TestStoreMigration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._old = store.DB_PATH
        store.DB_PATH = Path(self.tmp.name) / "finch.db"

    def tearDown(self):
        store.DB_PATH = self._old
        self.tmp.cleanup()

    def _cols(self):
        conn = sqlite3.connect(str(store.DB_PATH))
        try:
            return [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
        finally:
            conn.close()

    def test_init_db_baru_punya_guild_id(self):
        store.init_db()
        self.assertIn("guild_id", self._cols())

    def test_migrasi_dari_skema_lama_data_tidak_hilang(self):
        # bikin DB gaya lama: users(user_id PK, xp, level) tanpa guild_id
        conn = sqlite3.connect(str(store.DB_PATH))
        conn.execute(
            "CREATE TABLE users (user_id INTEGER PRIMARY KEY, xp INTEGER DEFAULT 0, level INTEGER DEFAULT 1)"
        )
        conn.execute("INSERT INTO users (user_id, xp, level) VALUES (123, 50, 2)")
        conn.commit()
        conn.close()

        store.init_db()

        conn = sqlite3.connect(str(store.DB_PATH))
        try:
            row = conn.execute(
                "SELECT user_id, guild_id, xp, level FROM users"
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(row, (123, 0, 50, 2))

    def test_init_db_idempoten(self):
        # dipanggil 2x (mis. restart) tidak error & data tetap
        store.init_db()
        conn = sqlite3.connect(str(store.DB_PATH))
        conn.execute(
            "INSERT INTO users (user_id, guild_id, xp, level) VALUES (7, 42, 10, 1)"
        )
        conn.commit()
        conn.close()

        store.init_db()

        conn = sqlite3.connect(str(store.DB_PATH))
        try:
            row = conn.execute(
                "SELECT xp FROM users WHERE user_id = 7 AND guild_id = 42"
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(row, (10,))


if __name__ == "__main__":
    unittest.main()
