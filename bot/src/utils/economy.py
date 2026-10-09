"""Logika terpusat sistem koin (economy).

Semua fungsi terima `conn` (sqlite3) + `guild_id`/`user_id` — gampang di-unit-test.
Waktu disimpan sebagai ISO string; perbandingan cooldown pakai detik epoch.
"""

import datetime
import random

from src.utils.waktu import parse_iso

DAILY_COOLDOWN_DETIK = 24 * 3600


def get_akun(conn, guild_id: int, user_id: int) -> dict:
    """Ambil akun koin; buat baru dengan saldo awal kalau belum ada."""
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
    conn.execute(
        "INSERT INTO economy (user_id, guild_id, balance, total_earned)"
        " VALUES (?, ?, ?, ?)",
        (user_id, guild_id, mulai, mulai),
    )
    conn.commit()
    return {"balance": mulai, "total_earned": mulai, "last_daily": None,
            "last_work": None, "baru": True}


def tambah_koin(conn, guild_id: int, user_id: int, jumlah: int) -> int:
    """Tambah koin (jumlah > 0). Return saldo baru. total_earned ikut naik."""
    if jumlah <= 0:
        raise ValueError("jumlah harus positif")
    akun = get_akun(conn, guild_id, user_id)
    baru = akun["balance"] + jumlah
    total = akun["total_earned"] + jumlah
    conn.execute(
        "UPDATE economy SET balance = ?, total_earned = ?"
        " WHERE user_id = ? AND guild_id = ?",
        (baru, total, user_id, guild_id),
    )
    conn.commit()
    return baru


def kurang_koin(conn, guild_id: int, user_id: int, jumlah: int) -> int | None:
    """Kurangi koin. Return saldo baru, atau None kalau saldo tidak cukup."""
    if jumlah <= 0:
        raise ValueError("jumlah harus positif")
    akun = get_akun(conn, guild_id, user_id)
    if akun["balance"] < jumlah:
        return None
    baru = akun["balance"] - jumlah
    conn.execute(
        "UPDATE economy SET balance = ? WHERE user_id = ? AND guild_id = ?",
        (baru, user_id, guild_id),
    )
    conn.commit()
    return baru


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

    Return (status, nilai): 'ok' -> nilai = koin didapat;
    'cooldown' -> nilai = sisa detik sampai bisa klaim lagi.
    """
    rng = rng or random
    akun = get_akun(conn, guild_id, user_id)
    terakhir = parse_iso(akun[kolom])
    if terakhir is not None:
        sisa = cooldown_detik - int((sekarang - terakhir).total_seconds())
        if sisa > 0:
            return "cooldown", sisa
    jumlah = rng.randint(jumlah_min, jumlah_max)
    conn.execute(
        f"UPDATE economy SET balance = balance + ?, total_earned = total_earned + ?,"
        f" {kolom} = ? WHERE user_id = ? AND guild_id = ?",
        (jumlah, jumlah, sekarang.isoformat(), user_id, guild_id),
    )
    conn.commit()
    return "ok", jumlah


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
    from src.cogs.dashboard_sync import get_guild_setting, get_guild_setting_int

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
    akun = get_akun(conn, guild_id, user_id)
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
    """Kasih 1 reputasi. Return ('ok', rep_baru) atau ('cooldown', sisa_detik)."""
    get_akun(conn, guild_id, pemberi_id)
    get_akun(conn, guild_id, target_id)
    row = conn.execute(
        "SELECT last_rep FROM economy WHERE user_id = ? AND guild_id = ?",
        (pemberi_id, guild_id),
    ).fetchone()
    terakhir = parse_iso(row[0] if row else None)
    if terakhir is not None:
        sisa = REP_COOLDOWN_DETIK - int((sekarang - terakhir).total_seconds())
        if sisa > 0:
            return "cooldown", sisa
    conn.execute(
        "UPDATE economy SET rep = rep + 1 WHERE user_id = ? AND guild_id = ?",
        (target_id, guild_id),
    )
    conn.execute(
        "UPDATE economy SET last_rep = ? WHERE user_id = ? AND guild_id = ?",
        (sekarang.isoformat(), pemberi_id, guild_id),
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
