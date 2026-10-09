"""Tes Tahap 12a — ekonomi+ (fungsi murni)."""
import random
import unittest

from src.cogs.ekonomi_plus import (
    bunga_deposito,
    harga_saham_baru,
    hari_valid_deposito,
    hitung_bunga,
    roll_peti,
)
from src.utils import consumable as cons


class _RngTetap:
    """RNG terkendali untuk tes deterministik."""

    def __init__(self, nilai_random, nilai_int, pilihan):
        self._r = nilai_random
        self._i = nilai_int
        self._p = pilihan

    def random(self):
        return self._r

    def randint(self, a, b):
        assert a <= self._i <= b, f"{self._i} di luar [{a},{b}]"
        return self._i

    def choice(self, seq):
        assert self._p in seq
        return self._p


class TestBunga(unittest.TestCase):
    def test_hitung_bunga(self):
        self.assertEqual(hitung_bunga(1000, 5), 50)
        self.assertEqual(hitung_bunga(999, 5), 49)  # floor
        self.assertEqual(hitung_bunga(0, 5), 0)

    def test_bunga_deposito(self):
        self.assertEqual(bunga_deposito(1000, 8), 80)
        self.assertEqual(bunga_deposito(1000, 3), 30)


class TestSaham(unittest.TestCase):
    def test_harga_naik(self):
        self.assertEqual(harga_saham_baru(100, 1.1), 110)

    def test_harga_turun(self):
        self.assertEqual(harga_saham_baru(100, 0.85), 85)

    def test_harga_minimal_10(self):
        self.assertEqual(harga_saham_baru(5, 0.5), 10)
        self.assertEqual(harga_saham_baru(10, 0.1), 10)


class TestDeposito(unittest.TestCase):
    def test_hari_valid(self):
        pilihan = [(7, 3), (30, 8)]
        self.assertTrue(hari_valid_deposito(7, pilihan))
        self.assertTrue(hari_valid_deposito(30, pilihan))

    def test_hari_tidak_valid(self):
        pilihan = [(7, 3), (30, 8)]
        self.assertFalse(hari_valid_deposito(14, pilihan))
        self.assertFalse(hari_valid_deposito(0, pilihan))


class TestPeti(unittest.TestCase):
    def test_koin_kecil(self):
        jenis, nilai = roll_peti(_RngTetap(0.10, 150, "perisai"))
        self.assertEqual((jenis, nilai), ("koin", 150))

    def test_koin_besar(self):
        jenis, nilai = roll_peti(_RngTetap(0.70, 500, "perisai"))
        self.assertEqual((jenis, nilai), ("koin", 500))

    def test_dapat_item(self):
        jenis, nilai = roll_peti(_RngTetap(0.95, 0, "tiket"))
        self.assertEqual(jenis, "item")
        self.assertIn(nilai, cons.ITEMS)

    def test_distribusi_sanity(self):
        rng = random.Random(42)
        hasil = [roll_peti(rng)[0] for _ in range(2000)]
        p_koin = hasil.count("koin") / len(hasil)
        # ekspektasi koin 85% — toleransi longgar
        self.assertGreater(p_koin, 0.75)
        self.assertLess(p_koin, 0.95)


if __name__ == "__main__":
    unittest.main()
