"""Regresi audit tahap 5: isolasi guild dan timestamp scheduler."""
from types import SimpleNamespace

from src import store
from src.cogs import dashboard_sync as ds


def test_channel_milik_guild_menerima_guild_yang_sama():
    channel = SimpleNamespace(guild=SimpleNamespace(id=12345))
    assert ds._channel_milik_guild(channel, 12345)


def test_channel_milik_guild_menolak_guild_lain_dan_dm():
    channel_lain = SimpleNamespace(guild=SimpleNamespace(id=54321))
    channel_dm = SimpleNamespace()
    assert not ds._channel_milik_guild(channel_lain, 12345)
    assert not ds._channel_milik_guild(channel_dm, 12345)
    assert not ds._channel_milik_guild(None, 12345)


def test_simpan_pengumuman_mempertahankan_timestamp_lokal_yang_lebih_baru(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "finch.db")
    store.init_db()
    guild_id = 12345
    timestamp_lokal = "2026-10-21T10:00:00+00:00"
    with store.get_connection() as conn:
        conn.execute(ds.TABEL_ANNOUNCEMENTS)
        conn.execute(
            "INSERT INTO dashboard_announcements "
            "(id, guild_id, channel_id, message, run_at, interval_minutes, enabled, last_sent_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (9, str(guild_id), "123456789", "pesan lama", None, 60, 1, timestamp_lokal),
        )
        conn.commit()

    cog = ds.DashboardSync.__new__(ds.DashboardSync)
    cog._simpan_pengumuman(
        guild_id,
        [{
            "id": 9,
            "channel_id": "123456789",
            "message": "pesan baru",
            "run_at": None,
            "interval_minutes": 60,
            "enabled": True,
            "last_sent_at": None,
        }],
    )

    with store.get_connection() as conn:
        row = conn.execute(
            "SELECT message, last_sent_at FROM dashboard_announcements WHERE id = ?",
            (9,),
        ).fetchone()
    assert row[0] == "pesan baru"
    assert row[1] == timestamp_lokal
