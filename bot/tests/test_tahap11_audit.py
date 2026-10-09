"""Regression test untuk temuan audit Tahap 11 (S1-S7, R1-R8).

Fokus pada logika DB yang diperbaiki — query & urutan operasi yang sama
dengan kode cog, dijalankan di SQLite in-memory.
"""
import sqlite3
import unittest

from src.utils import economy as eko


def db_baru() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE users (user_id INTEGER, guild_id INTEGER, level INTEGER, xp INTEGER,"
        " PRIMARY KEY (user_id, guild_id))"
    )
    conn.execute(
        "CREATE TABLE economy (user_id INTEGER NOT NULL, guild_id INTEGER NOT NULL,"
        " balance INTEGER NOT NULL DEFAULT 0, bank INTEGER NOT NULL DEFAULT 0,"
        " streak_daily INTEGER NOT NULL DEFAULT 0, last_streak_date TEXT,"
        " total_earned INTEGER NOT NULL DEFAULT 0, last_daily TEXT, last_work TEXT,"
        " PRIMARY KEY (user_id, guild_id))"
    )
    conn.execute("CREATE TABLE starboard_rewarded (message_id INTEGER PRIMARY KEY)")
    conn.execute(
        "CREATE TABLE lockdown_state (channel_id INTEGER PRIMARY KEY,"
        " guild_id INTEGER NOT NULL, send_messages INTEGER)"
    )
    conn.execute(
        "CREATE TABLE invites_log (user_id INTEGER NOT NULL, guild_id INTEGER NOT NULL,"
        " inviter_id INTEGER, code TEXT, PRIMARY KEY (user_id, guild_id))"
    )
    conn.execute(
        "CREATE TABLE tiket_rating_pending (owner_id INTEGER PRIMARY KEY,"
        " tiket_id INTEGER NOT NULL, guild_id INTEGER NOT NULL)"
    )
    conn.execute("CREATE TABLE tiket_rating (tiket_id INTEGER PRIMARY KEY, guild_id INTEGER,"
                 " user_id INTEGER, rating INTEGER)")
    return conn


