"""Test wiring channel/kategori per-server via dashboard (Subagent D).

Key baru: verify_channel_id, ticket_category_id, saran_channel_id,
counting_channel_id, tempvc_lobby_id, tempvc_category_id,
confess_channel_id, dailyq_channel_id.

Kontrak: channel_setting(gid, key, fallback) -> nilai per-server dari
dashboard bila ada & valid, fallback ke config global bila kosong/rusak.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

from src.cogs.dashboard_sync import (
    TABEL_SETTINGS,
    DashboardSync,
    channel_setting,
    get_guild_setting,
)
from src.store import get_connection, init_db

init_db()
with get_connection() as _c:
    _c.execute(TABEL_SETTINGS)
    _c.commit()

GID = 424242


def _bersih():
    with get_connection() as conn:
        conn.execute("DELETE FROM dashboard_settings WHERE guild_id = ?", (GID,))
        conn.commit()


def _simpan(key: str, value: str):
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO dashboard_settings (guild_id, key, value)"
            " VALUES (?, ?, ?)",
            (GID, key, value),
        )
        conn.commit()


# ---------- channel_setting ----------

def test_fallback_global_bila_belum_diatur():
    _bersih()
    assert channel_setting(GID, "verify_channel_id", 111) == 111
    assert channel_setting(GID, "verify_channel_id", 0) == 0


def test_nilai_dashboard_menang_atas_global():
    _bersih()
    _simpan("saran_channel_id", "222")
    assert channel_setting(GID, "saran_channel_id", 111) == 222


def test_nilai_dashboard_kosong_jatuh_ke_global():
    _bersih()
    _simpan("saran_channel_id", "")
    assert channel_setting(GID, "saran_channel_id", 111) == 111


def test_nilai_dashboard_rusak_jatuh_ke_global():
    _bersih()
    _simpan("counting_channel_id", "bukan-angka")
    assert channel_setting(GID, "counting_channel_id", 333) == 333


def test_semua_key_baru_terbaca():
    _bersih()
    for i, key in enumerate(
        [
            "verify_channel_id",
            "ticket_category_id",
            "saran_channel_id",
            "counting_channel_id",
            "tempvc_lobby_id",
            "tempvc_category_id",
            "confess_channel_id",
            "dailyq_channel_id",
        ]
    ):
        _simpan(key, str(9000 + i))
    for i, key in enumerate(
        [
            "verify_channel_id",
            "ticket_category_id",
            "saran_channel_id",
            "counting_channel_id",
            "tempvc_lobby_id",
            "tempvc_category_id",
            "confess_channel_id",
            "dailyq_channel_id",
        ]
    ):
        assert get_guild_setting(GID, key, "0") == str(9000 + i)
        assert channel_setting(GID, key, 1) == 9000 + i


# ---------- snapshot: voice + kategori ikut terkirim ----------

def _fake_guild():
    def ch(cid, nama, tipe):
        return SimpleNamespace(id=cid, name=nama, type=SimpleNamespace(value=tipe))

    g = MagicMock()
    g.id = GID
    g.name = "Server Tes"
    g.icon = None
    g.member_count = 10
    g.text_channels = [ch(1, "umum", 0)]
    g.voice_channels = [ch(2, "Lobby", 2)]
    g.categories = [ch(3, "Tiket", 4)]
    g.roles = []
    return g


def test_snapshot_channels_termasuk_voice_dan_kategori():
    cog = DashboardSync(MagicMock())
    snap = cog._snapshot_guild(_fake_guild())
    by_id = {c["id"]: c for c in snap["channels"]}
    assert by_id["1"] == {"id": "1", "name": "umum", "type": 0}
    assert by_id["2"] == {"id": "2", "name": "Lobby", "type": 2}
    assert by_id["3"] == {"id": "3", "name": "Tiket", "type": 4}
