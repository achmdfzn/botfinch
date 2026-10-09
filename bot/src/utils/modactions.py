"""Catat aksi moderasi ke DB lokal (tabel `mod_actions`).

Dipakai oleh command/listener moderasi (ban/kick/timeout/mute/warn/lockdown/
bersihkan/dll). Snapshot dashboard membaca 25 aksi terbaru per server dari
tabel ini (key `modlog` di payload /api/ingest).

Mati total & diam kalau DASHBOARD_URL / DASHBOARD_SECRET kosong — panggilan
ini jadi no-op tanpa menyentuh DB.
"""
import logging

import discord

from src import config
from src.store import get_connection

log = logging.getLogger("finch")

_TABEL = """
CREATE TABLE IF NOT EXISTS mod_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    mod_id TEXT NOT NULL,
    aksi TEXT NOT NULL,
    alasan TEXT NOT NULL DEFAULT '',
    waktu TEXT NOT NULL
)
"""

_tabel_ok = False
# simpan N aksi terbaru per server agar tabel tidak tumbuh tanpa batas
_BATAS_PER_GUILD = 500


def _pastikan_tabel() -> None:
    """Buat tabel bila belum ada (sekali per proses; IF NOT EXISTS aman)."""
    global _tabel_ok
    if _tabel_ok:
        return
    with get_connection() as conn:
        conn.execute(_TABEL)
        conn.commit()
    _tabel_ok = True


def catat_mod_action(guild_id, user_id, mod_id, aksi: str, alasan: str = "") -> None:
    """Simpan satu aksi moderasi.

    `waktu` = ISO UTC saat dicatat. Tidak pernah raise; diam total bila
    dashboard tidak dikonfigurasi (fitur mati).
    """
    if not (config.settings.dashboard_url and config.settings.dashboard_secret):
        return
    try:
        _pastikan_tabel()
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO mod_actions (guild_id, user_id, mod_id, aksi, alasan, waktu)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    str(guild_id),
                    str(user_id),
                    str(mod_id),
                    str(aksi),
                    str(alasan or ""),
                    discord.utils.utcnow().isoformat(),
                ),
            )
            conn.execute(
                "DELETE FROM mod_actions WHERE guild_id = ? AND id NOT IN ("
                " SELECT id FROM mod_actions WHERE guild_id = ?"
                " ORDER BY id DESC LIMIT ?)",
                (str(guild_id), str(guild_id), _BATAS_PER_GUILD),
            )
            conn.commit()
    except Exception:
        log.warning("gagal mencatat aksi moderasi (%s)", aksi, exc_info=True)