class TestAuditFixes(unittest.TestCase):
    # S3: pemenang season diurut level dulu, bukan sisa xp
    def test_season_order_level_dulu(self):
        conn = db_baru()
        conn.execute("INSERT INTO users VALUES (1, 10, 40, 5)")   # level 40, sisa xp 5
        conn.execute("INSERT INTO users VALUES (2, 10, 2, 200)")   # level 2, sisa xp 200
        top = conn.execute(
            "SELECT user_id FROM users WHERE guild_id = ?"
            " ORDER BY level DESC, xp DESC LIMIT 3",
            (10,),
        ).fetchall()
        self.assertEqual(top[0][0], 1, "level 40 harus menang walau sisa xp kecil")
        conn.close()

    # S4: payout season atomik — UPSERT dalam satu transaksi
    def test_season_payout_upsert(self):
        conn = db_baru()
        for uid, hadiah in ((1, 1000), (2, 500)):
            conn.execute(
                "INSERT INTO economy (user_id, guild_id, balance, total_earned)"
                " VALUES (?, ?, ?, ?)"
                " ON CONFLICT(user_id, guild_id) DO UPDATE SET"
                " balance = balance + ?, total_earned = total_earned + ?",
                (uid, 10, hadiah, hadiah, hadiah, hadiah),
            )
        conn.commit()
        bal = conn.execute(
            "SELECT balance, total_earned FROM economy WHERE user_id = 1 AND guild_id = 10"
        ).fetchone()
        self.assertEqual(bal, (1000, 1000))
        conn.close()

    # S5: reward starboard hanya sekali per pesan
    def test_starboard_reward_sekali(self):
        conn = db_baru()
        reward = 0
        for _ in range(3):  # simulasi lepas/pasang ⭐ 3x
            sudah = conn.execute(
                "SELECT 1 FROM starboard_rewarded WHERE message_id = ?", (99,)
            ).fetchone()
            if not sudah:
                conn.execute("INSERT INTO starboard_rewarded (message_id) VALUES (?)", (99,))
                conn.commit()
                reward += 50
        self.assertEqual(reward, 50, "reward harus sekali walau diposting 3x")
        conn.close()

    # S6: escrow lelang — bid memotong, outbid mengembalikan
    def test_lelang_escrow(self):
        conn = db_baru()
        eko.tambah_koin(conn, 10, 1, 1000)  # bidder A
        eko.tambah_koin(conn, 10, 2, 1000)  # bidder B
        # A bid 300
        self.assertIsNotNone(eko.kurang_koin(conn, 10, 1, 300))
        # B outbid 400 → A dikembalikan 300, B dipotong 400
        self.assertIsNotNone(eko.kurang_koin(conn, 10, 2, 400))
        eko.tambah_koin(conn, 10, 1, 300)
        a = eko.get_akun(conn, 10, 1)["balance"]
        b = eko.get_akun(conn, 10, 2)["balance"]
        # akun baru dapat bonus awal 100 → A: 1100, B: 1100
        self.assertEqual(a, 1100, "A harus kembali utuh setelah di-outbid")
        self.assertEqual(b, 700, "B terpotong escrow 400")
        conn.close()

    # S7: lockdown snapshot & restore
    def test_lockdown_snapshot_restore(self):
        conn = db_baru()
        # channel 5 memang read-only (send_messages=False) sebelum lockdown
        conn.execute(
            "INSERT OR IGNORE INTO lockdown_state (channel_id, guild_id, send_messages)"
            " VALUES (?, ?, ?)",
            (5, 10, 0),
        )
        conn.commit()
        val = conn.execute(
            "SELECT send_messages FROM lockdown_state WHERE channel_id = ?", (5,)
        ).fetchone()[0]
        self.assertEqual(val, 0)
        restore = None if val is None else bool(val)
        self.assertIs(restore, False, "channel read-only harus tetap read-only setelah unlock")
        conn.execute("DELETE FROM lockdown_state WHERE guild_id = ?", (10,))
        conn.commit()
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM lockdown_state").fetchone()[0], 0)
        conn.close()

    # R7: rejoin tidak kasih reward invite lagi
    def test_invite_rejoin_tanpa_reward(self):
        conn = db_baru()
        reward_diberikan = 0
        for _ in range(2):  # join, keluar, join lagi
            rejoin = conn.execute(
                "SELECT 1 FROM invites_log WHERE user_id = ? AND guild_id = ?",
                (7, 10),
            ).fetchone() is not None
            conn.execute(
                "INSERT OR REPLACE INTO invites_log (user_id, guild_id, inviter_id, code)"
                " VALUES (?, ?, ?, ?)",
                (7, 10, 8, "abc"),
            )
            conn.commit()
            if not rejoin:
                reward_diberikan += 200
        self.assertEqual(reward_diberikan, 200, "reward invite hanya untuk join pertama")
        conn.close()

    # R6: rating pending → rating tersimpan sekali, pending terhapus
    def test_rating_pending_flow(self):
        conn = db_baru()
        conn.execute(
            "INSERT OR REPLACE INTO tiket_rating_pending (owner_id, tiket_id, guild_id)"
            " VALUES (?, ?, ?)",
            (42, 777, 10),
        )
        conn.commit()
        pending = conn.execute(
            "SELECT tiket_id, guild_id FROM tiket_rating_pending WHERE owner_id = ?", (42,)
        ).fetchone()
        self.assertEqual(pending, (777, 10))
        conn.execute(
            "INSERT INTO tiket_rating (tiket_id, guild_id, user_id, rating) VALUES (?, ?, ?, ?)"
            " ON CONFLICT(tiket_id) DO UPDATE SET rating = excluded.rating",
            (pending[0], pending[1], 42, 5),
        )
        conn.execute("DELETE FROM tiket_rating_pending WHERE owner_id = ?", (42,))
        conn.commit()
        self.assertEqual(
            conn.execute("SELECT rating FROM tiket_rating WHERE tiket_id = 777").fetchone()[0], 5
        )
        self.assertIsNone(
            conn.execute("SELECT 1 FROM tiket_rating_pending WHERE owner_id = 42").fetchone()
        )
        conn.close()


if __name__ == "__main__":
    unittest.main()
