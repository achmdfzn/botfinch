"""Tes Tahap 12f (utilitas): dashboard, backup, grafik, embed builder, event rutin, vote saran.

Jalanin: python -m pytest tests/test_tahap12f.py -q
"""
import datetime
import sqlite3
import unittest

from src.cogs.utilitas import (
    _bucket_distribusi,
    _fmt_interval,
    _jatuh_tempo,
    _render_dashboard_html,
)
from src.utils.filters import parse_durasi


class TestFmtInterval(unittest.TestCase):
    def test_hari(self):
        self.assertEqual(_fmt_interval(604800), "7 hari")
        self.assertEqual(_fmt_interval(86400), "1 hari")

    def test_jam_menit(self):
        self.assertEqual(_fmt_interval(3600), "1 jam")
        self.assertEqual(_fmt_interval(7200), "2 jam")
        self.assertEqual(_fmt_interval(1800), "30 menit")

    def test_detik(self):
        self.assertEqual(_fmt_interval(90), "90 detik")


class TestBucketDistribusi(unittest.TestCase):
    def test_sepuluh_baris(self):
        buckets = _bucket_distribusi([1, 3, 7, 12, 50])
        self.assertEqual(len(buckets), 10)
        self.assertEqual(buckets[0], ("Lv 1–5", 2))
        self.assertEqual(buckets[1], ("Lv 6–10", 1))
        self.assertEqual(buckets[2], ("Lv 11–15", 1))
        self.assertEqual(buckets[9], ("Lv 46–50", 1))

    def test_kosong(self):
        buckets = _bucket_distribusi([])
        self.assertEqual(len(buckets), 10)
        self.assertTrue(all(c == 0 for _, c in buckets))


class TestJatuhTempo(unittest.TestCase):
    def setUp(self):
        self.now = datetime.datetime(2026, 10, 8, 12, 0, tzinfo=datetime.timezone.utc)

    def test_belum_pernah(self):
        self.assertTrue(_jatuh_tempo(None, 3600, self.now))

    def test_sudah_waktunya(self):
        lama = (self.now - datetime.timedelta(hours=2)).isoformat()
        self.assertTrue(_jatuh_tempo(lama, 3600, self.now))

    def test_belum_waktunya(self):
        baru = (self.now - datetime.timedelta(minutes=30)).isoformat()
        self.assertFalse(_jatuh_tempo(baru, 3600, self.now))

    def test_format_rusak(self):
        self.assertTrue(_jatuh_tempo("bukan-tanggal", 3600, self.now))


class TestParseDurasiEventRutin(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(parse_durasi("7d"), 604800)
        self.assertEqual(parse_durasi("1h"), 3600)
        self.assertEqual(parse_durasi("1d"), 86400)

    def test_invalid(self):
        self.assertIsNone(parse_durasi("xyz"))
        self.assertIsNone(parse_durasi(""))

    def test_minimal_1_jam(self):
        self.assertLess(parse_durasi("30m"), 3600)  # harus ditolak command


class TestDashboardHtml(unittest.TestCase):
    def test_render(self):
        html = _render_dashboard_html(
            "Finch",
            [("Server A", 100), ("Server B", 50)],
            [(1, 10, 500), (2, 5, 100)],
            [(1, 9999)],
        )
        self.assertIn("Finch", html)
        self.assertIn("Server A", html)
        self.assertIn("150", html)  # total member
        self.assertIn("/api/stats", html)
        self.assertIn("9,999", html)

    def test_escape_html(self):
        html = _render_dashboard_html(
            "<script>alert(1)</script>", [("<b>nakal</b>", 1)], [], []
        )
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)


class TestVoteSaranSql(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute(
            "CREATE TABLE suggestions (message_id INTEGER PRIMARY KEY, guild_id INTEGER,"
            " author_id INTEGER, text TEXT, status TEXT)"
        )
        self.conn.execute(
            "CREATE TABLE saran_vote (message_id INTEGER NOT NULL, user_id INTEGER NOT NULL,"
            " vote INTEGER NOT NULL, PRIMARY KEY (message_id, user_id))"
        )
        self.conn.execute(
            "INSERT INTO suggestions VALUES (100, 10, 1, 'Tambah channel mabar', 'Menunggu')"
        )
        self.conn.execute(
            "INSERT INTO suggestions VALUES (101, 10, 2, 'Event mingguan', 'Menunggu')"
        )

    def vote(self, mid, uid, nilai):
        self.conn.execute(
            "INSERT INTO saran_vote (message_id, user_id, vote) VALUES (?, ?, ?) "
            "ON CONFLICT(message_id, user_id) DO UPDATE SET vote = excluded.vote",
            (mid, uid, nilai),
        )
        self.conn.commit()

    def test_upsert_ganti_vote(self):
        self.vote(100, 5, 1)
        self.vote(100, 5, -1)  # user berubah pikiran
        row = self.conn.execute(
            "SELECT vote FROM saran_vote WHERE message_id = 100 AND user_id = 5"
        ).fetchone()
        self.assertEqual(row[0], -1)
        n = self.conn.execute(
            "SELECT COUNT(*) FROM saran_vote WHERE message_id = 100"
        ).fetchone()[0]
        self.assertEqual(n, 1, "satu user = satu vote")

    def test_skor_top(self):
        self.vote(100, 5, 1)
        self.vote(100, 6, 1)
        self.vote(100, 7, -1)
        self.vote(101, 5, 1)
        rows = self.conn.execute(
            "SELECT s.message_id, COALESCE(SUM(v.vote), 0) AS skor"
            " FROM suggestions s LEFT JOIN saran_vote v ON v.message_id = s.message_id"
            " WHERE s.guild_id = 10 GROUP BY s.message_id"
            " ORDER BY skor DESC LIMIT 5"
        ).fetchall()
        self.assertEqual(len(rows), 2)
        self.assertEqual({r[0] for r in rows}, {100, 101})
        self.assertTrue(all(skor == 1 for _, skor in rows))  # seri 1-1


class TestEventRutinSql(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute(
            "CREATE TABLE event_rutin (id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " guild_id INTEGER NOT NULL, channel_id INTEGER NOT NULL, nama TEXT NOT NULL,"
            " deskripsi TEXT NOT NULL DEFAULT '', interval_detik INTEGER NOT NULL,"
            " terakhir TEXT)"
        )

    def test_insert_dan_hapus(self):
        cur = self.conn.execute(
            "INSERT INTO event_rutin (guild_id, channel_id, nama, deskripsi, interval_detik)"
            " VALUES (?, ?, ?, ?, ?)",
            (10, 20, "Mabar Jumat", "", 604800),
        )
        self.conn.commit()
        rid = cur.lastrowid
        n = self.conn.execute("SELECT COUNT(*) FROM event_rutin").fetchone()[0]
        self.assertEqual(n, 1)
        cur = self.conn.execute(
            "DELETE FROM event_rutin WHERE id = ? AND guild_id = ?", (rid, 10)
        )
        self.conn.commit()
        self.assertEqual(cur.rowcount, 1)

    def test_hapus_id_salah(self):
        cur = self.conn.execute(
            "DELETE FROM event_rutin WHERE id = ? AND guild_id = ?", (999, 10)
        )
        self.assertEqual(cur.rowcount, 0)


if __name__ == "__main__":
    unittest.main()
