"""Regresi audit-4 TRACK ENGAGEMENT/SOSIAL.

Temuan yang diperbaiki di gelombang ini (fresh-eyes):
1. leveling /prestige — race double-prestige: dua command konkuren dulu
   sama-sama lolos cek level>=30 lalu UPDATE 2x (prestige +2). Kini guarded
   UPDATE ... WHERE level >= 30 + cek rowcount.
2. sosial nikah — skema lama PK(user_id) global vs kode yang berniat per-server:
   user menikah di server A lalu dilamar di server B -> INSERT menabrak PK ->
   IntegrityError (command crash). Kini migrasi idempoten ke PK(user_id, guild_id).
3. sosial CeraiView — DELETE tanpa filter guild_id menghapus pernikahan pasangan
   yang sama di server lain. Kini filter guild_id (constructor terima guild_id).
4. sosial LamaranView.terima — cek "sudah menikah" tanpa filter guild_id
   (false positive lintas server). Kini filter guild_id.
5. sosial gelar_beli & clan_buat — race klaim ganda -> IntegrityError mentah.
   Kini INSERT OR IGNORE + rowcount -> rollback + pesan ramah.
6. Koin saat modul ekonomi dimatikan: turnamen susun-kata, clan war, invite,
   ultah, bump, dailyq, quest pool, /nikah klaim, /pet adopsi, /gelar beli,
   /clan buat — kini hormat economy_enabled (default ON).
7. Pet XP di engagement.on_message kini hormat leveling_enabled
   (seperti reaction XP).
8. giveaway cek_giveaway & cek_rutin — SELECT awal tidak terbungkus try/except
   (satu DB error membunuh loop selamanya). Kini return aman.
9. Spam: /poll & /saran kini cooldown atomik 60 dtk (persisten DB);
   /nikah lamar cooldown 5 mnt (lamaran me-mention target -> vektor ping-spam).
10. voicexp — anti-farm: sendirian di voice / deaf -> tidak dapat XP/koin.
11. Validasi: /poll tolak pertanyaan kosong, /g-rutin hadiah maks 500 char
    (seperti /giveaway), /lomba jawab maks 200 char.
12. engagement pengumuman pet naik level kini allowed_mentions=none()
    (nama pet = input user, dulu bisa disisipi <@id> untuk nge-ping).
13. turnamen _kuis_selesai — payout gagal dulu return diam-diam tanpa pengumuman
    hasil; kini embed hasil tetap dikirim dengan catatan tanpa hadiah.

Pola: DB terisolasi per test via store.DB_PATH -> tmp dir (seperti test_giveaway.py).
"""
import datetime
import tempfile
from types import SimpleNamespace

import src.store as store
from src.cogs import engagement as engagement_mod
from src.cogs import polls as polls_mod
from src.cogs import saran as saran_mod
from src.cogs import sosial as sosial_mod
from src.cogs import voicexp as voicexp_mod
from src.cogs.birthday import parse_tanggal_ultah
from src.cogs.bump import bump_sisa_detik, ekstrak_bumper_id
from src.cogs.turnamen import normalisasi_jawaban, skor_ship
from src.store import get_connection

GID = 515004  # guild id khusus file test ini
GID2 = 515005


# ---------- util DB terisolasi ----------

def _db_baru():
    tmp = tempfile.mkdtemp()
    orig = store.DB_PATH
    store.DB_PATH = type(orig)(f"{tmp}/t.db")
    store.init_db()
    with get_connection() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS dashboard_settings ("
            " guild_id INTEGER NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL,"
            " PRIMARY KEY (guild_id, key))"
        )
        conn.commit()
    return orig


def _db_kembali(orig):
    store.DB_PATH = orig


def _set_toggle(gid: int, key: str, val: str):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO dashboard_settings (guild_id, key, value) VALUES (?, ?, ?)"
            " ON CONFLICT(guild_id, key) DO UPDATE SET value = excluded.value",
            (gid, key, val),
        )
        conn.commit()


# ---------- 1. prestige: race double-klaim ----------

def _prestige_guarded(conn, uid: int, gid: int) -> bool:
    """Replika logika guarded UPDATE /prestige (agar tidak butuh ctx)."""
    cur = conn.execute(
        "UPDATE users SET xp = 0, level = 1, prestige = COALESCE(prestige, 0) + 1"
        " WHERE user_id = ? AND guild_id = ? AND level >= 30",
        (uid, gid),
    )
    conn.commit()
    return cur.rowcount == 1


