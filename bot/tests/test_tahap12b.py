"""Tes Tahap 12b — turnamen, kuis, adu-cepat, ship (fungsi murni).

Jalanin:  python -m pytest tests/ -q
"""
import random
import unittest

from src.cogs.turnamen import (
    BANK_KUIS,
    KATA_SUSUN,
    acak_kata,
    normalisasi_jawaban,
    pesan_ship,
    skor_kuis_benar,
    skor_ship,
)


class TestAcakKata(unittest.TestCase):
    def test_return_tuple_asli_acak(self):
        rng = random.Random(42)
        asli, acak = acak_kata(rng)
        self.assertIn(asli, KATA_SUSUN)
        self.assertNotEqual(acak, asli)

    def test_huruf_sama(self):
        rng = random.Random(7)
        for _ in range(20):
            asli, acak = acak_kata(rng)
            self.assertEqual(sorted(acak), sorted(asli))

    def test_deterministik_dengan_seed(self):
        a1, b1 = acak_kata(random.Random(123))
        a2, b2 = acak_kata(random.Random(123))
        self.assertEqual((a1, b1), (a2, b2))


class TestNormalisasi(unittest.TestCase):
    def test_case_dan_spasi(self):
        self.assertEqual(normalisasi_jawaban("  JaKaRtA "), "jakarta")

    def test_spasi_ganda(self):
        self.assertEqual(normalisasi_jawaban("soekarno  hatta"), "soekarno hatta")

    def test_kosong(self):
        self.assertEqual(normalisasi_jawaban("   "), "")


class TestSkorKuis(unittest.TestCase):
    def test_pertama_full_bonus(self):
        self.assertEqual(skor_kuis_benar(True, 20.0, 20.0), 150)

    def test_pertama_tanpa_sisa(self):
        self.assertEqual(skor_kuis_benar(True, 0.0, 20.0), 100)

    def test_pertama_setengah(self):
        self.assertEqual(skor_kuis_benar(True, 10.0, 20.0), 125)

    def test_bukan_pertama(self):
        self.assertEqual(skor_kuis_benar(False, 20.0, 20.0), 50)
        self.assertEqual(skor_kuis_benar(False, 0.0, 20.0), 50)


class TestShip(unittest.TestCase):
    def test_deterministik(self):
        self.assertEqual(skor_ship(111, 222), skor_ship(111, 222))

    def test_urutan_tidak_pengaruh(self):
        self.assertEqual(skor_ship(111, 222), skor_ship(222, 111))

    def test_rentang(self):
        for a, b in [(1, 2), (999, 1000), (123456789, 987654321)]:
            s = skor_ship(a, b)
            self.assertGreaterEqual(s, 0)
            self.assertLessEqual(s, 100)

    def test_id_sama_tetap_valid(self):
        s = skor_ship(5, 5)
        self.assertGreaterEqual(s, 0)
        self.assertLessEqual(s, 100)


class TestPesanShip(unittest.TestCase):
    def test_semua_tier_ada_pesan(self):
        for skor in (0, 29, 30, 49, 50, 69, 70, 89, 90, 100):
            self.assertTrue(pesan_ship(skor), f"skor {skor} tanpa pesan")


class TestBankKuis(unittest.TestCase):
    def test_15_soal(self):
        self.assertEqual(len(BANK_KUIS), 15)

    def test_soal_jawaban_tidak_kosong(self):
        for soal, jawaban in BANK_KUIS:
            self.assertTrue(soal.strip())
            self.assertTrue(jawaban.strip())

    def test_jawaban_ternormalisasi_unik(self):
        norm = [normalisasi_jawaban(j) for _, j in BANK_KUIS]
        self.assertEqual(len(norm), len(set(norm)), "ada jawaban duplikat")


class TestKataSusn(unittest.TestCase):
    def test_cukup_banyak_dan_valid(self):
        self.assertGreaterEqual(len(KATA_SUSUN), 20)
        for kata in KATA_SUSUN:
            self.assertTrue(kata.isalpha(), f"kata tidak valid: {kata}")
            self.assertGreaterEqual(len(kata), 3)


if __name__ == "__main__":
    unittest.main()
