"""Test sinkronisasi dashboard web (dashboard_sync)."""
import sqlite3

from src.cogs.dashboard_sync import TABEL_SETTINGS as TABEL, _nilai, get_guild_setting
from src.store import get_connection, init_db

init_db()  # pastikan folder data/ ada (seperti saat bot startup)
with get_connection() as _c:
    _c.execute(TABEL)
    _c.commit()


def _bersih(gid: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM dashboard_settings WHERE guild_id = ?", (gid,))
        conn.commit()


def test_nilai_bool():
    assert _nilai(True) == "1"
    assert _nilai(False) == "0"
    assert _nilai("x") == "x"


def test_get_guild_setting_default():
    _bersih(999001)
    assert get_guild_setting(999001, "welcome_enabled", "1") == "1"
    assert get_guild_setting(999001, "apa_aja", "0") == "0"


def test_get_guild_setting_roundtrip():
    _bersih(999002)
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO dashboard_settings (guild_id, key, value) VALUES (?, ?, ?)",
            (999002, "leveling_enabled", "0"),
        )
        conn.commit()
    try:
        assert get_guild_setting(999002, "leveling_enabled", "1") == "0"
    finally:
        _bersih(999002)


def test_config_punya_dashboard_keys():
    from src import config

    assert hasattr(config.settings, "dashboard_url")
    assert hasattr(config.settings, "dashboard_secret")
    # default kosong = sinkronisasi mati
    assert config.settings.dashboard_url == "" or isinstance(config.settings.dashboard_url, str)


def test_env_example_tidak_bocor():
    txt = open("src/cogs/dashboard_sync.py").read()
    assert "DASHBOARD_SECRET" not in txt or "os.getenv" in txt or "config.settings" in txt


# --- Push instan: on_ready sekali + on_guild_join segera, no-op bila mati ---

def _cog_mati():
    """DashboardSync dengan integrasi mati (env kosong di test)."""
    import discord
    from discord.ext import commands
    from src.cogs.dashboard_sync import DashboardSync

    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    cog = DashboardSync(bot)
    assert cog._jalan is False
    return cog


def test_kirim_snapshot_noop_bila_mati():
    import asyncio

    cog = _cog_mati()
    # tidak boleh raise / tidak boleh coba HTTP apa pun
    asyncio.run(cog._kirim_snapshot([], "tes"))
    asyncio.run(cog._kirim_snapshot([], "tes"))


def test_on_guild_join_noop_bila_mati():
    import asyncio
    from unittest.mock import MagicMock

    cog = _cog_mati()
    asyncio.run(cog.on_guild_join(MagicMock()))  # return dini, tanpa sleep/HTTP


def test_on_ready_hanya_sekali(monkeypatch):
    import asyncio
    from unittest.mock import AsyncMock

    cog = _cog_mati()
    # paksa _jalan True tapi ganti pengirim aslinya dengan mock
    cog._jalan = True
    mock = AsyncMock()
    monkeypatch.setattr(cog, "_kirim_snapshot", mock)
    asyncio.run(cog.on_ready())
    asyncio.run(cog.on_ready())  # reconnect -> tidak kirim lagi
    assert mock.await_count == 1
    assert mock.await_args_list[0].args[1] == "startup"
