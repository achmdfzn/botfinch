"""Item consumable — dipakai lintas cog (shop, maling, leveling).

Item dibeli via /toko-item, tersimpan di tabel inventory.
Efek dicek via punya_aktif(); tiket lotre dikonsumsi via konsumsi_satu().
"""
import datetime

ITEMS = {
    "perisai": {
        "nama": "🛡️ Perisai Anti-Maling",
        "harga": 500,
        "durasi_jam": 24,
        "deskripsi": "Kebal dari /game maling selama 24 jam.",
    },
    "xpboost": {
        "nama": "⚡ Boost 2x XP",
        "harga": 800,
        "durasi_jam": 1,
        "deskripsi": "XP chat 2x selama 1 jam.",
    },
    "tiket": {
        "nama": "🎟️ Tiket Lotre",
        "harga": 100,
        "durasi_jam": 0,
        "deskripsi": "Tukar dengan 1 tiket lotre minggu berjalan.",
    },
}


def _sekarang() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def beri_item(conn, guild_id: int, user_id: int, item_id: str, jumlah: int = 1) -> None:
    """Tambah item ke inventory (buat row bila belum ada)."""
    info = ITEMS[item_id]
    berakhir = None
    if info["durasi_jam"] > 0:
        berakhir = (_sekarang() + datetime.timedelta(hours=info["durasi_jam"])).isoformat()
    conn.execute(
        "INSERT INTO inventory (user_id, guild_id, item_id, jumlah, berakhir)"
        " VALUES (?, ?, ?, ?, ?)"
        " ON CONFLICT(user_id, guild_id, item_id) DO UPDATE SET"
        " jumlah = jumlah + ?, berakhir = excluded.berakhir",
        (user_id, guild_id, item_id, jumlah, berakhir, jumlah),
    )
    conn.commit()


def punya_aktif(conn, guild_id: int, user_id: int, item_id: str) -> bool:
    """True bila user punya item yang masih berlaku."""
    row = conn.execute(
        "SELECT jumlah, berakhir FROM inventory WHERE user_id = ? AND guild_id = ? AND item_id = ?",
        (user_id, guild_id, item_id),
    ).fetchone()
    if not row or (row[0] or 0) <= 0:
        return False
    if row[1]:
        try:
            exp = datetime.datetime.fromisoformat(row[1])
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=datetime.timezone.utc)
            if exp <= _sekarang():
                return False
        except ValueError:
            return False
    return True


def konsumsi_satu(conn, guild_id: int, user_id: int, item_id: str) -> bool:
    """Kurangi 1 item bila aktif. Return True bila berhasil.

    Atomik: dua `/dagang pakai` bersamaan tidak bisa menghabiskan item
    yang sama 2x (dulu: cek dulu lalu UPDATE — jumlah bisa jadi negatif).
    """
    if not punya_aktif(conn, guild_id, user_id, item_id):
        return False
    cur = conn.execute(
        "UPDATE inventory SET jumlah = jumlah - 1"
        " WHERE user_id = ? AND guild_id = ? AND item_id = ? AND jumlah > 0",
        (user_id, guild_id, item_id),
    )
    conn.commit()
    return cur.rowcount > 0


def daftar_item(conn, guild_id: int, user_id: int) -> list[tuple[str, int, str | None]]:
    """[(item_id, jumlah, berakhir_iso)] milik user."""
    return conn.execute(
        "SELECT item_id, jumlah, berakhir FROM inventory WHERE user_id = ? AND guild_id = ? AND jumlah > 0",
        (user_id, guild_id),
    ).fetchall()
