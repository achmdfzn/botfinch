"""Tes Tahap 12e (engagement: pet, quest guild, daily question, hof, hidden achievement).

Jalanin: python -m pytest tests/test_tahap12e.py -q
"""
import datetime
import sqlite3
import unittest

from src.cogs.bump import ekstrak_bumper_id
from src.cogs.engagement import (
    PERTANYAAN_HARIAN,
    pet_level,
    pet_progress,
    pertanyaan_tanggal,
    senin_depan_utc,
)
from src.utils import achievement as ach


def db_achievement() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE achievement (user_id INTEGER NOT NULL, guild_id INTEGER NOT NULL,"
        " kode TEXT NOT NULL, tgl TEXT NOT NULL, PRIMARY KEY (user_id, guild_id, kode))"
    )
    return conn


class TestPet(unittest.TestCase):
    def test_level_dasar(self):
        self.assertEqual(pet_level(0), 1)
        self.assertEqual(pet_level(99), 1)
        self.assertEqual(pet_level(100), 2)
        self.assertEqual(pet_level(250), 3)

    def test_progress(self):
        self.assertEqual(pet_progress(0), (0, 100))
        self.assertEqual(pet_progress(45), (45, 100))
        self.assertEqual(pet_progress(100), (0, 100))
        self.assertEqual(pet_progress(199), (99, 100))

    def test_level_negatif_aman(self):
        self.assertEqual(pet_level(-5), 1)


class TestSeninDepan(unittest.TestCase):
    def test_selalu_senin_tengah_malam_utc(self):
        for hari in range(7):
            dari = datetime.datetime(2026, 10, 5 + hari, 12, 0, tzinfo=datetime.timezone.utc)
            hasil = senin_depan_utc(dari)
            self.assertEqual(hasil.weekday(), 0, "harus hari Senin")
            self.assertEqual((hasil.hour, hasil.minute, hasil.second), (0, 0, 0))
            self.assertGreater(hasil, dari, "harus di masa depan")

    def test_tepat_senin_tengah_malam_lompat_seminggu(self):
        dari = datetime.datetime(2026, 10, 12, 0, 0, tzinfo=datetime.timezone.utc)  # Senin
        hasil = senin_depan_utc(dari)
        self.assertEqual(hasil, dari + datetime.timedelta(days=7))


class TestDailyQuestion(unittest.TestCase):
    def test_30_pertanyaan(self):
        self.assertEqual(len(PERTANYAAN_HARIAN), 30)
        self.assertEqual(len(set(PERTANYAAN_HARIAN)), 30, "tidak boleh ada duplikat")

    def test_deterministik_per_tanggal(self):
        a = pertanyaan_tanggal("2026-10-08", 10)
        b = pertanyaan_tanggal("2026-10-08", 10)
        self.assertEqual(a, b)
        self.assertIn(a, PERTANYAAN_HARIAN)

    def test_beda_guild_boleh_beda(self):
        # tidak diwajibkan beda, tapi harus valid
        q = pertanyaan_tanggal("2026-10-08", 99)
        self.assertIn(q, PERTANYAAN_HARIAN)


class TestBumpKoin(unittest.TestCase):
    def test_ekstrak_mention(self):
        self.assertEqual(
            ekstrak_bumper_id(["<@123456> BUMP done!"]),
            123456,
        )
        self.assertEqual(
            ekstrak_bumper_id(["<@!789> just bumped"]),
            789,
        )

    def test_tanpa_mention(self):
        self.assertIsNone(ekstrak_bumper_id(["BUMP done!"]))
        self.assertIsNone(ekstrak_bumper_id([None]))
        self.assertIsNone(ekstrak_bumper_id([]))

    def test_abaikan_disboard_sendiri(self):
        self.assertIsNone(ekstrak_bumper_id(["<@302050872383242240> BUMP done!"]))


class TestHiddenAchievement(unittest.TestCase):
    def test_flag_hidden(self):
        for kode in ("hantu", "sultan_diam", "kolektor", "sosialita"):
            self.assertTrue(ach.is_hidden(kode), kode)
        self.assertFalse(ach.is_hidden("level10"))

    def test_struktur_tetap_5_tuple(self):
        # cek_buka unpack 5 elemen — achievement baru harus kompatibel
        for item in ach.ACHIEVEMENTS:
            self.assertEqual(len(item), 5)

    def test_cek_buka_hantu(self):
        conn = db_achievement()
        baru = ach.cek_buka(conn, 10, 1, {"hantu": 1})
        self.assertEqual(baru, [("hantu", "👻 Hantu")])
        # tidak dibuka dua kali
        self.assertEqual(ach.cek_buka(conn, 10, 1, {"hantu": 1}), [])
        conn.close()

    def test_cek_buka_sultan_diam(self):
        conn = db_achievement()
        self.assertEqual(ach.cek_buka(conn, 10, 1, {"sultan_diam": 50_000}), [])
        baru = ach.cek_buka(conn, 10, 1, {"sultan_diam": 100_000})
        self.assertEqual([k for k, _ in baru], ["sultan_diam"])
        conn.close()

    def test_cek_buka_kolektor_sosialita(self):
        conn = db_achievement()
        self.assertEqual([k for k, _ in ach.cek_buka(conn, 10, 1, {"kolektor": 3})], ["kolektor"])
        self.assertEqual([k for k, _ in ach.cek_buka(conn, 10, 1, {"sosialita": 1})], ["sosialita"])
        conn.close()

    def test_achievement_lama_tidak_berubah(self):
        conn = db_achievement()
        baru = ach.cek_buka(conn, 10, 1, {"level": 10})
        self.assertEqual(baru, [("level10", "🌟 Naik Daun")])
        conn.close()

    def test_hidden_terkunci(self):
        conn = db_achievement()
        terkunci = ach.hidden_terkunci(conn, 10, 1)
        self.assertEqual(set(terkunci), {"hantu", "sultan_diam", "kolektor", "sosialita"})
        ach.cek_buka(conn, 10, 1, {"hantu": 1})
        terkunci = ach.hidden_terkunci(conn, 10, 1)
        self.assertNotIn("hantu", terkunci)
        self.assertEqual(len(terkunci), 3)
        conn.close()

    def test_daftar_hanya_yang_terbuka(self):
        conn = db_achievement()
        ach.cek_buka(conn, 10, 1, {"hantu": 1})
        daftar = ach.daftar(conn, 10, 1)
        self.assertEqual(len(daftar), 1)
        self.assertEqual(daftar[0][0], "hantu")
        self.assertEqual(daftar[0][1], "👻 Hantu")
        conn.close()


class TestServerPoolUpsert(unittest.TestCase):
    def test_hadiah_quest_masuk_pool(self):
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE server_pool (guild_id INTEGER PRIMARY KEY,"
            " koin INTEGER NOT NULL DEFAULT 0)"
        )
        for _ in range(2):
            conn.execute(
                "INSERT INTO server_pool (guild_id, koin) VALUES (?, ?)"
                " ON CONFLICT(guild_id) DO UPDATE SET koin = koin + ?",
                (10, 300, 300),
            )
            conn.commit()
        koin = conn.execute(
            "SELECT koin FROM server_pool WHERE guild_id = 10"
        ).fetchone()[0]
        self.assertEqual(koin, 600)
        conn.close()


if __name__ == "__main__":
    unittest.main()
