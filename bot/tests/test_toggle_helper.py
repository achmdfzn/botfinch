"""Test helper `cek_toggle` (src/utils/toggle.py) — ekstraksi pola `cog_check`.

Tiga cabang:
- DM (guild None) -> True tanpa kirim pesan.
- Toggle nyala / belum diset -> True.
- Toggle mati ("0") -> kirim pesan penjelasan sekali, return False.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

from src.cogs.dashboard_sync import TABEL_SETTINGS
from src.store import get_connection, init_db
from src.utils.toggle import cek_toggle

init_db()
with get_connection() as _c:
    _c.execute(TABEL_SETTINGS)
    _c.commit()

GID = 515001  # guild id khusus file test ini


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


def _ctx(guild_id=GID, interaction=None):
    ctx = MagicMock()
    ctx.guild.id = guild_id
    ctx.send = AsyncMock()
    ctx.interaction = interaction
    return ctx


def test_cek_toggle_dm_lolos():
    ctx = MagicMock()
    ctx.guild = None
    ctx.send = AsyncMock()
    assert asyncio.run(cek_toggle(ctx, "economy_enabled", "mati")) is True
    ctx.send.assert_not_called()


def test_cek_toggle_nyala_default():
    _bersih()
    assert asyncio.run(cek_toggle(_ctx(), "economy_enabled", "mati")) is True


def test_cek_toggle_mati_kirim_pesan():
    _bersih()
    _set("economy_enabled", "0")
    ctx = _ctx()
    assert (
        asyncio.run(cek_toggle(ctx, "economy_enabled", "Modul ekonomi dimatikan."))
        is False
    )
    ctx.send.assert_called_once_with("Modul ekonomi dimatikan.")


def test_cek_toggle_mati_slash_interaction():
    _bersih()
    _set("leveling_enabled", "0")
    inter = MagicMock()
    inter.response.is_done.return_value = False
    inter.response.send_message = AsyncMock()
    inter.followup.send = AsyncMock()
    ctx = _ctx(interaction=inter)
    assert (
        asyncio.run(cek_toggle(ctx, "leveling_enabled", "Modul leveling dimatikan."))
        is False
    )
    inter.response.send_message.assert_called_once_with(
        "Modul leveling dimatikan.", ephemeral=True
    )
