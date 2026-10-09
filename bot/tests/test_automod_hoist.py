"""Test anti-hoist di src/cogs/automod.py — mock, tanpa koneksi Discord.

Cabang:
- nama "!Budi" -> di-strip jadi "Budi" (edit dipanggil).
- nama "Budi" -> sudah bersih, tidak disentuh.
- automod_enabled = "0" -> skip walau nama kotor.
- Forbidden saat edit -> tidak crash.
- helper _strip_hoist: sisa kosong -> "Member", nama bersih -> None,
  maksimal 10 karakter dekorasi di-strip.
- on_member_update: nama berubah jadi hoist -> di-strip.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import discord

from src.cogs.automod import AutoMod, _strip_hoist
from src.cogs.dashboard_sync import TABEL_SETTINGS
from src.store import get_connection, init_db

init_db()
with get_connection() as _c:
    _c.execute(TABEL_SETTINGS)
    _c.commit()

GID = 515010  # guild id khusus file test ini


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


def _member(display_name="!Budi", bot_pos=10, member_pos=5, izin=True):
    member = MagicMock()
    member.display_name = display_name
    member.nick = None
    member.bot = False
    member.guild.id = GID
    me = MagicMock()
    me.guild_permissions.manage_nicknames = izin
    me.top_role.position = bot_pos
    member.guild.me = me
    member.top_role.position = member_pos
    member.edit = AsyncMock()
    return member


def _cog():
    return AutoMod(MagicMock())


def test_strip_hoist_nama_kotor():
    assert _strip_hoist("!Budi") == "Budi"
    assert _strip_hoist("☠!Budi") == "Budi"


def test_strip_hoist_nama_bersih():
    assert _strip_hoist("Budi") is None
    assert _strip_hoist("123Abc") is None


def test_strip_hoist_sisa_kosong_jadi_member():
    assert _strip_hoist("!!!") == "Member"


def test_strip_hoist_maks_10_karakter():
    assert _strip_hoist("!" * 12 + "Budi") == "!!Budi"


def test_join_nama_kotor_distrip():
    _bersih()
    member = _member("!Budi")
    asyncio.run(_cog().on_member_join(member))
    member.edit.assert_called_once_with(nick="Budi", reason="Anti-hoist otomatis")


def test_join_nama_bersih_tidak_disentuh():
    _bersih()
    member = _member("Budi")
    asyncio.run(_cog().on_member_join(member))
    member.edit.assert_not_called()


def test_join_automod_mati_skip():
    _bersih()
    _set("automod_enabled", "0")
    member = _member("!Budi")
    asyncio.run(_cog().on_member_join(member))
    member.edit.assert_not_called()
    _bersih()


def test_join_forbidden_tidak_crash():
    _bersih()
    member = _member("!Budi")
    resp = MagicMock()
    resp.status = 403
    resp.reason = "Forbidden"
    member.edit.side_effect = discord.Forbidden(resp, "Forbidden")
    asyncio.run(_cog().on_member_join(member))  # tidak boleh raise
    member.edit.assert_called_once()


def test_join_tanpa_izin_manage_nicknames_skip():
    _bersih()
    member = _member("!Budi", izin=False)
    asyncio.run(_cog().on_member_join(member))
    member.edit.assert_not_called()


def test_join_target_lebih_tinggi_hierarki_skip():
    _bersih()
    member = _member("!Budi", bot_pos=5, member_pos=10)
    asyncio.run(_cog().on_member_join(member))
    member.edit.assert_not_called()


def test_update_nama_berubah_jadi_hoist_distrip():
    _bersih()
    before = _member("Budi")
    after = _member("!!!Budi")
    asyncio.run(_cog().on_member_update(before, after))
    after.edit.assert_called_once_with(nick="Budi", reason="Anti-hoist otomatis")


def test_update_nama_tidak_berubah_skip():
    _bersih()
    before = _member("!Budi")
    after = _member("!Budi")
    after.edit = AsyncMock()
    asyncio.run(_cog().on_member_update(before, after))
    after.edit.assert_not_called()
