"""Tes Tahap 11a (fungsi murni). Jalanin:  python -m pytest tests/ -q"""
import random
import unittest

from src.cogs.minigames import (
    RPS_PILIHAN,
    acak_kata,
    buat_dek,
    hasil_rps,
    nilai_tangan,
    _cek_taruhan,
)
from src.cogs.economy import _minggu_ini, _parse_jumlah_param


class TestBlackjack(unittest.TestCase):
    def test_dek_52_unik(self):
        dek = buat_dek(random.Random(1))
        self.assertEqual(len(dek), 52)
        self.assertEqual(len(set(dek)), 52)
        for rank, suit in dek:
            self.assertEqual(len((rank, suit)), 2)

    def test_nilai_blackjack(self):
        self.assertEqual(nilai_tangan([("A", "♠"), ("K", "♥")]), 21)

    def test_as_ganda_turun(self):
        # A + 9 + A = 11 + 9 + 1 = 21
        self.assertEqual(
            nilai_tangan([("A", "♠"), ("9", "♥"), ("A", "♦")]), 21
        )

    def test_as_jadi_satu_saat_bust(self):
        # A + K + 9 = 11+10+9=30 -> As jadi 1 -> 20
        self.assertEqual(
            nilai_tangan([("A", "♠"), ("K", "♥"), ("9", "♦")]), 20
        )

    def test_kartu_angka_dan_face(self):
        self.assertEqual(nilai_tangan([("10", "♠"), ("9", "♥")]), 19)
        self.assertEqual(nilai_tangan([("J", "♠"), ("Q", "♥")]), 20)

    def test_bust_tanpa_as(self):
        self.assertEqual(nilai_tangan([("K", "♠"), ("9", "♥"), ("5", "♦")]), 24)


class TestAcakKata(unittest.TestCase):
    def test_beda_dari_asli_huruf_sama(self):
        for kata in ["kucing", "komputer", "sepeda", "bintang"]:
            hasil = acak_kata(kata, random.Random(42))
            self.assertNotEqual(hasil.lower(), kata.lower(), kata)
            self.assertEqual(sorted(hasil.lower()), sorted(kata.lower()), kata)

    def test_deterministik_dengan_seed(self):
        a = acak_kata("kucing", random.Random(7))
        b = acak_kata("kucing", random.Random(7))
        self.assertEqual(a, b)


class TestRps(unittest.TestCase):
    def test_seri(self):
        for p in RPS_PILIHAN:
            self.assertEqual(hasil_rps(p, p), "seri")

    def test_menang_kalah(self):
        self.assertEqual(hasil_rps("gunting", "kertas"), "menang")
        self.assertEqual(hasil_rps("kertas", "gunting"), "kalah")
        self.assertEqual(hasil_rps("batu", "gunting"), "menang")
        self.assertEqual(hasil_rps("gunting", "batu"), "kalah")


class TestCekTaruhan(unittest.TestCase):
    def test_valid(self):
        self.assertIsNone(_cek_taruhan(1000, 100))

    def test_dibawah_minimal(self):
        err = _cek_taruhan(1000, 5)
        self.assertIsNotNone(err)
        self.assertIn("minimal", err)

    def test_diatas_maksimal(self):
        err = _cek_taruhan(100000, 6000)
        self.assertIsNotNone(err)
        self.assertIn("maksimal", err)

    def test_saldo_kurang(self):
        err = _cek_taruhan(100, 500)
        self.assertIsNotNone(err)
        self.assertIn("tidak cukup", err)

    def test_negatif(self):
        self.assertIsNotNone(_cek_taruhan(1000, -10))


class TestMingguIni(unittest.TestCase):
    def test_format(self):
        import datetime

        m = _minggu_ini(datetime.datetime(2026, 10, 8, tzinfo=datetime.timezone.utc))
        self.assertEqual(m, "2026-W41")


class TestParseJumlah(unittest.TestCase):
    def test_angka(self):
        n, err = _parse_jumlah_param("500", 1000)
        self.assertEqual((n, err), (500, None))

    def test_all(self):
        for t in ["all", "ALL", "semua", " Semua "]:
            n, err = _parse_jumlah_param(t, 1000)
            self.assertEqual((n, err), (1000, None))

    def test_invalid(self):
        n, err = _parse_jumlah_param("abc", 1000)
        self.assertIsNone(n)
        self.assertIsNotNone(err)

    def test_nol_negatif(self):
        self.assertIsNotNone(_parse_jumlah_param("0", 1000)[1])
        self.assertIsNotNone(_parse_jumlah_param("-5", 1000)[1])


if __name__ == "__main__":
    unittest.main()
