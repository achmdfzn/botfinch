"""Regresi integrasi starboard <-> dashboard.

Bug yang diperbaiki di src/cogs/starboard.py::_sync:
1. Channel & ambang starboard per-server dari dashboard
   (`starboard_channel_id`, `starboard_threshold`) sebelumnya diabaikan —
   bot selalu memakai env global config.settings.starboard_channel_id /
   starboard_min. Sekarang: dashboard dulu, fallback env bila kosong/tak valid.
2. Default `starboard_enabled` dibuat eksplisit "1" (ON) selaras
   SETTING_DEFAULTS dashboard (D-001) — konvensi bot: modul default aktif;
   tanpa channel terkonfigurasi starboard tetap tidak beraksi.

Jalanin: .venv/bin/python -m pytest tests/test_starboard_dashboard.py -q
"""
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from src.cogs.starboard import Starboard
from src.store import get_connection, init_db

init_db()

GID = 515001  # guild id khusus file test ini (beda dari test_toggle_plugin)

CHANNEL_ENV = 31337
CHANNEL_DASH = 99999
SRC_CHANNEL = 222


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
        conn.execute("DELETE FROM starboard WHERE channel_id = ?", (SRC_CHANNEL,))
        conn.execute("DELETE FROM starboard_rewarded")
        conn.commit()


def _pengaturan(**kw):
    """Stub config.settings (frozen) — koin 0 agar jalur reward dilewati."""
    kw.setdefault("starboard_koin", 0)
    stub = MagicMock()
    for k, v in kw.items():
        setattr(stub, k, v)
    return patch("src.config.settings", new=stub)


def _pesan(bintang: int, msg_id: int):
    msg = MagicMock()
    msg.id = msg_id
    msg.content = "halo dunia"
    msg.jump_url = "https://discord.com/channels/x/777"
    msg.created_at = datetime.now(timezone.utc)
    msg.author.bot = False
    msg.author.id = 4242
    msg.author.display_avatar.url = "https://cdn.discordapp.com/x.png"
    msg.attachments = []
    reaksi = MagicMock()
    reaksi.emoji = "⭐"  # str("⭐") == "⭐" lolos filter _sync
    reaksi.count = bintang
    msg.reactions = [reaksi]
    return msg


def _channel(cid: int, msg=None):
    ch = MagicMock(spec=discord.TextChannel)
    ch.id = cid
    ch.mention = f"<#{cid}>"
    ch.fetch_message = AsyncMock(return_value=msg)
    sb_msg = MagicMock()
    sb_msg.id = 888000 + cid
    ch.send = AsyncMock(return_value=sb_msg)
    return ch


def _bot_dengan(ch_src, sb_ch):
    bot = MagicMock()
    guild = MagicMock()
    peta = {ch_src.id: ch_src, sb_ch.id: sb_ch}
    guild.get_channel = MagicMock(side_effect=lambda cid: peta.get(cid))
    bot.get_guild = MagicMock(return_value=guild)
    return bot, guild


def _payload(msg_id: int):
    payload = MagicMock()
    payload.emoji = "⭐"
    payload.guild_id = GID
    payload.message_id = msg_id
    payload.channel_id = SRC_CHANNEL
    return payload


def test_dashboard_channel_dan_threshold_dipakai():
    """starboard_channel_id + starboard_threshold dashboard mengalahkan env."""
    _bersih()
    _set("starboard_enabled", "1")
    _set("starboard_channel_id", str(CHANNEL_DASH))
    _set("starboard_threshold", "5")
    with _pengaturan(starboard_channel_id=CHANNEL_ENV, starboard_min=3):
        bot, guild = _bot_dengan(
            _channel(SRC_CHANNEL), _channel(CHANNEL_DASH)
        )
        # 4 bintang: di bawah ambang dashboard (5) -> TIDAK diposting,
        # meski sudah >= starboard_min env (3).
        msg4 = _pesan(4, 777001)
        ch_src = _channel(SRC_CHANNEL, msg4)
        sb_ch = _channel(CHANNEL_DASH)
        bot2, _ = _bot_dengan(ch_src, sb_ch)
        cog2 = Starboard(bot2)
        asyncio.run(cog2._sync(_payload(777001)))
        sb_ch.send.assert_not_called()
        # guild.get_channel HARUS dipanggil dengan id dashboard, bukan env
        ids_diminta = [c.args[0] for c in bot2.get_guild.return_value.get_channel.call_args_list]
        assert CHANNEL_DASH in ids_diminta
        assert CHANNEL_ENV not in ids_diminta

        # 5 bintang: mencapai ambang dashboard -> diposting ke channel dashboard
        _bersih()
        _set("starboard_enabled", "1")
        _set("starboard_channel_id", str(CHANNEL_DASH))
        _set("starboard_threshold", "5")
        msg5 = _pesan(5, 777002)
        ch_src5 = _channel(SRC_CHANNEL, msg5)
        sb_ch5 = _channel(CHANNEL_DASH)
        bot5, _ = _bot_dengan(ch_src5, sb_ch5)
        cog5 = Starboard(bot5)
        asyncio.run(cog5._sync(_payload(777002)))
        sb_ch5.send.assert_called_once()


