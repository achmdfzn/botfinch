"""Job/class system — dipakai lintas cog (leveling, economy, minigames).

Pemain pilih 1 job via /job-pilih; bonus dibaca via bonus_untuk().
"""
import datetime

JOBS = {
    "pedagang": {
        "nama": "💰 Pedagang",
        "deskripsi": "+15% koin dari /kerja",
        "bonus_kerja": 0.15,
    },
    "petarung": {
        "nama": "⚔️ Petarung",
        "deskripsi": "+15% XP dari chat",
        "bonus_xp": 0.15,
    },
    "maling": {
        "nama": "🥷 Maling",
        "deskripsi": "+10% peluang /game maling berhasil",
        "bonus_maling": 0.10,
    },
}


def get_job(conn, guild_id: int, user_id: int) -> str | None:
    """Return job_id aktif atau None."""
    row = conn.execute(
        "SELECT job_id FROM job WHERE user_id = ? AND guild_id = ?",
        (user_id, guild_id),
    ).fetchone()
    job = row[0] if row else None
    return job if job in JOBS else None


def set_job(conn, guild_id: int, user_id: int, job_id: str) -> None:
    """Pasang/ganti job (validasi di caller)."""
    conn.execute(
        "INSERT INTO job (user_id, guild_id, job_id, diambil) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(user_id, guild_id) DO UPDATE SET job_id = excluded.job_id, diambil = excluded.diambil",
        (
            user_id,
            guild_id,
            job_id,
            datetime.datetime.now(datetime.timezone.utc).isoformat(),
        ),
    )
    conn.commit()


def bonus_untuk(conn, guild_id: int, user_id: int) -> dict:
    """Return dict bonus job aktif, kosong bila tidak punya job."""
    job = get_job(conn, guild_id, user_id)
    if not job:
        return {}
    return JOBS[job]
