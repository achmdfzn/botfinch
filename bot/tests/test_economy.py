"""Tes sistem koin (economy). Jalanin:  python -m pytest tests/ -q"""
import datetime
import random
import sqlite3
import unittest

from src import config
from src.utils import economy as eko

UTC = datetime.timezone.utc


def _conn_baru():
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE economy (
            user_id INTEGER NOT NULL,
            guild_id INTEGER NOT NULL,
            balance INTEGER NOT NULL DEFAULT 0,
            total_earned INTEGER NOT NULL DEFAULT 0,
            last_daily TEXT,
            last_work TEXT,
            rep INTEGER NOT NULL DEFAULT 0,
            last_rep TEXT,
            last_trivia TEXT,
            PRIMARY KEY (user_id, guild_id)
        )
    """)
    return conn


def _now():
    return datetime.datetime.now(UTC)


class TestAkunKoin(unittest.TestCase):
    def setUp(self):
        self.conn = _conn_baru()

    def tearDown(self):
        self.conn.close()

    def test_akun_baru_dapat_saldo_awal(self):
        akun = eko.get_akun(self.conn, 1, 100)
        self.assertTrue(akun["baru"])
        self.assertEqual(akun["balance"], config.settings.economy_start_balance)
        self.assertEqual(akun["total_earned"], config.settings.economy_start_balance)

    def test_akun_lama_tidak_baru(self):
        eko.get_akun(self.conn, 1, 100)
        akun = eko.get_akun(self.conn, 1, 100)
        self.assertFalse(akun["baru"])

    def test_tambah_koin(self):
        mulai = config.settings.economy_start_balance
        baru = eko.tambah_koin(self.conn, 1, 100, 250)
        self.assertEqual(baru, mulai + 250)
        akun = eko.get_akun(self.conn, 1, 100)
        self.assertEqual(akun["total_earned"], mulai + 250)

    def test_tambah_koin_invalid(self):
        with self.assertRaises(ValueError):
            eko.tambah_koin(self.conn, 1, 100, 0)
        with self.assertRaises(ValueError):
            eko.tambah_koin(self.conn, 1, 100, -5)

    def test_kurang_koin_cukup(self):
        mulai = config.settings.economy_start_balance
        sisa = eko.kurang_koin(self.conn, 1, 100, 30)
        self.assertEqual(sisa, mulai - 30)

    def test_kurang_koin_tidak_cukup(self):
        mulai = config.settings.economy_start_balance
        hasil = eko.kurang_koin(self.conn, 1, 100, mulai + 9999)
        self.assertIsNone(hasil)
        # saldo tidak berubah
        self.assertEqual(eko.get_akun(self.conn, 1, 100)["balance"], mulai)

    def test_kurang_koin_invalid(self):
        with self.assertRaises(ValueError):
            eko.kurang_koin(self.conn, 1, 100, 0)


class TestCooldown(unittest.TestCase):
    def setUp(self):
        self.conn = _conn_baru()

    def tearDown(self):
        self.conn.close()

    def test_daily_ok_lalu_cooldown(self):
        rng = random.Random(7)
        status, nilai = eko.klaim_daily(self.conn, 1, 100, _now(), rng)
        self.assertEqual(status, "ok")
        s = config.settings
        self.assertGreaterEqual(nilai, s.economy_daily_min)
        self.assertLessEqual(nilai, s.economy_daily_max)

        status2, sisa = eko.klaim_daily(self.conn, 1, 100, _now(), rng)
        self.assertEqual(status2, "cooldown")
        self.assertGreater(sisa, 0)
        self.assertLessEqual(sisa, 24 * 3600)

    def test_daily_bisa_lagi_setelah_24jam(self):
        rng = random.Random(7)
        eko.klaim_daily(self.conn, 1, 100, _now(), rng)
        besok = _now() + datetime.timedelta(hours=25)
        status, _ = eko.klaim_daily(self.conn, 1, 100, besok, rng)
        self.assertEqual(status, "ok")

    def test_kerja_cooldown_config(self):
        rng = random.Random(3)
        cd = config.settings.economy_work_cooldown
        status, nilai = eko.kerja(self.conn, 1, 100, _now(), rng)
        self.assertEqual(status, "ok")
        s = config.settings
        self.assertGreaterEqual(nilai, s.economy_work_min)
        self.assertLessEqual(nilai, s.economy_work_max)

        status2, sisa = eko.kerja(self.conn, 1, 100, _now(), rng)
        if cd > 0:
            self.assertEqual(status2, "cooldown")
            self.assertLessEqual(sisa, cd)
        else:
            self.assertEqual(status2, "ok")


class TestPeringkatTop(unittest.TestCase):
    def setUp(self):
        self.conn = _conn_baru()

    def tearDown(self):
        self.conn.close()

    def test_peringkat_dan_top(self):
        eko.tambah_koin(self.conn, 1, 101, 500)  # terkaya
        eko.tambah_koin(self.conn, 1, 102, 100)
        eko.get_akun(self.conn, 1, 103)  # saldo awal saja
        self.assertEqual(eko.peringkat(self.conn, 1, 101), 1)
        self.assertEqual(eko.peringkat(self.conn, 1, 102), 2)
        top = eko.top_koin(self.conn, 1, 10)
        self.assertEqual(top[0][0], 101)
        self.assertEqual(top[1][0], 102)
        self.assertEqual(top[2][0], 103)
        # limit dihormati
        self.assertEqual(len(eko.top_koin(self.conn, 1, 2)), 2)

    def test_format_sisa_waktu(self):
        self.assertEqual(eko.format_sisa_waktu(3661), "1 jam 1 menit")
        self.assertEqual(eko.format_sisa_waktu(300), "5 menit")
        self.assertEqual(eko.format_sisa_waktu(0), "0 menit")


class TestRep(unittest.TestCase):
    def setUp(self):
        self.conn = _conn_baru()

    def tearDown(self):
        self.conn.close()

    def test_beri_rep_ok(self):
        status, rep = eko.beri_rep(self.conn, 1, 100, 200, _now())
        self.assertEqual(status, "ok")
        self.assertEqual(rep, 1)
        self.assertEqual(eko.get_rep(self.conn, 1, 200), 1)

    def test_rep_cooldown_24jam(self):
        eko.beri_rep(self.conn, 1, 100, 200, _now())
        status, sisa = eko.beri_rep(self.conn, 1, 100, 300, _now())
        self.assertEqual(status, "cooldown")
        self.assertGreater(sisa, 0)
        # target lain pun ikut cooldown (satu rep per 24 jam per pemberi)
        self.assertEqual(eko.get_rep(self.conn, 1, 300), 0)

    def test_rep_bisa_lagi_besok(self):
        eko.beri_rep(self.conn, 1, 100, 200, _now())
        besok = _now() + datetime.timedelta(hours=25)
        status, rep = eko.beri_rep(self.conn, 1, 100, 200, besok)
        self.assertEqual(status, "ok")
        self.assertEqual(rep, 2)


class TestTriviaCooldown(unittest.TestCase):
    def setUp(self):
        self.conn = _conn_baru()

    def tearDown(self):
        self.conn.close()

    def test_boleh_lalu_cooldown(self):
        cd = config.settings.economy_trivia_cooldown
        boleh, _ = eko.bisa_trivia(self.conn, 1, 100, _now(), cd)
        self.assertTrue(boleh)
        eko.catat_trivia(self.conn, 1, 100, _now())
        boleh2, sisa = eko.bisa_trivia(self.conn, 1, 100, _now(), cd)
        if cd > 0:
            self.assertFalse(boleh2)
            self.assertGreater(sisa, 0)
        else:
            self.assertTrue(boleh2)


if __name__ == "__main__":
    unittest.main()
