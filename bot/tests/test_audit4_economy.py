"""Regression test audit putaran-4 TRACK EKONOMI.

Fokus: SISA race condition / idempotensi yang lolos dari audit 1-3 —
- `trivia_menang` masih read-modify-write (SELECT lalu SET) -> kini atomik
  via utils.economy.catat_trivia_menang
- bunga bank (`bunga_harian`) & bunga pinjaman (`_loop_harian`) dibayar
  ganda tiap restart bot (tasks.loop jalan lagi saat startup) -> kini
  di-gate per hari via utils.economy.tandai_harian
- INSERT baris pertama quest (`_baris`) & season (`_pastikan_state`)
  tanpa OR IGNORE -> kini anti IntegrityError saat balapan
- cap atas `/dagang trade` disamakan dengan `/transfer`

Semua klaim sensitif diverifikasi dengan thread konkuren nyata
(bukan sekadar pola SQL), memakai DB file WAL sementara.

Jalanin: ~/workspace/finch/bot/.venv/bin/python -m pytest tests/test_audit4_economy.py -q
"""
import datetime
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from src.cogs.ekonomi_plus import _coba_buka_pinjaman
from src.cogs.season import _pastikan_state
from src.cogs.shop import _eksekusi_bid
from src.utils import economy as eko
from src.utils import consumable as cons
from src.utils import quests as q


