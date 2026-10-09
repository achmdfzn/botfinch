"""Tes logika AFK (pure function). Jalanin:  python -m pytest tests/ -q"""
import unittest

from src.cogs.afk import format_balas_afk


class TestFormatBalasAfk(unittest.TestCase):
    ISO = "2026-10-06T09:00:00+00:00"

    def test_dengan_alasan(self):
        hasil = format_balas_afk("Fauzan", "makan dulu", self.ISO)
        self.assertIn("💤", hasil)
        self.assertIn("Fauzan", hasil)
        self.assertIn("makan dulu", hasil)
        self.assertIn("<t:", hasil)  # timestamp Discord

    def test_tanpa_alasan(self):
        hasil = format_balas_afk("Fauzan", None, self.ISO)
        self.assertIn("AFK", hasil)
        self.assertNotIn("None", hasil)

    def test_iso_rusak_tidak_crash(self):
        hasil = format_balas_afk("Fauzan", "x", "bukan-tanggal")
        self.assertIn("tadi", hasil)


if __name__ == "__main__":
    unittest.main()
