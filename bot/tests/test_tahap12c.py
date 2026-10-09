"""Tes Tahap 12c — fitur sosial (logika murni). Jalanin: python -m pytest tests/ -q"""
import sqlite3
import unittest

from src.cogs.sosial import GELAR_TOKO, LamaranView, CeraiView, gelar_nama
from src.utils import job as jobmod


def db_baru() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE job (user_id INTEGER NOT NULL, guild_id INTEGER NOT NULL,"
        " job_id TEXT NOT NULL, diambil TEXT NOT NULL, PRIMARY KEY (user_id, guild_id))"
    )
    conn.execute(
        "CREATE TABLE nikah (user_id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL,"
        " pasangan_id INTEGER NOT NULL, sejak TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE clan (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL,"
        " nama TEXT NOT NULL, ketua_id INTEGER NOT NULL, dibuat TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE clan_member (clan_id INTEGER NOT NULL, user_id INTEGER PRIMARY KEY,"
        " joined TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE gelar_milik (user_id INTEGER NOT NULL, guild_id INTEGER NOT NULL,"
        " gelar_id TEXT NOT NULL, PRIMARY KEY (user_id, guild_id, gelar_id))"
    )
    conn.execute(
        "CREATE TABLE gelar_aktif (user_id INTEGER NOT NULL, guild_id INTEGER NOT NULL,"
        " gelar_id TEXT NOT NULL, PRIMARY KEY (user_id, guild_id))"
    )
    conn.execute(
        "CREATE TABLE users (user_id INTEGER, guild_id INTEGER, level INTEGER, xp INTEGER,"
        " prestige INTEGER DEFAULT 0, PRIMARY KEY (user_id, guild_id))"
    )
    return conn


class TestJob(unittest.TestCase):
    def test_tiga_job_ada(self):
        self.assertEqual(set(jobmod.JOBS), {"pedagang", "petarung", "maling"})

    def test_set_get_bonus(self):
        conn = db_baru()
        self.assertIsNone(jobmod.get_job(conn, 10, 1))
        self.assertEqual(jobmod.bonus_untuk(conn, 10, 1), {})
        jobmod.set_job(conn, 10, 1, "petarung")
        self.assertEqual(jobmod.get_job(conn, 10, 1), "petarung")
        bonus = jobmod.bonus_untuk(conn, 10, 1)
        self.assertAlmostEqual(bonus["bonus_xp"], 0.15)
        # ganti job
        jobmod.set_job(conn, 10, 1, "pedagang")
        self.assertAlmostEqual(jobmod.bonus_untuk(conn, 10, 1)["bonus_kerja"], 0.15)
        conn.close()

    def test_bonus_maling(self):
        conn = db_baru()
        jobmod.set_job(conn, 10, 2, "maling")
        self.assertAlmostEqual(jobmod.bonus_untuk(conn, 10, 2)["bonus_maling"], 0.10)
        conn.close()


class TestNikah(unittest.TestCase):
    def test_dua_baris_dan_pasangan(self):
        conn = db_baru()
        conn.execute("INSERT INTO nikah VALUES (1, 10, 2, 'x')")
        conn.execute("INSERT INTO nikah VALUES (2, 10, 1, 'x')")
        conn.commit()
        a = conn.execute("SELECT pasangan_id FROM nikah WHERE user_id = 1").fetchone()[0]
        b = conn.execute("SELECT pasangan_id FROM nikah WHERE user_id = 2").fetchone()[0]
        self.assertEqual((a, b), (2, 1))
        # cerai hapus dua-duanya
        conn.execute("DELETE FROM nikah WHERE user_id IN (1, 2)")
        conn.commit()
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM nikah").fetchone()[0], 0)
        conn.close()

    def test_view_instansiasi(self):
        v = LamaranView(1, 2, 10)
        self.assertEqual(len(v.children), 2)
        c = CeraiView(1, 2)
        self.assertEqual(len(c.children), 1)


