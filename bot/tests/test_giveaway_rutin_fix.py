"""Regression test untuk bug indentasi `_proses_rutin` (giveaway rutin).

Bug: seluruh blok posting giveaway rutin terperangkap di bawah
`return` pada cabang `if channel is None:` — kode mati (unreachable),
sehingga /g-rutin tidak pernah memposting apa pun.

Test: saat jatuh tempo & channel ada, `_posting_giveaway` HARUS dipanggil
dan `terakhir` diperbarui. Saat channel hilang / belum jatuh tempo,
tidak ada posting.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import discord

from src.cogs.dashboard_sync import TABEL_SETTINGS
from src.cogs.giveaway import Giveaway
from src.store import get_connection, init_db

init_db()
with get_connection() as _c:
    _c.execute(TABEL_SETTINGS)
    _c.commit()

GID = 515002
CHID = 777001


def _bersih():
    with get_connection() as conn:
        conn.execute("DELETE FROM giveaway_rutin WHERE guild_id = ?", (GID,))
        conn.execute("DELETE FROM server_pool WHERE guild_id = ?", (GID,))
        conn.commit()


def _tambah_rutin(terakhir):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO giveaway_rutin (guild_id, channel_id, interval_detik,"
            " pemenang, hadiah, koin, host_id, terakhir)"
            " VALUES (?, ?, 3600, 1, 'Hadiah', 0, 111, ?)",
            (GID, CHID, terakhir),
        )
        conn.commit()
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def _cog(channel):
    cog = Giveaway.__new__(Giveaway)  # tanpa start loop
    cog.bot = MagicMock()
    cog.bot.get_channel.return_value = channel
    cog._posting_giveaway = AsyncMock(return_value=123456)
    return cog


def _terakhir(rid):
    with get_connection() as conn:
        return conn.execute(
            "SELECT terakhir FROM giveaway_rutin WHERE id = ?", (rid,)
        ).fetchone()[0]


def test_rutin_jatuh_tempo_memposting():
    _bersih()
    rid = _tambah_rutin(None)  # belum pernah jalan -> jatuh tempo
    cog = _cog(MagicMock())
    now = discord.utils.utcnow()
    asyncio.run(cog._proses_rutin(now, rid, GID, CHID, 3600, 1, "Hadiah", 0, 111, None))
    cog._posting_giveaway.assert_called_once()
    assert _terakhir(rid) is not None  # terakhir diperbarui


def test_rutin_belum_jatuh_tempo_tidak_memposting():
    _bersih()
    now = discord.utils.utcnow()
    rid = _tambah_rutin(now.isoformat())  # baru saja jalan
    cog = _cog(MagicMock())
    asyncio.run(cog._proses_rutin(now, rid, GID, CHID, 3600, 1, "Hadiah", 0, 111, now.isoformat()))
    cog._posting_giveaway.assert_not_called()


def test_rutin_channel_hilang_tidak_memposting():
    _bersih()
    rid = _tambah_rutin(None)
    cog = _cog(None)  # get_channel -> None
    now = discord.utils.utcnow()
    asyncio.run(cog._proses_rutin(now, rid, GID, CHID, 3600, 1, "Hadiah", 0, 111, None))
    cog._posting_giveaway.assert_not_called()
    assert _terakhir(rid) is None  # terakhir TIDAK diperbarui
