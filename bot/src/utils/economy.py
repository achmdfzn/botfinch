"""Logika terpusat sistem koin (economy).

Semua fungsi terima `conn` (sqlite3) + `guild_id`/`user_id` — gampang di-unit-test.
Waktu disimpan sebagai ISO string; perbandingan cooldown pakai detik epoch.
"""

import datetime
import random
import re

from src.utils.waktu import parse_iso

DAILY_COOLDOWN_DETIK = 24 * 3600

# Nama kolom tidak bisa di-parameterize di SQLite -> validasi ketat.
# Semua pemanggil memakai literal internal; ini pencegah bila suatu saat
# ada input luar yang lolos ke helper ini.
_KOLOM_AMAN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def get_akun(conn, guild_id: int, user_id: int) -> dict:
    """Ambil akun koin; buat baru dengan saldo awal kalau belum ada.

    INSERT OR IGNORE: dua pemanggilan konkuren untuk user baru tidak
    IntegrityError — hanya satu yang benar-benar membuat baris.
    """
    from src import config

    row = conn.execute(
        "SELECT balance, total_earned, last_daily, last_work FROM economy"
        " WHERE user_id = ? AND guild_id = ?",
        (user_id, guild_id),
    ).fetchone()
    if row:
        return {
            "balance": row[0],
            "total_earned": row[1],
            "last_daily": row[2],
            "last_work": row[3],
            "baru": False,
        }
    mulai = max(0, config.settings.economy_start_balance)
    cur = conn.execute(
        "INSERT OR IGNORE INTO economy (user_id, guild_id, balance, total_earned)"
        " VALUES (?, ?, ?, ?)",
        (user_id, guild_id, mulai, mulai),
    )
    conn.commit()
    if cur.rowcount == 0:
        # Kalah balapan pembuatan akun: baca baris milik pemenang.
        row = conn.execute(
            "SELECT balance, total_earned, last_daily, last_work FROM economy"
            " WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id),
        ).fetchone()
        return {
            "balance": row[0],
            "total_earned": row[1],
            "last_daily": row[2],
            "last_work": row[3],
            "baru": False,
        }
    return {"balance": mulai, "total_earned": mulai, "last_daily": None,
            "last_work": None, "baru": True}


def tambah_koin(conn, guild_id: int, user_id: int, jumlah: int) -> int:
    """Tambah koin (jumlah > 0). Return saldo baru. total_earned ikut naik.

    Atomik: UPDATE relatif (balance = balance + ?) — dua pemanggilan
    konkuren tidak saling menimpa (dulu: baca saldo lalu SET nilai
    hitungan, salah satu penambahan hilang).
    """
    if jumlah <= 0:
        raise ValueError("jumlah harus positif")
    get_akun(conn, guild_id, user_id)  # pastikan baris ada
    conn.execute(
        "UPDATE economy SET balance = balance + ?, total_earned = total_earned + ?"
        " WHERE user_id = ? AND guild_id = ?",
        (jumlah, jumlah, user_id, guild_id),
    )
    conn.commit()
    row = conn.execute(
        "SELECT balance FROM economy WHERE user_id = ? AND guild_id = ?",
        (user_id, guild_id),
    ).fetchone()
    return row[0] if row else 0


def kurang_koin(conn, guild_id: int, user_id: int, jumlah: int) -> int | None:
    """Kurangi koin. Return saldo baru, atau None kalau saldo tidak cukup.

    Atomik: cek saldo & kurangi dalam SATU statement UPDATE kondisional,
    sehingga dua pemanggilan konkuren tidak bisa overdraft (dulu: baca saldo
    dulu lalu UPDATE — dua panggilan bersamaan bisa sama-sama lolos cek).
    """
    if jumlah <= 0:
        raise ValueError("jumlah harus positif")
    get_akun(conn, guild_id, user_id)  # pastikan baris ada
    cur = conn.execute(
        "UPDATE economy SET balance = balance - ?"
        " WHERE user_id = ? AND guild_id = ? AND balance >= ?",
        (jumlah, user_id, guild_id, jumlah),
    )
    if cur.rowcount == 0:
        return None
    conn.commit()
    row = conn.execute(
        "SELECT balance FROM economy WHERE user_id = ? AND guild_id = ?",
        (user_id, guild_id),
    ).fetchone()
    return row[0] if row else None


