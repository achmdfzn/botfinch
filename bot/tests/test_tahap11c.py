"""Tes Tahap 11c — fungsi murni. Jalanin: python -m pytest tests/ -q"""
import datetime
import unittest

from src.cogs.birthday import parse_tanggal_ultah
from src.cogs.bump import bump_sisa_detik
from src.cogs.events import parse_waktu_event
from src.cogs.polls import _interval_human
from src.cogs.reminders import _format_interval
from src.cogs.responder import cari_respons

UTC = datetime.timezone.utc


class TestParseTanggalUltah(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(parse_tanggal_ultah("25-12"), "25-12")
        self.assertEqual(parse_tanggal_ultah("5-3"), "05-03")
        self.assertEqual(parse_tanggal_ultah(" 01-01 "), "01-01")

    def test_kabisat_diterima(self):
        self.assertEqual(parse_tanggal_ultah("29-02"), "29-02")

    def test_invalid(self):
        self.assertIsNone(parse_tanggal_ultah("31-02"))
        self.assertIsNone(parse_tanggal_ultah("32-01"))
        self.assertIsNone(parse_tanggal_ultah("00-12"))
        self.assertIsNone(parse_tanggal_ultah("25-13"))
        self.assertIsNone(parse_tanggal_ultah("25/12"))
        self.assertIsNone(parse_tanggal_ultah("abc"))
        self.assertIsNone(parse_tanggal_ultah(""))
        self.assertIsNone(parse_tanggal_ultah("25-12-2000"))


class TestParseWaktuEvent(unittest.TestCase):
    def test_valid_wib_ke_utc(self):
        # 19:00 WIB = 12:00 UTC
        hasil = parse_waktu_event("25-12-2026 19:00")
        self.assertIsNotNone(hasil)
        self.assertEqual(hasil.tzinfo, UTC)
        self.assertEqual((hasil.hour, hasil.minute), (12, 0))
        self.assertEqual((hasil.day, hasil.month, hasil.year), (25, 12, 2026))

    def test_invalid(self):
        self.assertIsNone(parse_waktu_event("25-12-2026"))
        self.assertIsNone(parse_waktu_event("19:00"))
        self.assertIsNone(parse_waktu_event("32-13-2026 25:00"))
        self.assertIsNone(parse_waktu_event("abc"))
        self.assertIsNone(parse_waktu_event(""))


class TestCariRespons(unittest.TestCase):
    DAFTAR = [("ip mabar", "IP: 1.2.3.4"), ("rules", "Baca #rules ya!")]

    def test_substring_case_insensitive(self):
        self.assertEqual(
            cari_respons(self.DAFTAR, "bang IP MABAR berapa?"), "IP: 1.2.3.4"
        )
        self.assertEqual(cari_respons(self.DAFTAR, "RULES dong"), "Baca #rules ya!")

    def test_pertama_cocok_menang(self):
        daftar = [("mabar", "A"), ("ip mabar", "B")]
        self.assertEqual(cari_respons(daftar, "ip mabar yuk"), "A")

    def test_tidak_cocok(self):
        self.assertIsNone(cari_respons(self.DAFTAR, "halo semua"))
        self.assertIsNone(cari_respons([], "ip mabar"))

    def test_trigger_kosong_dilewati(self):
        self.assertIsNone(cari_respons([("", "x")], "halo"))


class TestBumpSisa(unittest.TestCase):
    def test_belum_pernah(self):
        now = datetime.datetime.now(UTC)
        self.assertEqual(bump_sisa_detik(None, now), 0)

    def test_baru_saja(self):
        now = datetime.datetime.now(UTC)
        iso = (now - datetime.timedelta(minutes=30)).isoformat()
        sisa = bump_sisa_detik(iso, now)
        self.assertGreater(sisa, 0)
        self.assertLessEqual(sisa, 2 * 3600)

    def test_sudah_lewat(self):
        now = datetime.datetime.now(UTC)
        iso = (now - datetime.timedelta(hours=3)).isoformat()
        self.assertEqual(bump_sisa_detik(iso, now), 0)

    def test_iso_rusak(self):
        now = datetime.datetime.now(UTC)
        self.assertEqual(bump_sisa_detik("bukan-tanggal", now), 0)


class TestFormatInterval(unittest.TestCase):
    def test_reminder(self):
        self.assertEqual(_format_interval(3600), "1 jam")
        self.assertEqual(_format_interval(90000), "1 hari 1 jam")
        self.assertEqual(_format_interval(300), "5 menit")

    def test_poll(self):
        self.assertEqual(_interval_human(3600), "1 jam")
        self.assertEqual(_interval_human(604800), "7 hari")
        self.assertEqual(_interval_human(90000), "1 hari 1 jam")


if __name__ == "__main__":
    unittest.main()
