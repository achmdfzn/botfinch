"""Quest harian — misi yang ke-reset tiap hari (tanggal UTC).

QUESTS: (id, nama, kolom_progress, kolom_klaim, target, hadiah_koin, satuan)
Contoh: kirim 25 pesan -> +150 koin.
"""

import datetime

QUESTS: list[tuple[str, str, str, str, int, int, str]] = [
    ("pesan", "💬 Aktif Chat", "pesan", "klaim_pesan", 25, 150, "pesan"),
    ("voice", "🗣️ Nongkrong Voice", "voice_menit", "klaim_voice", 30, 200, "menit"),
    ("daily", "🎁 Klaim Daily", "daily_ok", "klaim_daily", 1, 50, "klaim"),
]


def _tanggal_hari_ini() -> str:
    return datetime.datetime.now(datetime.timezone.utc).date().isoformat()


def _baris(conn, guild_id: int, user_id: int, tanggal: str | None = None) -> dict:
    tanggal = tanggal or _tanggal_hari_ini()
    row = conn.execute(
        "SELECT pesan, voice_menit, daily_ok, klaim_pesan, klaim_voice, klaim_daily"
        " FROM quest_progress WHERE user_id = ? AND guild_id = ? AND tanggal = ?",
        (user_id, guild_id, tanggal),
    ).fetchone()
    if row:
        return {
            "pesan": row[0], "voice_menit": row[1], "daily_ok": row[2],
            "klaim_pesan": row[3], "klaim_voice": row[4], "klaim_daily": row[5],
        }
    conn.execute(
        "INSERT INTO quest_progress (user_id, guild_id, tanggal) VALUES (?, ?, ?)",
        (user_id, guild_id, tanggal),
    )
    conn.commit()
    return {"pesan": 0, "voice_menit": 0, "daily_ok": 0,
            "klaim_pesan": 0, "klaim_voice": 0, "klaim_daily": 0}


def tambah_pesan(conn, guild_id: int, user_id: int) -> None:
    """Dipanggil tiap pesan (dari leveling.on_message)."""
    _baris(conn, guild_id, user_id)
    conn.execute(
        "UPDATE quest_progress SET pesan = pesan + 1"
        " WHERE user_id = ? AND guild_id = ? AND tanggal = ?",
        (user_id, guild_id, _tanggal_hari_ini()),
    )
    conn.commit()


def tambah_voice(conn, guild_id: int, user_id: int, menit: int) -> None:
    """Dipanggil saat sesi voice selesai (dari voicexp)."""
    if menit <= 0:
        return
    _baris(conn, guild_id, user_id)
    conn.execute(
        "UPDATE quest_progress SET voice_menit = voice_menit + ?"
        " WHERE user_id = ? AND guild_id = ? AND tanggal = ?",
        (menit, user_id, guild_id, _tanggal_hari_ini()),
    )
    conn.commit()


def tandai_daily(conn, guild_id: int, user_id: int) -> None:
    """Dipanggil saat /daily berhasil diklaim."""
    _baris(conn, guild_id, user_id)
    conn.execute(
        "UPDATE quest_progress SET daily_ok = 1"
        " WHERE user_id = ? AND guild_id = ? AND tanggal = ?",
        (user_id, guild_id, _tanggal_hari_ini()),
    )
    conn.commit()


def status_quest(conn, guild_id: int, user_id: int) -> list[dict]:
    """Status semua quest hari ini: progress, selesai, sudah_diklaim."""
    baris = _baris(conn, guild_id, user_id)
    hasil = []
    for qid, nama, kolom, kolom_klaim, target, hadiah, satuan in QUESTS:
        progress = min(baris[kolom], target)
        hasil.append({
            "id": qid,
            "nama": nama,
            "progress": progress,
            "target": target,
            "hadiah": hadiah,
            "satuan": satuan,
            "selesai": baris[kolom] >= target,
            "diklaim": bool(baris[kolom_klaim]),
        })
    return hasil


def klaim_quest(conn, guild_id: int, user_id: int) -> tuple[int, list[str]]:
    """Klaim semua quest yang selesai & belum diklaim.

    Return (total_hadiah_koin, [nama_quest]). Koin-nya dikredit oleh caller
    via eko.tambah_koin (biar satu tempat yang urus saldo).
    """
    tanggal = _tanggal_hari_ini()
    baris = _baris(conn, guild_id, user_id, tanggal)
    total = 0
    diklaim_nama = []
    for qid, nama, kolom, kolom_klaim, target, hadiah, _satuan in QUESTS:
        if baris[kolom] >= target and not baris[kolom_klaim]:
            total += hadiah
            diklaim_nama.append(nama)
            conn.execute(
                f"UPDATE quest_progress SET {kolom_klaim} = 1"
                " WHERE user_id = ? AND guild_id = ? AND tanggal = ?",
                (user_id, guild_id, tanggal),
            )
    conn.commit()
    return total, diklaim_nama
