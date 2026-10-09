"""Tes Tahap 12d (moderasi_plus). Jalanin: python -m pytest tests/test_tahap12d.py -q"""
import datetime
import sqlite3
import unittest
from collections import deque

import discord

from src.cogs.moderasi_plus import (
    JOIN_AMBANG,
    JOIN_WINDOW,
    KATEGORI_TIKET,
    LOCKDOWN_COOLDOWN,
)
from src.cogs.tickets import KATEGORI_TIKET as TIKET_KAT
from src.cogs.tickets import TicketKategoriView
from src.utils.waktu import parse_iso as _parse_iso


def db_baru() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE tickets (channel_id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL,"
        " owner_id INTEGER NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP,"
        " closed INTEGER DEFAULT 0, kategori TEXT DEFAULT 'umum', balas_terakhir TEXT)"
    )
    conn.execute(
        "CREATE TABLE warnings (user_id INTEGER NOT NULL, guild_id INTEGER NOT NULL,"
        " count INTEGER DEFAULT 0, updated_at TEXT DEFAULT CURRENT_TIMESTAMP,"
        " PRIMARY KEY (user_id, guild_id))"
    )
    conn.execute(
        "CREATE TABLE autoresponder (guild_id INTEGER NOT NULL, trigger TEXT NOT NULL,"
        " respons TEXT NOT NULL, PRIMARY KEY (guild_id, trigger))"
    )
    conn.execute(
        "CREATE TABLE lockdown_state (channel_id INTEGER PRIMARY KEY,"
        " guild_id INTEGER NOT NULL, send_messages INTEGER)"
    )
    return conn


class TestParseIso(unittest.TestCase):
    def test_none(self):
        self.assertIsNone(_parse_iso(None))

    def test_valid(self):
        dt = _parse_iso("2026-10-08T05:00:00+00:00")
        self.assertIsNotNone(dt)
        self.assertIsNotNone(dt.tzinfo)

    def test_naive_jadi_utc(self):
        dt = _parse_iso("2026-10-08T05:00:00")
        self.assertEqual(dt.tzinfo, datetime.timezone.utc)

    def test_invalid(self):
        self.assertIsNone(_parse_iso("bukan-tanggal"))


class TestKategori(unittest.TestCase):
    def test_kategori_sama(self):
        self.assertEqual(KATEGORI_TIKET, TIKET_KAT)
        self.assertEqual(KATEGORI_TIKET, ["Umum", "Bantuan", "Report", "Saran"])

    def test_view_punya_select(self):
        view = TicketKategoriView()
        selects = [c for c in view.children if isinstance(c, discord.ui.Select)]
        self.assertEqual(len(selects), 1)
        self.assertEqual(len(selects[0].options), 4)


class TestAutoLockdownLogika(unittest.TestCase):
    def _simulasi(self, join_offsets):
        """Simulasi join: offsets = detik lalu tiap join terjadi."""
        now = 1_000_000.0
        dq: deque = deque(maxlen=50)
        for off in sorted(join_offsets, reverse=True):  # tertua dulu (kronologis)
            dq.append(now - off)
        while dq and now - dq[0] > JOIN_WINDOW:
            dq.popleft()
        return len(dq) >= JOIN_AMBANG

    def test_trigger_8_join(self):
        self.assertTrue(self._simulasi([5, 10, 15, 20, 25, 30, 40, 50]))

    def test_tidak_trigger_7_join(self):
        self.assertFalse(self._simulasi([5, 10, 15, 20, 25, 30, 40]))

    def test_join_lama_kedaluwarsa(self):
        # 8 join tapi 5 di antaranya >60 detik lalu -> tidak trigger
        self.assertFalse(self._simulasi([5, 10, 15, 70, 80, 90, 100, 110]))

    def test_cooldown_30_menit(self):
        self.assertEqual(LOCKDOWN_COOLDOWN, 1800)


class TestBalasTerakhir(unittest.TestCase):
    def test_update_balas_terakhir(self):
        conn = db_baru()
        conn.execute("INSERT INTO tickets (channel_id, guild_id, owner_id) VALUES (1, 10, 99)")
        conn.commit()
        iso = "2026-10-08T05:00:00+00:00"
        row = conn.execute(
            "SELECT 1 FROM tickets WHERE channel_id = ? AND closed = 0", (1,)
        ).fetchone()
        self.assertIsNotNone(row)
        conn.execute(
            "UPDATE tickets SET balas_terakhir = ? WHERE channel_id = ?", (iso, 1)
        )
        conn.commit()
        got = conn.execute("SELECT balas_terakhir FROM tickets WHERE channel_id = 1").fetchone()[0]
        self.assertEqual(got, iso)
        conn.close()

    def test_sla_coalesce(self):
        conn = db_baru()
        conn.execute("INSERT INTO tickets (channel_id, guild_id, owner_id) VALUES (2, 10, 99)")
        conn.commit()
        row = conn.execute(
            "SELECT COALESCE(balas_terakhir, created_at) FROM tickets WHERE channel_id = 2"
        ).fetchone()
        self.assertIsNotNone(row[0])  # fallback ke created_at
        conn.close()


class TestWarnList(unittest.TestCase):
    def test_top10_urut(self):
        conn = db_baru()
        conn.execute("INSERT INTO warnings VALUES (1, 10, 5, '2026-10-01')")
        conn.execute("INSERT INTO warnings VALUES (2, 10, 2, '2026-10-02')")
        conn.execute("INSERT INTO warnings VALUES (3, 10, 0, '2026-10-03')")
        conn.commit()
        rows = conn.execute(
            "SELECT user_id, count FROM warnings WHERE guild_id = ? AND count > 0"
            " ORDER BY count DESC LIMIT 10",
            (10,),
        ).fetchall()
        self.assertEqual([r[0] for r in rows], [1, 2])
        conn.close()


class TestFaq(unittest.TestCase):
    def test_like_ketemu(self):
        conn = db_baru()
        conn.execute(
            "INSERT INTO autoresponder VALUES (10, 'verifikasi', 'Klik tombol verifikasi')"
        )
        conn.commit()
        rows = conn.execute(
            "SELECT trigger FROM autoresponder WHERE guild_id = ? AND trigger LIKE ?",
            (10, "%verif%"),
        ).fetchall()
        self.assertEqual(len(rows), 1)
        rows = conn.execute(
            "SELECT trigger FROM autoresponder WHERE guild_id = ? AND trigger LIKE ?",
            (10, "%tidakada%"),
        ).fetchall()
        self.assertEqual(rows, [])
        conn.close()


class TestLockdownSnapshot(unittest.TestCase):
    def test_insert_or_ignore_format(self):
        conn = db_baru()
        for ch_id, val in ((5, None), (6, 0), (7, 1)):
            conn.execute(
                "INSERT OR IGNORE INTO lockdown_state (channel_id, guild_id, send_messages)"
                " VALUES (?, ?, ?)",
                (ch_id, 10, val),
            )
        conn.commit()
        # INSERT OR IGNORE: tidak menimpa snapshot pertama
        conn.execute(
            "INSERT OR IGNORE INTO lockdown_state (channel_id, guild_id, send_messages)"
            " VALUES (?, ?, ?)",
            (6, 10, 1),
        )
        conn.commit()
        got = dict(conn.execute("SELECT channel_id, send_messages FROM lockdown_state").fetchall())
        self.assertEqual(got, {5: None, 6: 0, 7: 1})
        conn.close()


if __name__ == "__main__":
    unittest.main()