def _klaim_cooldown(
    conn,
    guild_id: int,
    user_id: int,
    kolom: str,
    cooldown_detik: int,
    jumlah_min: int,
    jumlah_max: int,
    sekarang: datetime.datetime,
    rng=None,
) -> tuple[str, int]:
    """Helper generik klaim ber-cooldown.

    Atomik: cek cooldown & kredit dalam SATU statement UPDATE kondisional.
    Dua panggilan konkuren (mis. double-click /daily) tidak bisa sama-sama
    lolos — hanya satu yang rowcount-nya 1 (dulu: SELECT cek dulu lalu UPDATE,
    keduanya bisa lolos sebelum salah satunya commit).

    Return (status, nilai): 'ok' -> nilai = koin didapat;
    'cooldown' -> nilai = sisa detik sampai bisa klaim lagi.
    """
    if not _KOLOM_AMAN.match(kolom):
        raise ValueError(f"Nama kolom tidak valid: {kolom!r}")
    rng = rng or random
    get_akun(conn, guild_id, user_id)  # pastikan baris ada
    jumlah = rng.randint(jumlah_min, jumlah_max)
    # Batas waktu dalam ISO: klaim lama yang lebih tua dari ini sudah kedaluwarsa.
    # Format ISO konsisten (aware UTC) sehingga perbandingan leksikografis = kronologis.
    batas = (sekarang - datetime.timedelta(seconds=cooldown_detik)).isoformat()
    cur = conn.execute(
        f"UPDATE economy SET balance = balance + ?, total_earned = total_earned + ?,"
        f" {kolom} = ? WHERE user_id = ? AND guild_id = ?"
        f" AND ({kolom} IS NULL OR {kolom} <= ?)",
        (jumlah, jumlah, sekarang.isoformat(), user_id, guild_id, batas),
    )
    if cur.rowcount > 0:
        conn.commit()
        return "ok", jumlah
    # Gagal update = masih cooldown (klaim lain menang race). Baca ulang
    # timestamp TERBARU untuk hitung sisa (bacaan awal bisa basi).
    row = conn.execute(
        f"SELECT {kolom} FROM economy WHERE user_id = ? AND guild_id = ?",
        (user_id, guild_id),
    ).fetchone()
    terakhir = parse_iso(row[0] if row else None)
    if terakhir is not None:
        sisa = cooldown_detik - int((sekarang - terakhir).total_seconds())
        if sisa > 0:
            return "cooldown", sisa
    return "cooldown", 0


def klaim_daily(conn, guild_id: int, user_id: int,
                sekarang: datetime.datetime | None = None, rng=None) -> tuple[str, int]:
    """Klaim hadiah harian (cooldown 24 jam)."""
    from src import config
    from src.cogs.dashboard_sync import get_guild_setting

    sekarang = sekarang or datetime.datetime.now(datetime.timezone.utc)
    # Override per-server via dashboard: nominal tetap (bukan acak)
    tetap = (get_guild_setting(guild_id, "economy_daily", "") or "").strip()
    if tetap:
        try:
            nominal = max(0, int(tetap))
        except ValueError:
            nominal = None
        if nominal is not None:
            return _klaim_cooldown(
                conn, guild_id, user_id, "last_daily", DAILY_COOLDOWN_DETIK,
                nominal, nominal, sekarang, rng,
            )
    return _klaim_cooldown(
        conn, guild_id, user_id, "last_daily", DAILY_COOLDOWN_DETIK,
        config.settings.economy_daily_min, config.settings.economy_daily_max,
        sekarang, rng,
    )


def kerja(conn, guild_id: int, user_id: int,
          sekarang: datetime.datetime | None = None, rng=None) -> tuple[str, int]:
    """Kerja untuk dapat koin (cooldown dari config)."""
    from src import config
    from src.cogs.dashboard_sync import get_guild_setting_int

    sekarang = sekarang or datetime.datetime.now(datetime.timezone.utc)
    wmin = get_guild_setting_int(guild_id, "economy_work_min", config.settings.economy_work_min)
    wmax = get_guild_setting_int(guild_id, "economy_work_max", config.settings.economy_work_max)
    wmin, wmax = max(0, wmin), max(0, wmax)
    if wmin > wmax:
        wmin, wmax = wmax, wmin
    return _klaim_cooldown(
        conn, guild_id, user_id, "last_work",
        max(0, config.settings.economy_work_cooldown),
        wmin, wmax,
        sekarang, rng,
    )


