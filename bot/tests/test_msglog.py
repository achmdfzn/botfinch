"""Hardening message logging (moderation.py).

Kontrak yang dijaga:
- Listener `on_message_edit`, `on_message_delete`, dan `on_bulk_message_delete`
  tidak jalan bila toggle `msglog_enabled` dimatikan via dashboard
  (default "1" = perilaku lama tetap jalan).
- DM tidak pernah di-log (guild None) — privasi.
- Edit tanpa perubahan konten tidak di-log.
- Pesan bot tidak di-log.
- Bulk delete hanya log ringkas (jumlah + channel), TIDAK dump isi pesan.
- mod-log tidak bisa memicu mass-ping dari konten user yang di-log.

Jalanin: .venv/bin/python -m pytest tests/test_msglog.py -q
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from src.cogs.moderation import Moderation
from src.store import get_connection, init_db

init_db()

GID = 616100  # guild id khusus file test ini


def _set(key: str, value: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO dashboard_settings (guild_id, key, value)"
            " VALUES (?, ?, ?)",
            (GID, str(key), str(value)),
        )
        conn.commit()


def _bersih() -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM dashboard_settings WHERE guild_id = ?", (GID,))
        conn.commit()


def _pesan(guild_id=GID, konten="halo dunia", bot=False):
    """Pesan mock: channel id jauh dari counting_channel_id (default 0)."""
    m = MagicMock()
    m.author.bot = bot
    m.author.mention = "<@7>"
    m.content = konten
    m.channel.mention = "<#9>"
    m.channel.id = 424242
    if guild_id is None:
        m.guild = None
    else:
        m.guild.id = guild_id
    return m


def _cog():
    bot = MagicMock()
    cog = Moderation.__new__(Moderation)
    cog.bot = bot
    return cog


def _run_edit(before, after):
    with patch("src.cogs.moderation.modlog.log_event", new=AsyncMock()) as logm:
        asyncio.run(_cog().on_message_edit(before, after))
    return logm


def _run_delete(message):
    with patch("src.cogs.moderation.modlog.log_event", new=AsyncMock()) as logm:
        asyncio.run(_cog().on_message_delete(message))
    return logm


def _run_bulk(messages):
    with patch("src.cogs.moderation.modlog.log_event", new=AsyncMock()) as logm:
        asyncio.run(_cog().on_bulk_message_delete(messages))
    return logm


# ---------- on_message_edit ----------

def test_edit_toggle_off_tidak_log():
    _bersih()
    _set("msglog_enabled", "0")
    sebelum = _pesan(konten="lama")
    sesudah = _pesan(konten="baru")
    assert _run_edit(sebelum, sesudah).call_count == 0


def test_edit_toggle_on_log():
    _bersih()
    _set("msglog_enabled", "1")
    sebelum = _pesan(konten="lama")
    sesudah = _pesan(konten="baru")
    assert _run_edit(sebelum, sesudah).call_count == 1


def test_edit_tanpa_perubahan_tidak_log():
    _bersih()
    _set("msglog_enabled", "1")
    pesan = _pesan(konten="sama")
    assert _run_edit(pesan, _pesan(konten="sama")).call_count == 0


def test_edit_pesan_bot_tidak_log():
    _bersih()
    _set("msglog_enabled", "1")
    sebelum = _pesan(konten="lama", bot=True)
    sesudah = _pesan(konten="baru", bot=True)
    assert _run_edit(sebelum, sesudah).call_count == 0


def test_edit_dm_tidak_log():
    _bersih()
    _set("msglog_enabled", "1")
    sebelum = _pesan(guild_id=None, konten="lama")
    sesudah = _pesan(guild_id=None, konten="baru")
    assert _run_edit(sebelum, sesudah).call_count == 0


# ---------- on_message_delete ----------

def test_delete_toggle_off_tidak_log():
    _bersih()
    _set("msglog_enabled", "0")
    assert _run_delete(_pesan(konten="hapus aku")).call_count == 0


def test_delete_toggle_on_log():
    _bersih()
    _set("msglog_enabled", "1")
    assert _run_delete(_pesan(konten="hapus aku")).call_count == 1


def test_delete_pesan_bot_tidak_log():
    _bersih()
    _set("msglog_enabled", "1")
    assert _run_delete(_pesan(konten="dari bot", bot=True)).call_count == 0


def test_delete_dm_tidak_log():
    _bersih()
    _set("msglog_enabled", "1")
    assert _run_delete(_pesan(guild_id=None, konten="rahasia dm")).call_count == 0


# ---------- on_bulk_message_delete ----------

def test_bulk_log_ringkas_sekali():
    """Bulk delete -> log_event terpanggil SEKALI, isi pesan tidak ikut."""
    _bersih()
    _set("msglog_enabled", "1")
    pesan = [_pesan(konten=f"RAHASIA-UNIK-{i}") for i in range(5)]
    logm = _run_bulk(pesan)
    assert logm.call_count == 1
    judul, deskripsi = logm.call_args[0][1], logm.call_args[0][2]
    assert "massal" in judul.lower()
    assert "5" in deskripsi
    assert "RAHASIA-UNIK" not in deskripsi  # isi pesan tidak di-dump


def test_bulk_toggle_off_tidak_log():
    _bersih()
    _set("msglog_enabled", "0")
    pesan = [_pesan(konten="x") for _ in range(3)]
    assert _run_bulk(pesan).call_count == 0


def test_bulk_dm_tidak_log():
    _bersih()
    _set("msglog_enabled", "1")
    pesan = [_pesan(guild_id=None, konten="dm") for _ in range(3)]
    assert _run_bulk(pesan).call_count == 0


def test_bulk_kosong_tidak_log():
    _bersih()
    _set("msglog_enabled", "1")
    assert _run_bulk([]).call_count == 0


# ---------- mod-log anti mass-ping ----------

def test_modlog_mentions_tanpa_everyone():
    """Konten user yang di-log tidak boleh memicu @everyone/@here."""
    from src.utils import modlog

    assert modlog.MENTIONS_LOG_AMAN.everyone is False
    assert modlog.MENTIONS_LOG_AMAN.users is True
