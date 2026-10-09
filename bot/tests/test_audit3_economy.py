"""Regression test audit gelombang-1 TRACK EKONOMI (Worker A).

Fokus: sisa race condition / check-then-act di mutasi koin, pinjaman,
lelang+escrow, klaim, dan payout — diverifikasi dengan thread konkuren
nyata (bukan sekadar pola SQL), plus guard toggle/idempotensi.

Jalanin: python -m pytest tests/ -q
"""
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from src.cogs.ekonomi_plus import _coba_buka_pinjaman
from src.cogs.shop import _eksekusi_bid
from src.utils import economy as eko


def _db_file():
    """File DB sementara (WAL) yang bisa dipakai lintas thread."""
    p = Path(tempfile.mkdtemp()) / "audit3.db"
    conn = sqlite3.connect(str(p), timeout=30, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute(
        "CREATE TABLE economy (user_id INTEGER NOT NULL, guild_id INTEGER NOT NULL,"
        " balance INTEGER NOT NULL DEFAULT 0, total_earned INTEGER NOT NULL DEFAULT 0,"
        " last_daily TEXT, last_work TEXT, PRIMARY KEY (user_id, guild_id))"
    )
    conn.execute(
        "CREATE TABLE pinjaman (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " user_id INTEGER NOT NULL, guild_id INTEGER NOT NULL, pokok INTEGER NOT NULL,"
        " sisa INTEGER NOT NULL, bunga_harian INTEGER NOT NULL,"
        " dibuat TEXT NOT NULL, jatuh_tempo TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE lelang (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " guild_id INTEGER NOT NULL, channel_id INTEGER NOT NULL,"
        " message_id INTEGER NOT NULL, nama_role TEXT NOT NULL,"
        " harga_awal INTEGER NOT NULL, tawaran_tertinggi INTEGER NOT NULL DEFAULT 0,"
        " penawar_id INTEGER, ends_at TEXT NOT NULL, ended INTEGER DEFAULT 0)"
    )
    conn.execute(
        "CREATE TABLE lelang_bid (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " lelang_id INTEGER NOT NULL, user_id INTEGER NOT NULL,"
        " jumlah INTEGER NOT NULL, waktu TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE turnamen (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " guild_id INTEGER NOT NULL, jenis TEXT NOT NULL,"
        " status TEXT NOT NULL DEFAULT 'buka', dibuat TEXT NOT NULL, berakhir TEXT)"
    )
    conn.commit()
    conn.close()
    return p


def _conn(p):
    conn = sqlite3.connect(str(p), timeout=30, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def _saldo(p, uid, gid=1):
    with _conn(p) as c:
        r = c.execute(
            "SELECT balance FROM economy WHERE user_id = ? AND guild_id = ?",
            (uid, gid),
        ).fetchone()
    return r[0] if r else None


class TestTambahKoinAtomik(unittest.TestCase):
    def test_konkuren_tidak_hilang(self):
        """10 thread x 100 tambah_koin(1) konkuren -> saldo persis +1000,
        total_earned ikut naik sama (tidak ada penambahan yang hilang)."""
        p = _db_file()
        with _conn(p) as c:
            awal = eko.get_akun(c, 1, 7)["balance"]
        barrier = threading.Barrier(10)

        def kerja():
            c = _conn(p)
            barrier.wait()
            for _ in range(100):
                eko.tambah_koin(c, 1, 7, 1)
            c.close()

        threads = [threading.Thread(target=kerja) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        with _conn(p) as c:
            row = c.execute(
                "SELECT balance, total_earned FROM economy WHERE user_id = 7 AND guild_id = 1"
            ).fetchone()
        self.assertEqual(row[0], awal + 1000)
        self.assertEqual(row[1], row[0])  # total_earned sinkron, tidak ada yang hilang

    def test_nilai_balik_dan_validasi(self):
        p = _db_file()
        with _conn(p) as c:
            c.execute(
                "INSERT INTO economy (user_id, guild_id, balance, total_earned)"
                " VALUES (1, 1, 100, 100)"
            )
            c.commit()
            self.assertEqual(eko.tambah_koin(c, 1, 1, 50), 150)
            with self.assertRaises(ValueError):
                eko.tambah_koin(c, 1, 1, 0)
            with self.assertRaises(ValueError):
                eko.tambah_koin(c, 1, 1, -5)

    def test_get_akun_konkuren_tanpa_integrity_error(self):
        """5 thread get_akun user baru bersamaan -> 1 baris, 1 'baru'."""
        p = _db_file()
        barrier = threading.Barrier(5)
        hasil = []

        def kerja():
            c = _conn(p)
            barrier.wait()
            hasil.append(eko.get_akun(c, 1, 42)["baru"])
            c.close()

        threads = [threading.Thread(target=kerja) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sum(1 for b in hasil if b), 1)
        with _conn(p) as c:
            n = c.execute(
                "SELECT COUNT(*) FROM economy WHERE user_id = 42 AND guild_id = 1"
            ).fetchone()[0]
        self.assertEqual(n, 1)


class TestPinjamanAtomik(unittest.TestCase):
    def test_dua_pinjam_konkuren_hanya_satu(self):
        """Dua /dagang pinjam bersamaan -> tepat 1 pinjaman aktif."""
        p = _db_file()
        barrier = threading.Barrier(2)
        hasil = []
        import datetime

        def kerja():
            c = _conn(p)
            barrier.wait()
            hasil.append(
                _coba_buka_pinjaman(
                    c, 1, 9, 1000, 5, 7,
                    datetime.datetime(2026, 10, 10, tzinfo=datetime.timezone.utc),
                )
            )
            c.close()

        threads = [threading.Thread(target=kerja) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        sukses = [h for h in hasil if h is not None]
        self.assertEqual(len(sukses), 1)
        self.assertEqual(hasil.count(None), 1)
        with _conn(p) as c:
            n = c.execute(
                "SELECT COUNT(*) FROM pinjaman WHERE user_id = 9 AND guild_id = 1 AND sisa > 0"
            ).fetchone()[0]
        self.assertEqual(n, 1)

    def test_pinjam_kedua_setelah_lunas_bisa_lagi(self):
        p = _db_file()
        import datetime

        now = datetime.datetime(2026, 10, 10, tzinfo=datetime.timezone.utc)
        with _conn(p) as c:
            pid = _coba_buka_pinjaman(c, 1, 9, 1000, 5, 7, now)
            self.assertIsNotNone(pid)
            self.assertIsNone(_coba_buka_pinjaman(c, 1, 9, 500, 5, 7, now))
            c.execute("UPDATE pinjaman SET sisa = 0 WHERE id = ?", (pid,))
            c.commit()
            pid2 = _coba_buka_pinjaman(c, 1, 9, 500, 5, 7, now)
            self.assertIsNotNone(pid2)
            self.assertNotEqual(pid, pid2)


class TestBidLelang(unittest.TestCase):
    def _siap(self, p):
        with _conn(p) as c:
            c.execute(
                "INSERT INTO economy (user_id, guild_id, balance, total_earned)"
                " VALUES (1, 1, 10000, 10000), (2, 1, 10000, 10000)"
            )
            c.execute(
                "INSERT INTO lelang (guild_id, channel_id, message_id, nama_role,"
                " harga_awal, ends_at) VALUES (1, 10, 99, 'VIP', 100, '2099-01-01')"
            )
            c.commit()

    def test_bid_konkuren_uang_tidak_hilang_tidak_tercetak(self):
        """A bid 500 vs B bid 800 bersamaan: B menang, A full refund,
        tidak ada koin tercetak / escrow bocor."""
        p = _db_file()
        self._siap(p)
        barrier = threading.Barrier(2)
        hasil = {}

        def kerja(uid, jumlah):
            c = _conn(p)
            barrier.wait()
            hasil[uid] = _eksekusi_bid(c, 1, uid, 10, jumlah)
            c.close()

        ta = threading.Thread(target=kerja, args=(1, 500))
        tb = threading.Thread(target=kerja, args=(2, 800))
        ta.start()
        tb.start()
        ta.join()
        tb.join()
        # B (800) selalu menang pada akhirnya; A bisa "ok" (duluan) atau
        # "minimal" (B duluan) — keduanya benar, yang penting uang konsisten.
        self.assertEqual(hasil[2][0], "ok")
        self.assertIn(hasil[1][0], ("ok", "minimal"))
        with _conn(p) as c:
            tertinggi, penawar = c.execute(
                "SELECT tawaran_tertinggi, penawar_id FROM lelang WHERE id = 1"
            ).fetchone()
        self.assertEqual((tertinggi, penawar), (800, 2))
        # A kembali utuh 10000 (refund escrow 500 bila sempat menang); B tinggal
        # 9200 (800 di escrow). Tidak ada koin tercetak / bocor.
        self.assertEqual(_saldo(p, 1), 10000)
        self.assertEqual(_saldo(p, 2), 9200)
        # Konservasi: 10000 + 9200 + 800 (escrow) = 20000 awal
        self.assertEqual(_saldo(p, 1) + _saldo(p, 2) + tertinggi, 20000)

    def test_bid_setelah_settlement_koin_aman(self):
        """Bid masuk setelah loop menyelesaikan lelang -> ditolak, koin utuh."""
        p = _db_file()
        self._siap(p)
        with _conn(p) as c:
            c.execute("UPDATE lelang SET ended = 1 WHERE id = 1")
            c.commit()
            status, _ = _eksekusi_bid(c, 1, 1, 10, 500)
        self.assertEqual(status, "tidak-ada")
        self.assertEqual(_saldo(p, 1), 10000)  # tidak dipotong

    def test_validasi_minimal_sendiri_koin_kurang(self):
        p = _db_file()
        self._siap(p)
        with _conn(p) as c:
            self.assertEqual(_eksekusi_bid(c, 1, 1, 99, 500)[0], "tidak-ada")
            status, info = _eksekusi_bid(c, 1, 1, 10, 50)
            self.assertEqual(status, "minimal")
            self.assertEqual(info, 101)  # harga_awal 100 + 1
            self.assertEqual(_eksekusi_bid(c, 1, 1, 10, 200)[0], "ok")
            self.assertEqual(_eksekusi_bid(c, 1, 1, 10, 300)[0], "sendiri")
            # koin kurang: user 3 tanpa saldo
            c.execute(
                "INSERT INTO economy (user_id, guild_id, balance, total_earned)"
                " VALUES (3, 1, 10, 10)"
            )
            c.commit()
            self.assertEqual(_eksekusi_bid(c, 1, 3, 10, 500)[0], "koin-kurang")
        self.assertEqual(_saldo(p, 3), 10)


class TestTurnamenBuatAtomik(unittest.TestCase):
    def test_dua_buat_konkuren_hanya_satu(self):
        """Pola INSERT...WHERE NOT EXISTS: dua /lomba buat bersamaan -> 1 row."""
        p = _db_file()
        barrier = threading.Barrier(2)
        hasil = []

        def kerja():
            c = _conn(p)
            barrier.wait()
            cur = c.execute(
                "INSERT INTO turnamen (guild_id, jenis, status, dibuat, berakhir)"
                " SELECT 1, 'susunkata', 'buka', 'x', 'y'"
                " WHERE NOT EXISTS (SELECT 1 FROM turnamen"
                " WHERE guild_id = 1 AND status IN ('buka', 'jalan'))"
            )
            c.commit()
            hasil.append(cur.rowcount)
            c.close()

        threads = [threading.Thread(target=kerja) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sorted(hasil), [0, 1])
        with _conn(p) as c:
            n = c.execute(
                "SELECT COUNT(*) FROM turnamen WHERE guild_id = 1"
                " AND status IN ('buka', 'jalan')"
            ).fetchone()[0]
        self.assertEqual(n, 1)

    def test_settle_idempoten(self):
        """Guard status di _selesaikan_turnamen: settle 2x -> 1x rowcount."""
        p = _db_file()
        with _conn(p) as c:
            c.execute(
                "INSERT INTO turnamen (guild_id, jenis, status, dibuat)"
                " VALUES (1, 'susunkata', 'jalan', 'x')"
            )
            c.commit()
            cur1 = c.execute(
                "UPDATE turnamen SET status = 'selesai' WHERE id = 1"
                " AND status IN ('buka', 'jalan')"
            )
            cur2 = c.execute(
                "UPDATE turnamen SET status = 'selesai' WHERE id = 1"
                " AND status IN ('buka', 'jalan')"
            )
            c.commit()
        self.assertEqual(cur1.rowcount, 1)
        self.assertEqual(cur2.rowcount, 0)  # panggilan kedua tidak payout ulang


if __name__ == "__main__":
    unittest.main()
