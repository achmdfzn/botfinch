"""Test registri self-role yatim (Subagent D2, tugas 2f).

Kontrak: bila fetch_message gagal di SEMUA channel, baris ditandai di tabel
selfrole_orphan (persisten antar-restart) sehingga pemindaian mahal
semua-channel tidak diulang tiap loop. Flag dibersihkan saat dashboard
berhenti mengirim baris tersebut; panel baru (message_id baru) di-seed normal.
"""
from unittest.mock import MagicMock

from src.cogs.dashboard_sync import (
    TABEL_ANNOUNCEMENTS,
    TABEL_SELFROLES,
    TABEL_SELFROLE_ORPHAN,
    TABEL_SETTINGS,
    DashboardSync,
)
from src.store import get_connection, init_db

init_db()
with get_connection() as _c:
    _c.execute(TABEL_SETTINGS)
    _c.execute(TABEL_SELFROLES)
    _c.execute(TABEL_ANNOUNCEMENTS)
    _c.execute(TABEL_SELFROLE_ORPHAN)
    _c.commit()

GID = 515151
MID = 777001


def _bersih():
    with get_connection() as conn:
        conn.execute("DELETE FROM dashboard_selfroles WHERE guild_id = ?", (GID,))
        conn.execute("DELETE FROM selfrole_orphan WHERE guild_id = ?", (GID,))
        conn.commit()


def _tambah_panel():
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO dashboard_selfroles (guild_id, message_id, emoji, role_id)"
            " VALUES (?, ?, ?, ?)",
            (GID, MID, "⭐", 123),
        )
        conn.commit()


def _guild_tanpa_channel():
    g = MagicMock()
    g.id = GID
    g.text_channels = []  # pesan tak mungkin ditemukan -> yatim
    return g


def _jumlah_yatim() -> int:
    with get_connection() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM selfrole_orphan WHERE guild_id = ?", (GID,)
        ).fetchone()[0]


async def _seed(cog, guild):
    await cog._seed_reaksi(guild)


def test_baris_yatim_ditandai_dan_tak_dipindai_ulang():
    import asyncio

    _bersih()
    _tambah_panel()
    cog = DashboardSync(MagicMock())
    g = _guild_tanpa_channel()
    asyncio.run(_seed(cog, g))
    assert _jumlah_yatim() == 1
    # Loop berikutnya: baris yatim dilewati (tidak insert ganda / error)
    asyncio.run(_seed(cog, g))
    assert _jumlah_yatim() == 1


def test_flag_dibersihkan_bila_panel_tak_dikirim_lagi():
    import asyncio

    _bersih()
    _tambah_panel()
    cog = DashboardSync(MagicMock())
    asyncio.run(_seed(cog, _guild_tanpa_channel()))
    assert _jumlah_yatim() == 1
    # Dashboard menghapus panel -> sync berikutnya membersihkan flag
    cog._simpan_selfroles(GID, [])
    assert _jumlah_yatim() == 0


def test_panel_baru_message_id_baru_tetap_di_seed():
    import asyncio

    _bersih()
    _tambah_panel()
    cog = DashboardSync(MagicMock())
    asyncio.run(_seed(cog, _guild_tanpa_channel()))
    assert _jumlah_yatim() == 1
    # Panel dibuat ulang (message_id baru) -> bukan yatim, tidak terpengaruh flag lama
    with get_connection() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM selfrole_orphan WHERE guild_id = ? AND message_id = ?",
            (GID, MID + 1),
        ).fetchone()[0] == 0