def test_fallback_env_bila_dashboard_kosong():
    """Tanpa key dashboard -> pakai env global seperti dulu."""
    _bersih()
    _set("starboard_enabled", "1")
    with _pengaturan(starboard_channel_id=CHANNEL_ENV, starboard_min=3):
        msg = _pesan(3, 777003)
        ch_src = _channel(SRC_CHANNEL, msg)
        sb_ch = _channel(CHANNEL_ENV)
        bot, _ = _bot_dengan(ch_src, sb_ch)
        cog = Starboard(bot)
        asyncio.run(cog._sync(_payload(777003)))
        sb_ch.send.assert_called_once()
        ids_diminta = [c.args[0] for c in bot.get_guild.return_value.get_channel.call_args_list]
        assert CHANNEL_ENV in ids_diminta


def test_threshold_tak_valid_fallback_ke_env():
    """starboard_threshold='abc' -> diabaikan, pakai starboard_min env."""
    _bersih()
    _set("starboard_enabled", "1")
    _set("starboard_channel_id", str(CHANNEL_DASH))
    _set("starboard_threshold", "abc")
    with _pengaturan(starboard_channel_id=CHANNEL_ENV, starboard_min=3):
        msg = _pesan(3, 777004)
        ch_src = _channel(SRC_CHANNEL, msg)
        sb_ch = _channel(CHANNEL_DASH)
        bot, _ = _bot_dengan(ch_src, sb_ch)
        cog = Starboard(bot)
        asyncio.run(cog._sync(_payload(777004)))
        sb_ch.send.assert_called_once()  # 3 >= min env 3


def test_default_on_tanpa_key():
    """Tanpa key starboard_enabled -> ON (selaras dashboard SETTING_DEFAULTS=true)."""
    _bersih()
    _set("starboard_channel_id", str(CHANNEL_DASH))
    with _pengaturan(starboard_channel_id=CHANNEL_ENV, starboard_min=3):
        msg = _pesan(3, 777005)
        ch_src = _channel(SRC_CHANNEL, msg)
        sb_ch = _channel(CHANNEL_DASH)
        bot, _ = _bot_dengan(ch_src, sb_ch)
        cog = Starboard(bot)
        asyncio.run(cog._sync(_payload(777005)))
        sb_ch.send.assert_called_once()


def test_default_on_tanpa_channel_tidak_beraksi():
    """Default ON tapi tanpa channel terkonfigurasi -> diam (tidak crash)."""
    _bersih()
    with _pengaturan(starboard_channel_id=0, starboard_min=3):
        bot = MagicMock()
        cog = Starboard(bot)
        asyncio.run(cog._sync(_payload(777006)))  # tidak raise
        bot.get_guild.assert_not_called()


def test_dimatikan_eksplisit():
    """starboard_enabled='0' -> OFF meski channel terkonfigurasi."""
    _bersih()
    _set("starboard_enabled", "0")
    _set("starboard_channel_id", str(CHANNEL_DASH))
    with _pengaturan(starboard_channel_id=CHANNEL_ENV, starboard_min=3):
        bot = MagicMock()
        cog = Starboard(bot)
        asyncio.run(cog._sync(_payload(777007)))
        bot.get_guild.assert_not_called()