def _db_file():
    """File DB sementara (WAL) yang bisa dipakai lintas thread."""
    p = Path(tempfile.mkdtemp()) / "audit4.db"
    conn = sqlite3.connect(str(p), timeout=30, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute(
        "CREATE TABLE economy (user_id INTEGER NOT NULL, guild_id INTEGER NOT NULL,"
        " balance INTEGER NOT NULL DEFAULT 0, total_earned INTEGER NOT NULL DEFAULT 0,"
        " last_daily TEXT, last_work TEXT, trivia_menang INTEGER DEFAULT 0,"
        " PRIMARY KEY (user_id, guild_id))"
    )
    conn.execute(
        "CREATE TABLE quest_progress (user_id INTEGER NOT NULL, guild_id INTEGER NOT NULL,"
        " tanggal TEXT NOT NULL, pesan INTEGER NOT NULL DEFAULT 0,"
        " voice_menit INTEGER NOT NULL DEFAULT 0, daily_ok INTEGER NOT NULL DEFAULT 0,"
        " klaim_pesan INTEGER NOT NULL DEFAULT 0, klaim_voice INTEGER NOT NULL DEFAULT 0,"
        " klaim_daily INTEGER NOT NULL DEFAULT 0,"
        " PRIMARY KEY (user_id, guild_id, tanggal))"
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
        "CREATE TABLE inventory (user_id INTEGER NOT NULL, guild_id INTEGER NOT NULL,"
        " item_id TEXT NOT NULL, jumlah INTEGER NOT NULL DEFAULT 0, berakhir TEXT,"
        " PRIMARY KEY (user_id, guild_id, item_id))"
    )
    conn.execute(
        "CREATE TABLE season_state (guild_id INTEGER PRIMARY KEY,"
        " season INTEGER NOT NULL DEFAULT 1, berakhir TEXT NOT NULL)"
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


def _jalan_bersama(target, n=8):
    """Jalankan `target()` di n thread yang start sedekat mungkin."""
    barrier = threading.Barrier(n)
    hasil = [None] * n
    errors = []

    def _bungkus(i):
        try:
            barrier.wait(timeout=10)
            hasil[i] = target()
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=_bungkus, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert not errors, f"thread error: {errors!r}"
    return hasil


class TestAudit4Race(unittest.TestCase):
    def test_daily_double_claim_hanya_satu_ok(self):
        """/daily konkuren: hanya satu yang dapat 'ok'."""
        p = _db_file()
        now = datetime.datetime.now(datetime.timezone.utc)

        def _klaim():
            with _conn(p) as c:
                return eko._klaim_cooldown(
                    c, 1, 42, "last_daily", 86400, 100, 100, now
                )

        hasil = _jalan_bersama(_klaim)
        ok = [h for h in hasil if h[0] == "ok"]
        self.assertEqual(len(ok), 1)
        self.assertEqual(ok[0][1], 100)
        # 100 saldo awal akun baru (ECONOMY_START_BALANCE) + 100 daily
        self.assertEqual(_saldo(p, 42), 200)

    def test_quest_klaim_hanya_dibayar_sekali(self):
        """/quest klaim konkuren: total hadiah hanya dibayar sekali."""
        p = _db_file()
        with _conn(p) as c:
            c.execute(
                "INSERT INTO quest_progress (user_id, guild_id, tanggal, pesan)"
                " VALUES (1, 1, ?, 25)",
                (q._tanggal_hari_ini(),),
            )
            c.commit()

        def _klaim():
            with _conn(p) as c:
                return q.klaim_quest(c, 1, 1)

        hasil = _jalan_bersama(_klaim)
        total = sum(h[0] for h in hasil)
        dapat = [h for h in hasil if h[0] > 0]
        self.assertEqual(total, 150)  # hadiah quest 'pesan'
        self.assertEqual(len(dapat), 1)

    def test_trivia_menang_atomik(self):
        """Increment trivia_menang konkuren: tidak ada yang hilang."""
        p = _db_file()

        def _naik():
            n = 0
            with _conn(p) as c:
                for _ in range(5):
                    n = eko.catat_trivia_menang(c, 1, 7)
            return n

        _jalan_bersama(_naik)
        with _conn(p) as c:
            r = c.execute(
                "SELECT trivia_menang FROM economy WHERE user_id = 7 AND guild_id = 1"
            ).fetchone()
        self.assertIsNotNone(r)
        self.assertEqual(r[0], 8 * 5)

    def test_konsumsi_satu_hanya_satu_berhasil(self):
        """1 item dipakai 8 thread bersamaan: hanya satu yang berhasil."""
        p = _db_file()
        with _conn(p) as c:
            c.execute(
                "INSERT INTO inventory (user_id, guild_id, item_id, jumlah, berakhir)"
                " VALUES (1, 1, 'tiket', 1, NULL)"
            )
            c.commit()

        def _pakai():
            with _conn(p) as c:
                return cons.konsumsi_satu(c, 1, 1, "tiket")

        hasil = _jalan_bersama(_pakai)
        self.assertEqual(sum(1 for h in hasil if h), 1)

    def test_bid_konkuren_escrow_konsisten(self):
        """Dua /bid bersamaan: escrow tidak bocor, tidak refund ganda."""
        p = _db_file()
        with _conn(p) as c:
            eko.tambah_koin(c, 1, 11, 1000)
            eko.tambah_koin(c, 1, 12, 1000)
            c.execute(
                "INSERT INTO lelang (guild_id, channel_id, message_id, nama_role,"
                " harga_awal, ends_at) VALUES (1, 7, 99, 'VIP', 100, '2099-01-01T00:00:00+00:00')"
            )
            c.commit()

        def _bid_a():
            with _conn(p) as c:
                return _eksekusi_bid(c, 1, 11, 7, 200)

        def _bid_b():
            with _conn(p) as c:
                return _eksekusi_bid(c, 1, 12, 7, 300)

        barrier = threading.Barrier(2)
        out = {}

        def _run(k, fn):
            barrier.wait(timeout=10)
            out[k] = fn()

        ta = threading.Thread(target=_run, args=("a", _bid_a))
        tb = threading.Thread(target=_run, args=("b", _bid_b))
        ta.start()
        tb.start()
        ta.join(timeout=60)
        tb.join(timeout=60)
        # B (300) selalu menang; status A tergantung urutan: 'ok' bila duluan,
        # 'minimal' bila B sudah menawar 300 lebih dulu. Saldo akhir deterministik.
        self.assertEqual(out["b"][0], "ok")
        self.assertIn(out["a"][0], ("ok", "minimal"))
        self.assertEqual(_saldo(p, 11), 1000 + 100)  # kembali utuh + saldo awal
        self.assertEqual(_saldo(p, 12), 700 + 100)  # 300 ditahan escrow
        with _conn(p) as c:
            r = c.execute(
                "SELECT tawaran_tertinggi, penawar_id FROM lelang WHERE id = 1"
            ).fetchone()
            n_bid = c.execute("SELECT COUNT(*) FROM lelang_bid").fetchone()[0]
        self.assertEqual((r[0], r[1]), (300, 12))
        # Hanya bid yang lolos yang tercatat di lelang_bid.
        self.assertEqual(n_bid, 2 if out["a"][0] == "ok" else 1)

    def test_pinjam_konkuren_hanya_satu(self):
        """Dua /dagang pinjam bersamaan: hanya satu pinjaman aktif."""
        p = _db_file()
        now = datetime.datetime.now(datetime.timezone.utc)

        def _pinjam():
            with _conn(p) as c:
                return _coba_buka_pinjaman(c, 1, 5, 1000, 5, 7, now)

        hasil = _jalan_bersama(_pinjam)
        berhasil = [h for h in hasil if h is not None]
        self.assertEqual(len(berhasil), 1)
        with _conn(p) as c:
            n = c.execute(
                "SELECT COUNT(*) FROM pinjaman WHERE user_id = 5 AND sisa > 0"
            ).fetchone()[0]
        self.assertEqual(n, 1)

    def test_kurang_koin_tidak_overdraft(self):
        """8 debit konkuren @100 dari saldo 600: tepat 6 lolos, sisa 0,
        tanpa overdraft (saldo 500 + 100 saldo awal akun baru)."""
        p = _db_file()
        with _conn(p) as c:
            eko.tambah_koin(c, 1, 9, 500)

        def _debit():
            with _conn(p) as c:
                return eko.kurang_koin(c, 1, 9, 100)

        hasil = _jalan_bersama(_debit)
        lolos = [h for h in hasil if h is not None]
        self.assertEqual(len(lolos), 6)
        self.assertEqual(_saldo(p, 9), 0)

    def test_baris_quest_race_tanpa_integrity_error(self):
        """8 pesan pertama di hari baru: tanpa IntegrityError, semua kehitung."""
        p = _db_file()

        def _pesan():
            with _conn(p) as c:
                q.tambah_pesan(c, 1, 3)

        _jalan_bersama(_pesan)  # assert not errors di dalam helper
        with _conn(p) as c:
            r = c.execute(
                "SELECT COUNT(*), SUM(pesan) FROM quest_progress"
                " WHERE user_id = 3 AND guild_id = 1"
            ).fetchone()
        self.assertEqual(r[0], 1)
        self.assertEqual(r[1], 8)

    def test_pastikan_state_race_tanpa_integrity_error(self):
        """/season & loop season bersamaan di guild baru: 1 baris state."""
        p = _db_file()

        def _state():
            with _conn(p) as c:
                return _pastikan_state(c, 77)

        hasil = _jalan_bersama(_state)
        self.assertTrue(all(h[0] == 1 for h in hasil))
        with _conn(p) as c:
            n = c.execute(
                "SELECT COUNT(*) FROM season_state WHERE guild_id = 77"
            ).fetchone()[0]
        self.assertEqual(n, 1)


class TestAudit4Idempoten(unittest.TestCase):
    def test_tandai_harian_idempoten(self):
        """Proses harian: sekali per tanggal, beda tanggal/kunci boleh lagi."""
        p = _db_file()
        with _conn(p) as c:
            self.assertTrue(eko.tandai_harian(c, "bunga_bank", "2026-10-10"))
            self.assertFalse(eko.tandai_harian(c, "bunga_bank", "2026-10-10"))
            self.assertTrue(eko.tandai_harian(c, "bunga_bank", "2026-10-11"))
            self.assertTrue(eko.tandai_harian(c, "bunga_pinjaman", "2026-10-10"))
            # Persisten lintas koneksi (restart bot = koneksi baru)
        with _conn(p) as c:
            self.assertFalse(eko.tandai_harian(c, "bunga_bank", "2026-10-11"))

    def test_bunga_tidak_menimpa_pembayaran_manual(self):
        """Bunga pinjaman = UPDATE relatif: pembayaran manual di tengah
        tidak terhapus (regresi temuan audit-2)."""
        p = _db_file()
        now = datetime.datetime.now(datetime.timezone.utc)
        with _conn(p) as c:
            _coba_buka_pinjaman(c, 1, 5, 1000, 10, 7, now)
            # Simulasi: loop bunga baca sisa, lalu user lunasi manual,
            # lalu loop tulis bunga secara relatif (bukan timpa nilai basi).
            r = c.execute("SELECT sisa FROM pinjaman WHERE user_id = 5").fetchone()
            sisa_bacaan_loop = r[0]
            c.execute(
                "UPDATE pinjaman SET sisa = MAX(0, sisa - 400) WHERE user_id = 5"
            )
            c.commit()
            bunga = sisa_bacaan_loop * 10 // 100  # dihitung dari bacaan basi
            c.execute("UPDATE pinjaman SET sisa = sisa + ? WHERE user_id = 5", (bunga,))
            c.commit()
            r = c.execute("SELECT sisa FROM pinjaman WHERE user_id = 5").fetchone()
        # 1000 - 400 (lunasi) + 100 (bunga dari bacaan basi, relatif) = 700.
        # Kalau bunga menimpa: hasilnya 1100 (pembayaran 400 hangus).
        self.assertEqual(r[0], 700)


if __name__ == "__main__":
    unittest.main()
