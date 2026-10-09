"""Test auto-publish di src/cogs/autopublish.py — mock, tanpa koneksi Discord.

Cabang:
- channel news + author non-bot -> message.publish() dipanggil.
- channel biasa -> skip.
- author bot -> skip.
- autopublish_enabled = "0" -> skip.
- Forbidden saat publish -> tidak crash.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import discord

from src.cogs.autopublish import AutoPublish
from src.cogs.dashboard_sync import TABEL_SETTINGS
from src.store import get_connection, init_db

init_db()
with get_connection() as _c:
    _c.execute(TABEL_SETTINGS)
    _c.commit()

GID = 515020  # guild id khusus file test ini


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


def _channel(is_news=True):
    # spec=discord.TextChannel agar isinstance() lolos pada mock
    ch = MagicMock(spec=discord.TextChannel)
    ch.is_news.return_value = is_news
    return ch


def _pesan(is_news=True, author_bot=False, guild_id=GID):
    msg = MagicMock()
    msg.guild.id = guild_id
    msg.author.bot = author_bot
    msg.channel = _channel(is_news)
    msg.publish = AsyncMock()
    return msg


def _cog():
    return AutoPublish(MagicMock())


def test_news_channel_non_bot_dipublish():
    _bersih()
    msg = _pesan(is_news=True, author_bot=False)
    asyncio.run(_cog().on_message(msg))
    msg.publish.assert_called_once_with()


def test_channel_biasa_skip():
    _bersih()
    msg = _pesan(is_news=False)
    asyncio.run(_cog().on_message(msg))
    msg.publish.assert_not_called()


def test_author_bot_skip():
    _bersih()
    msg = _pesan(is_news=True, author_bot=True)
    asyncio.run(_cog().on_message(msg))
    msg.publish.assert_not_called()


def test_toggle_mati_skip():
    _bersih()
    _set("autopublish_enabled", "0")
    msg = _pesan(is_news=True)
    asyncio.run(_cog().on_message(msg))
    msg.publish.assert_not_called()
    _bersih()


def test_forbidden_tidak_crash():
    _bersih()
    msg = _pesan(is_news=True)
    resp = MagicMock()
    resp.status = 403
    resp.reason = "Forbidden"
    msg.publish.side_effect = discord.Forbidden(resp, "Forbidden")
    asyncio.run(_cog().on_message(msg))  # tidak boleh raise
    msg.publish.assert_called_once()
