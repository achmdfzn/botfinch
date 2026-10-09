"""Test Tahap 8: xp helper, voice menit, youtube RSS parse."""
import unittest
import sqlite3

from src.utils.xp import tambah_xp, hitung_menit
from src.cogs.youtube import parse_rss


class TestTambahXp(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("CREATE TABLE users (user_id INTEGER, guild_id INTEGER, xp INTEGER, level INTEGER, PRIMARY KEY (user_id, guild_id))")

    def tearDown(self):
        self.conn.close()

    def test_user_baru(self):
        lvl, naik = tambah_xp(self.conn, 1, 10, 15)
        self.assertEqual(lvl, 1)
        self.assertFalse(naik)

    def test_level_up(self):
        lvl, naik = tambah_xp(self.conn, 1, 10, 150)
        self.assertEqual(lvl, 2)
        self.assertTrue(naik)

    def test_multi_level(self):
        lvl, naik = tambah_xp(self.conn, 1, 10, 500)
        self.assertTrue(naik)
        self.assertGreaterEqual(lvl, 2)


class TestHitungMenit(unittest.TestCase):
    def test_kurang_semenit(self):
        self.assertEqual(hitung_menit(59), 0)

    def test_pas(self):
        self.assertEqual(hitung_menit(180), 3)

    def test_floor(self):
        self.assertEqual(hitung_menit(199), 3)


class TestParseRss(unittest.TestCase):
    def test_parse(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:yt="http://www.youtube.com/xml/schemas/2015">
<entry><yt:videoId>abc123</yt:videoId><title>Judul Video</title><published>2024-01-01T00:00:00+00:00</published></entry>
<entry><yt:videoId>def456</yt:videoId><title>Kedua</title><published>2024-01-02T00:00:00+00:00</published></entry>
</feed>"""
        out = parse_rss(xml)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["videoId"], "abc123")
        self.assertEqual(out[1]["title"], "Kedua")

    def test_invalid(self):
        self.assertEqual(parse_rss("bukan xml"), [])


if __name__ == "__main__":
    unittest.main()