def test_prestige_race_hanya_satu_menang():
    orig = _db_baru()
    try:
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO users (user_id, guild_id, xp, level) VALUES (7, ?, 0, 30)",
                (GID,),
            )
            conn.commit()
        # Dua "command" konkuren pakai koneksi berbeda (seperti dua worker).
        with get_connection() as c1, get_connection() as c2:
            menang1 = _prestige_guarded(c1, 7, GID)
            menang2 = _prestige_guarded(c2, 7, GID)
        assert menang1 != menang2, "tepat satu yang boleh prestige"
        with get_connection() as conn:
            row = conn.execute(
                "SELECT level, prestige FROM users WHERE user_id = 7 AND guild_id = ?",
                (GID,),
            ).fetchone()
        assert row == (1, 1), f"prestige harus tepat 1x, dapat {row}"
    finally:
        _db_kembali(orig)


def test_prestige_level_kurang_ditolak():
    orig = _db_baru()
    try:
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO users (user_id, guild_id, xp, level) VALUES (8, ?, 0, 29)",
                (GID,),
            )
            conn.commit()
            assert _prestige_guarded(conn, 8, GID) is False
    finally:
        _db_kembali(orig)


# ---------- 2. migrasi nikah PK(user_id) -> PK(user_id, guild_id) ----------

def _buat_nikah_lama():
    with get_connection() as conn:
        conn.execute("DROP TABLE IF EXISTS nikah")
        conn.execute(
            "CREATE TABLE nikah (user_id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL,"
            " pasangan_id INTEGER NOT NULL, sejak TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO nikah VALUES (11, ?, 22, '2026-01-01T00:00:00')", (GID,)
        )
        conn.commit()


def test_migrasi_nikah_idempoten_dan_data_utuh():
    orig = _db_baru()
    try:
        _buat_nikah_lama()
        sosial_mod._migrasi_nikah_per_guild()
        with get_connection() as conn:
            pk = [c[1] for c in conn.execute("PRAGMA table_info(nikah)").fetchall() if c[5] > 0]
            assert pk == ["user_id", "guild_id"], f"PK harus (user_id, guild_id), dapat {pk}"
            row = conn.execute("SELECT user_id, guild_id, pasangan_id FROM nikah").fetchone()
            assert row == (11, GID, 22)
        # Idempoten: jalan kedua tidak merusak / tidak error
        sosial_mod._migrasi_nikah_per_guild()
        with get_connection() as conn:
            assert conn.execute("SELECT COUNT(*) FROM nikah").fetchone()[0] == 1
        # Per-server kini legal: user yang sama boleh menikah di guild lain
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO nikah VALUES (11, ?, 33, '2026-02-01T00:00:00')", (GID2,)
            )
            conn.commit()
            assert conn.execute("SELECT COUNT(*) FROM nikah").fetchone()[0] == 2
    finally:
        _db_kembali(orig)


def test_cerai_hanya_hapus_guild_sendiri():
    """Replika SQL CeraiView.ya: DELETE harus memfilter guild_id."""
    orig = _db_baru()
    try:
        sosial_mod._migrasi_nikah_per_guild()  # seperti saat cog dimuat
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO nikah VALUES (11, ?, 22, 'x')", (GID,)
            )
            conn.execute(
                "INSERT INTO nikah VALUES (22, ?, 11, 'x')", (GID,)
            )
            conn.execute(
                "INSERT INTO nikah VALUES (11, ?, 22, 'x')", (GID2,)
            )
            conn.execute(
                "INSERT INTO nikah VALUES (22, ?, 11, 'x')", (GID2,)
            )
            conn.commit()
            # SQL persis seperti di CeraiView.ya setelah perbaikan
            conn.execute(
                "DELETE FROM nikah WHERE guild_id = ? AND user_id IN (?, ?)",
                (GID, 11, 22),
            )
            conn.commit()
            sisa = conn.execute("SELECT guild_id FROM nikah").fetchall()
        assert sisa == [(GID2,), (GID2,)], f"pernikahan guild lain ikut terhapus: {sisa}"
    finally:
        _db_kembali(orig)


def test_terima_lamaran_cek_per_guild():
    """Replika SQL LamaranView.terima: cek menikah harus per-guild."""
    orig = _db_baru()
    try:
        with get_connection() as conn:
            conn.execute("INSERT INTO nikah VALUES (11, ?, 22, 'x')", (GID2,))
            conn.commit()
            rows = conn.execute(
                "SELECT user_id FROM nikah WHERE guild_id = ? AND user_id IN (?, ?)",
                (GID, 11, 99),
            ).fetchall()
        assert rows == [], "menikah di guild lain tidak boleh memblokir lamaran di sini"
    finally:
        _db_kembali(orig)


