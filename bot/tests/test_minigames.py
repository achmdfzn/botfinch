"""Tes mini-games (logika murni). Jalanin:  python -m pytest tests/ -q"""
import random
import unittest

from src.cogs.minigames import (
    TEBAK_MAX,
    TRIVIA_SOAL,
    bayar_slot,
    lempar_koin,
    putar_slot,
    undi_tebak,
)
from src.cogs.counting import cek_hitungan


class TestSlot(unittest.TestCase):
    def test_tiga_sehati_bayar_5x(self):
        self.assertEqual(bayar_slot(["🍒", "🍒", "🍒"], 100), 500)

    def test_tiga_7_jackpot_10x(self):
        self.assertEqual(bayar_slot(["7️⃣", "7️⃣", "7️⃣"], 100), 1000)

    def test_tiga_diamond_8x(self):
        self.assertEqual(bayar_slot(["💎", "💎", "💎"], 100), 800)

    def test_dua_sehati_bayar_2x(self):
        self.assertEqual(bayar_slot(["🍒", "🍒", "🔔"], 100), 200)
        self.assertEqual(bayar_slot(["🍒", "🔔", "🔔"], 100), 200)
        self.assertEqual(bayar_slot(["🍒", "🔔", "🍒"], 100), 200)

    def test_zonk(self):
        self.assertEqual(bayar_slot(["🍒", "🔔", "⭐"], 100), 0)

    def test_putar_deterministik(self):
        a = putar_slot(random.Random(5))
        b = putar_slot(random.Random(5))
        self.assertEqual(a, b)
        self.assertEqual(len(a), 3)


class TestCoinflipTebak(unittest.TestCase):
    def test_lempar_valid(self):
        for _ in range(20):
            self.assertIn(lempar_koin(), ["kepala", "ekor"])

    def test_undi_tebak_range(self):
        for _ in range(50):
            n = undi_tebak()
            self.assertGreaterEqual(n, 1)
            self.assertLessEqual(n, TEBAK_MAX)


class TestTriviaBank(unittest.TestCase):
    def test_bank_valid(self):
        self.assertGreaterEqual(len(TRIVIA_SOAL), 10)
        for soal, opsi, kunci in TRIVIA_SOAL:
            self.assertEqual(len(opsi), 4, soal)
            self.assertGreaterEqual(kunci, 0)
            self.assertLess(kunci, 4, soal)


class TestCounting(unittest.TestCase):
    def test_valid(self):
        ok, _ = cek_hitungan("5", 4, 100, 200)
        self.assertTrue(ok)

    def test_bukan_angka(self):
        ok, _ = cek_hitungan("halo", 4, 100, 200)
        self.assertFalse(ok)

    def test_angka_salah(self):
        ok, err = cek_hitungan("7", 4, 100, 200)
        self.assertFalse(ok)
        self.assertIn("5", err)

    def test_dua_kali_beruntun(self):
        ok, _ = cek_hitungan("5", 4, 200, 200)
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