class TestClan(unittest.TestCase):
    def test_buat_gabung_keluar(self):
        conn = db_baru()
        cur = conn.execute(
            "INSERT INTO clan (guild_id, nama, ketua_id, dibuat) VALUES (10, 'Garuda', 1, 'x')"
        )
        cid = cur.lastrowid
        conn.execute("INSERT INTO clan_member VALUES (?, 1, 'x')", (cid,))
        conn.execute("INSERT INTO clan_member VALUES (?, 2, 'y')", (cid,))
        conn.commit()
        jumlah = conn.execute("SELECT COUNT(*) FROM clan_member WHERE clan_id = ?", (cid,)).fetchone()[0]
        self.assertEqual(jumlah, 2)
        # ketua keluar -> ketua pindah ke anggota tertua
        conn.execute("DELETE FROM clan_member WHERE clan_id = ? AND user_id = 1", (cid,))
        sisa = conn.execute(
            "SELECT user_id FROM clan_member WHERE clan_id = ? ORDER BY joined ASC LIMIT 1", (cid,)
        ).fetchone()
        conn.execute("UPDATE clan SET ketua_id = ? WHERE id = ?", (sisa[0], cid))
        conn.commit()
        ketua = conn.execute("SELECT ketua_id FROM clan WHERE id = ?", (cid,)).fetchone()[0]
        self.assertEqual(ketua, 2)
        conn.close()

    def test_nama_unik_per_guild(self):
        conn = db_baru()
        conn.execute("INSERT INTO clan (guild_id, nama, ketua_id, dibuat) VALUES (10, 'Garuda', 1, 'x')")
        conn.commit()
        dupe = conn.execute(
            "SELECT id FROM clan WHERE guild_id = 10 AND nama = 'Garuda'"
        ).fetchone()
        self.assertIsNotNone(dupe)
        beda = conn.execute(
            "SELECT id FROM clan WHERE guild_id = 99 AND nama = 'Garuda'"
        ).fetchone()
        self.assertIsNone(beda)
        conn.close()

    def test_skor_war(self):
        conn = db_baru()
        conn.execute("INSERT INTO clan (guild_id, nama, ketua_id, dibuat) VALUES (10, 'A', 1, 'x')")
        conn.execute("INSERT INTO clan (guild_id, nama, ketua_id, dibuat) VALUES (10, 'B', 3, 'x')")
        conn.execute("INSERT INTO clan_member VALUES (1, 1, 'x')")
        conn.execute("INSERT INTO clan_member VALUES (1, 2, 'x')")
        conn.execute("INSERT INTO clan_member VALUES (2, 3, 'x')")
        conn.execute("INSERT INTO users VALUES (1, 10, 20, 0, 0)")
        conn.execute("INSERT INTO users VALUES (2, 10, 5, 0, 0)")
        conn.execute("INSERT INTO users VALUES (3, 10, 30, 0, 0)")
        conn.commit()
        skor = {}
        for cid in (1, 2):
            total = conn.execute(
                "SELECT COALESCE(SUM(u.level), 0) FROM users u "
                "JOIN clan_member m ON m.user_id = u.user_id AND u.guild_id = 10 "
                "WHERE m.clan_id = ?", (cid,)
            ).fetchone()[0]
            skor[cid] = total
        self.assertEqual(skor, {1: 25, 2: 30})
        conn.close()


class TestGelar(unittest.TestCase):
    def test_toko_isi(self):
        self.assertEqual(GELAR_TOKO["sultan"]["harga"], 5000)
        self.assertEqual(GELAR_TOKO["legenda"]["harga"], 10000)
        self.assertEqual(GELAR_TOKO["kraz"]["harga"], 20000)

    def test_beli_pasang_nama(self):
        conn = db_baru()
        self.assertIsNone(gelar_nama(conn, 10, 1))
        conn.execute("INSERT INTO gelar_milik VALUES (1, 10, 'sultan')")
        conn.commit()
        # pasang butuh milik
        conn.execute(
            "INSERT INTO gelar_aktif VALUES (1, 10, 'sultan') "
            "ON CONFLICT(user_id, guild_id) DO UPDATE SET gelar_id = excluded.gelar_id"
        )
        conn.commit()
        self.assertEqual(gelar_nama(conn, 10, 1), "🌟 Sultan")
        conn.close()


class TestTopPrestige(unittest.TestCase):
    def test_urutan(self):
        conn = db_baru()
        conn.execute("INSERT INTO users VALUES (1, 10, 5, 0, 2)")
        conn.execute("INSERT INTO users VALUES (2, 10, 40, 0, 0)")
        conn.execute("INSERT INTO users VALUES (3, 10, 10, 0, 5)")
        rows = conn.execute(
            "SELECT user_id FROM users WHERE guild_id = 10 AND COALESCE(prestige, 0) > 0 "
            "ORDER BY prestige DESC, level DESC LIMIT 10"
        ).fetchall()
        self.assertEqual([r[0] for r in rows], [3, 1])
        conn.close()


if __name__ == "__main__":
    unittest.main()