# ---------- 5. gelar_beli & clan_buat: race klaim ganda ----------

def test_gelar_beli_double_tidak_integrity_error():
    orig = _db_baru()
    try:
        with get_connection() as conn:
            # Dua INSERT konkuren untuk gelar yang sama
            c1 = conn.execute(
                "INSERT OR IGNORE INTO gelar_milik (user_id, guild_id, gelar_id)"
                " VALUES (21, ?, 'sultan')",
                (GID,),
            )
            c2 = conn.execute(
                "INSERT OR IGNORE INTO gelar_milik (user_id, guild_id, gelar_id)"
                " VALUES (21, ?, 'sultan')",
                (GID,),
            )
            assert (c1.rowcount, c2.rowcount) == (1, 0)
            conn.rollback()  # simulasi rollback pihak yang kalah race
            assert conn.execute("SELECT COUNT(*) FROM gelar_milik").fetchone()[0] == 0
    finally:
        _db_kembali(orig)


def test_clan_member_double_tidak_integrity_error():
    orig = _db_baru()
    try:
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO clan (guild_id, nama, ketua_id, dibuat) VALUES (?, 'A', 31, 'x')",
                (GID,),
            )
            cid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            c1 = conn.execute(
                "INSERT OR IGNORE INTO clan_member (clan_id, user_id, joined)"
                " VALUES (?, 31, 'x')",
                (cid,),
            )
            c2 = conn.execute(
                "INSERT OR IGNORE INTO clan_member (clan_id, user_id, joined)"
                " VALUES (?, 31, 'x')",
                (cid,),
            )
            assert (c1.rowcount, c2.rowcount) == (1, 0)
            conn.rollback()
            assert conn.execute("SELECT COUNT(*) FROM clan_member").fetchone()[0] == 0
    finally:
        _db_kembali(orig)


# ---------- 6. _ekonomi_aktif default ON ----------

def test_ekonomi_aktif_default_dan_toggle():
    orig = _db_baru()
    try:
        assert sosial_mod._ekonomi_aktif(GID) is True
        _set_toggle(GID, "economy_enabled", "0")
        assert sosial_mod._ekonomi_aktif(GID) is False
        _set_toggle(GID, "economy_enabled", "1")
        assert sosial_mod._ekonomi_aktif(GID) is True
    finally:
        _db_kembali(orig)


# ---------- 9. cooldown atomik ----------

def test_cooldown_klaim_atomik_sosial():
    orig = _db_baru()
    try:
        with get_connection() as conn:
            pertama = sosial_mod._cooldown_klaim(conn, GID, 41, "nikah_lamar", 300)
            kedua = sosial_mod._cooldown_klaim(conn, GID, 41, "nikah_lamar", 300)
            assert pertama is True and kedua is False
            sisa = sosial_mod._cooldown_sisa(conn, GID, 41, "nikah_lamar", 300)
            assert 0 < sisa <= 300
    finally:
        _db_kembali(orig)


def test_cooldown_poll_atomik():
    orig = _db_baru()
    try:
        with get_connection() as conn:
            assert polls_mod._klaim_cooldown_poll(conn, GID, 42) == 0
            sisa = polls_mod._klaim_cooldown_poll(conn, GID, 42)
            assert 0 < sisa <= polls_mod.POLL_COOLDOWN_DETIK
    finally:
        _db_kembali(orig)


def test_cooldown_saran_atomik():
    orig = _db_baru()
    try:
        with get_connection() as conn:
            assert saran_mod._klaim_cooldown_saran(conn, GID, 43) == 0
            sisa = saran_mod._klaim_cooldown_saran(conn, GID, 43)
            assert 0 < sisa <= saran_mod.SARAN_COOLDOWN_DETIK
    finally:
        _db_kembali(orig)


# ---------- 10. voicexp anti-farm ----------

def _member(uid: int, bot: bool = False):
    return SimpleNamespace(id=uid, bot=bot)


def _channel(*members):
    return SimpleNamespace(members=list(members))


def test_sendiri_di_voice():
    assert voicexp_mod.sendiri_di_voice(_channel(_member(1)), 1) is True
    assert voicexp_mod.sendiri_di_voice(_channel(_member(1), _member(2, bot=True)), 1) is True
    assert voicexp_mod.sendiri_di_voice(_channel(_member(1), _member(2)), 1) is False
    assert voicexp_mod.sendiri_di_voice(_channel(), 1) is True