def peringkat(conn, guild_id: int, user_id: int) -> int:
    """Peringkat saldo user di server (1 = terkaya)."""
    akun = get_akun(conn, guild_id, user_id)
    row = conn.execute(
        "SELECT COUNT(*) FROM economy WHERE guild_id = ? AND balance > ?",
        (guild_id, akun["balance"]),
    ).fetchone()
    return (row[0] if row else 0) + 1


def top_koin(conn, guild_id: int, limit: int = 10) -> list[tuple[int, int]]:
    """Top saldo: list (user_id, balance), terkaya dulu."""
    return [
        (r[0], r[1])
        for r in conn.execute(
            "SELECT user_id, balance FROM economy WHERE guild_id = ?"
            " ORDER BY balance DESC, user_id ASC LIMIT ?",
            (guild_id, limit),
        ).fetchall()
    ]


REP_COOLDOWN_DETIK = 24 * 3600


def get_rep(conn, guild_id: int, user_id: int) -> int:
    """Jumlah reputasi user."""
    row = conn.execute(
        "SELECT rep FROM economy WHERE user_id = ? AND guild_id = ?",
        (user_id, guild_id),
    ).fetchone()
    return row[0] if row and row[0] else 0


def beri_rep(
    conn,
    guild_id: int,
    pemberi_id: int,
    target_id: int,
    sekarang: datetime.datetime,
) -> tuple[str, int]:
    """Kasih 1 reputasi. Return ('ok', rep_baru) atau ('cooldown', sisa_detik).

    Atomik: klaim slot cooldown via UPDATE kondisional — dua /rep konkuren
    dari pemberi yang sama tidak bisa memberi 2 rep sekaligus.
    """
    get_akun(conn, guild_id, pemberi_id)
    get_akun(conn, guild_id, target_id)
    batas = (sekarang - datetime.timedelta(seconds=REP_COOLDOWN_DETIK)).isoformat()
    cur = conn.execute(
        "UPDATE economy SET last_rep = ? WHERE user_id = ? AND guild_id = ?"
        " AND (last_rep IS NULL OR last_rep <= ?)",
        (sekarang.isoformat(), pemberi_id, guild_id, batas),
    )
    if cur.rowcount == 0:
        row = conn.execute(
            "SELECT last_rep FROM economy WHERE user_id = ? AND guild_id = ?",
            (pemberi_id, guild_id),
        ).fetchone()
        terakhir = parse_iso(row[0] if row else None)
        if terakhir is not None:
            sisa = REP_COOLDOWN_DETIK - int((sekarang - terakhir).total_seconds())
            if sisa > 0:
                return "cooldown", sisa
        return "cooldown", 0
    conn.execute(
        "UPDATE economy SET rep = rep + 1 WHERE user_id = ? AND guild_id = ?",
        (target_id, guild_id),
    )
    conn.commit()
    return "ok", get_rep(conn, guild_id, target_id)


def bisa_trivia(
    conn, guild_id: int, user_id: int, sekarang: datetime.datetime, cooldown_detik: int
) -> tuple[bool, int]:
    """Cek cooldown trivia. Return (boleh_main, sisa_detik)."""
    get_akun(conn, guild_id, user_id)
    row = conn.execute(
        "SELECT last_trivia FROM economy WHERE user_id = ? AND guild_id = ?",
        (user_id, guild_id),
    ).fetchone()
    terakhir = parse_iso(row[0] if row else None)
    if terakhir is not None:
        sisa = cooldown_detik - int((sekarang - terakhir).total_seconds())
        if sisa > 0:
            return False, sisa
    return True, 0


def catat_trivia(conn, guild_id: int, user_id: int, sekarang: datetime.datetime) -> None:
    """Tandai trivia dimainkan (mulai cooldown)."""
    get_akun(conn, guild_id, user_id)
    conn.execute(
        "UPDATE economy SET last_trivia = ? WHERE user_id = ? AND guild_id = ?",
        (sekarang.isoformat(), user_id, guild_id),
    )
    conn.commit()


def format_sisa_waktu(detik: int) -> str:
    """Detik -> '3 jam 12 menit' (untuk pesan cooldown)."""
    detik = max(0, int(detik))
    jam, sisa = divmod(detik, 3600)
    menit, _ = divmod(sisa, 60)
    bagian = []
    if jam:
        bagian.append(f"{jam} jam")
    if menit or not bagian:
        bagian.append(f"{menit} menit")
    return " ".join(bagian)
