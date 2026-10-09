"""Tes Tahap 11B: syarat giveaway + helper murni baru."""
import unittest

from src.cogs.giveaway import _cek_syarat
from src.cogs.voicexp import format_menit


class TestCekSyarat(unittest.TestCase):
    def test_lolos_semua(self):
        self.assertIsNone(
            _cek_syarat(10, 500, {1, 2}, min_level=5, min_koin=100, role_syarat=2)
        )

    def test_tanpa_syarat_lolos(self):
        self.assertIsNone(_cek_syarat(1, 0, set(), 0, 0, 0))

    def test_level_kurang(self):
        alasan = _cek_syarat(3, 500, {1}, min_level=5, min_koin=0, role_syarat=0)
        self.assertIsNotNone(alasan)
        self.assertIn("level", alasan.lower())

    def test_level_pas(self):
        self.assertIsNone(_cek_syarat(5, 0, set(), min_level=5, min_koin=0, role_syarat=0))

    def test_koin_kurang(self):
        alasan = _cek_syarat(10, 50, set(), min_level=0, min_koin=100, role_syarat=0)
        self.assertIsNotNone(alasan)
        self.assertIn("koin", alasan.lower())

    def test_role_kurang(self):
        alasan = _cek_syarat(10, 500, {1}, min_level=0, min_koin=0, role_syarat=2)
        self.assertIsNotNone(alasan)
        self.assertIn("role", alasan.lower())

    def test_prioritas_level_dulu(self):
        # gagal di syarat pertama yang tidak terpenuhi
        alasan = _cek_syarat(1, 0, set(), min_level=5, min_koin=100, role_syarat=9)
        self.assertIn("level", alasan.lower())


class TestFormatMenit(unittest.TestCase):
    def test_menit_biasa(self):
        self.assertEqual(format_menit(45), "45 mnt")

    def test_pas_jam(self):
        self.assertEqual(format_menit(120), "2 jam")

    def test_jam_menit(self):
        self.assertEqual(format_menit(90), "1 jam 30 mnt")

    def test_nol_dan_negatif(self):
        self.assertEqual(format_menit(0), "0 mnt")
        self.assertEqual(format_menit(-5), "0 mnt")


if __name__ == "__main__":
    unittest.main()