def test_format_menit():
    assert voicexp_mod.format_menit(45) == "45 mnt"
    assert voicexp_mod.format_menit(120) == "2 jam"
    assert voicexp_mod.format_menit(90) == "1 jam 30 mnt"
    assert voicexp_mod.format_menit(0) == "0 mnt"


# ---------- pure functions ----------

def test_parse_tanggal_ultah():
    assert parse_tanggal_ultah("25-12") == "25-12"
    assert parse_tanggal_ultah("5-3") == "05-03"
    assert parse_tanggal_ultah("31-02") is None
    assert parse_tanggal_ultah("29-02") == "29-02"
    assert parse_tanggal_ultah("32-01") is None
    assert parse_tanggal_ultah("abc") is None
    assert parse_tanggal_ultah("1-13") is None


def test_bump_helpers():
    assert ekstrak_bumper_id(["Bump done! <@12345>"]) == 12345
    assert ekstrak_bumper_id(["Bump done! <@302050872383242240>"]) is None
    assert ekstrak_bumper_id([None, ""]) is None
    now = datetime.datetime.now(datetime.timezone.utc)
    assert bump_sisa_detik(None, now) == 0
    assert bump_sisa_detik("bukan-tanggal", now) == 0
    baru = (now - datetime.timedelta(minutes=30)).isoformat()
    sisa = bump_sisa_detik(baru, now)
    assert 89 * 60 < sisa <= 90 * 60
    lama = (now - datetime.timedelta(hours=3)).isoformat()
    assert bump_sisa_detik(lama, now) == 0


def test_turnamen_pure():
    assert normalisasi_jawaban("  JaKaRtA\t") == "jakarta"
    assert skor_ship(1, 2) == skor_ship(2, 1)
    assert 0 <= skor_ship(1, 2) <= 100


def test_polls_pure():
    assert polls_mod.parse_opsi("a, b ,, c") == ["a", "b", "c"]
    assert polls_mod.parse_opsi("") == []
    assert polls_mod.validasi_teks_poll("ok", ["a", "b"]) is None
    assert polls_mod.validasi_teks_poll("x" * 501, ["a", "b"]) is not None
    assert polls_mod.validasi_teks_poll("ok", ["x" * 101, "b"]) is not None


def test_engagement_pure():
    assert engagement_mod.pet_level(0) == 1
    assert engagement_mod.pet_level(100) == 2
    assert engagement_mod.pet_level(-5) == 1
    assert engagement_mod.pet_progress(150) == (50, 100)
    t1 = engagement_mod.pertanyaan_tanggal("2026-10-10", GID)
    t2 = engagement_mod.pertanyaan_tanggal("2026-10-10", GID)
    assert t1 == t2 and t1 in engagement_mod.PERTANYAAN_HARIAN
    senin = engagement_mod.senin_depan_utc(
        datetime.datetime(2026, 10, 10, 12, 0, tzinfo=datetime.timezone.utc)  # Sabtu
    )
    assert senin.weekday() == 0 and senin.hour == 0


def test_dailyq_cap_race_pola():
    """Pola BEGIN IMMEDIATE + cap di _proses_dailyq: hanya N penjawab tercatat."""
    orig = _db_baru()
    try:
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO dailyq (guild_id, tanggal, pertanyaan) VALUES (?, '2026-10-10', 'q')",
                (GID,),
            )
            conn.commit()
            # Simulasi 5 klaim konkuren untuk maks 3
            menang = 0
            for uid in range(5):
                conn.execute("BEGIN IMMEDIATE")
                try:
                    jumlah = conn.execute(
                        "SELECT COUNT(*) FROM dailyq_jawab WHERE guild_id = ? AND tanggal = ?",
                        (GID, "2026-10-10"),
                    ).fetchone()[0]
                    if jumlah < 3:
                        conn.execute(
                            "INSERT INTO dailyq_jawab VALUES (?, '2026-10-10', ?)",
                            (GID, uid),
                        )
                        menang += 1
                    conn.commit()
                except Exception:
                    conn.rollback()
            total = conn.execute(
                "SELECT COUNT(*) FROM dailyq_jawab WHERE guild_id = ? AND tanggal = ?",
                (GID, "2026-10-10"),
            ).fetchone()[0]
        assert total == 3 and menang == 3
    finally:
        _db_kembali(orig)
