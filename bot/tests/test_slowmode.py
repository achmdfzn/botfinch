"""Test slowmode manual (src/cogs/slowmode.py) — mock, tanpa koneksi Discord.

Mencakup: validasi range 0–21600, channel default vs eksplisit, penolakan
non-text channel, permission check manage_channels, toggle off -> cog_check
False, pesan ramah saat Forbidden, dan format embed.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import discord
from discord.ext import commands

from src.cogs.dashboard_sync import TABEL_SETTINGS
from src.cogs.slowmode import (
    SLOWMODE_MAX,
    SLOWMODE_MIN,
    Slowmode,
    format_durasi,
    pilih_target,
    validasi_detik,
)
from src.store import get_connection, init_db

init_db()
with get_connection() as _c:
    _c.execute(TABEL_SETTINGS)
    _c.commit()

GID = 515009  # guild id khusus file test ini


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


def _text_channel(slowmode_delay=0):
    ch = MagicMock(spec=discord.TextChannel)
    ch.slowmode_delay = slowmode_delay
    ch.mention = "#umum"
    return ch


def _ctx(channel=None, guild_id=GID):
    ctx = MagicMock()
    ctx.guild.id = guild_id
    ctx.channel = channel or _text_channel()
    ctx.interaction = None
    ctx.send = AsyncMock()
    ctx.author.display_name = "Mod"
    ctx.author.id = 42
    return ctx


def run(coro):
    return asyncio.run(coro)


# ---------- validasi & helper ----------

def test_validasi_range_batas():
    assert validasi_detik(SLOWMODE_MIN) is None
    assert validasi_detik(SLOWMODE_MAX) is None
    assert validasi_detik(30) is None


def test_validasi_range_ditolak():
    assert "❌" in (validasi_detik(-1) or "")
    assert "21600" in (validasi_detik(SLOWMODE_MAX + 1) or "")


def test_format_durasi():
    assert format_durasi(30) == "30 detik"
    assert format_durasi(300) == "5 menit"
    assert format_durasi(3600) == "1 jam"
    assert format_durasi(21600) == "6 jam"


def test_pilih_target_default_channel_ini():
    ch = _text_channel()
    ctx = _ctx(channel=ch)
    target, galat = pilih_target(ctx, None)
    assert galat is None
    assert target is ch


def test_pilih_target_channel_eksplisit():
    ch1 = _text_channel()
    ch2 = _text_channel()
    target, galat = pilih_target(_ctx(channel=ch1), ch2)
    assert galat is None
    assert target is ch2


def test_pilih_target_tolak_voice():
    voice = MagicMock(spec=discord.VoiceChannel)
    target, galat = pilih_target(_ctx(), voice)
    assert target is None
    assert galat and "text channel" in galat


def test_pilih_target_tolak_kategori():
    kategori = MagicMock(spec=discord.CategoryChannel)
    target, galat = pilih_target(_ctx(), kategori)
    assert target is None
    assert galat and "text channel" in galat


def test_pilih_target_tolak_dm():
    ctx = _ctx()
    ctx.guild = None
    target, galat = pilih_target(ctx, None)
    assert target is None
    assert galat and "server" in galat


# ---------- command: izin & metadata ----------

def test_nama_command():
    assert Slowmode.slowmode.name == "slowmode"
    assert Slowmode.slowmode_info.name == "slowmode-info"


def test_permission_check_terpasang():
    checks = Slowmode.slowmode.checks
    assert len(checks) >= 1, "harus ada @commands.has_permissions"


def test_permission_check_lolos_dan_gagal():
    predikat = Slowmode.slowmode.checks[0]

    ctx_ok = MagicMock()
    ctx_ok.permissions = discord.Permissions(manage_channels=True)
    assert predikat(ctx_ok) is True

    ctx_no = MagicMock()
    ctx_no.permissions = discord.Permissions(manage_channels=False)
    try:
        predikat(ctx_no)
        gagal = False
    except commands.MissingPermissions:
        gagal = True
    assert gagal, "tanpa manage_channels harus MissingPermissions"


# ---------- command: /slowmode ----------

def test_slowmode_sukses_panggil_edit():
    cog = Slowmode(MagicMock())
    ch = _text_channel()
    ctx = _ctx(channel=ch)
    run(cog.slowmode.callback(cog, ctx, 30))
    ch.edit.assert_awaited_once()
    assert ch.edit.call_args.kwargs["slowmode_delay"] == 30
    embed = ctx.send.call_args.kwargs["embed"]
    assert "30 detik" in embed.description
    assert embed.fields[0].name == "Moderator"
    assert embed.fields[0].value == "Mod"  # nama polos, bukan mention


def test_slowmode_channel_eksplisit():
    cog = Slowmode(MagicMock())
    ch1 = _text_channel()
    ch2 = _text_channel()
    ctx = _ctx(channel=ch1)
    run(cog.slowmode.callback(cog, ctx, 60, ch2))
    ch1.edit.assert_not_called()
    ch2.edit.assert_awaited_once()


def test_slowmode_nol_matikan():
    cog = Slowmode(MagicMock())
    ch = _text_channel(slowmode_delay=60)
    ctx = _ctx(channel=ch)
    run(cog.slowmode.callback(cog, ctx, 0))
    assert ch.edit.call_args.kwargs["slowmode_delay"] == 0
    embed = ctx.send.call_args.kwargs["embed"]
    assert "Dimatikan" in embed.title


def test_slowmode_range_invalid_tidak_edit():
    cog = Slowmode(MagicMock())
    ch = _text_channel()
    ctx = _ctx(channel=ch)
    run(cog.slowmode.callback(cog, ctx, 99999))
    ch.edit.assert_not_called()
    pesan = ctx.send.call_args.args[0]
    assert "❌" in pesan and "21600" in pesan


def test_slowmode_forbidden_pesan_ramah():
    cog = Slowmode(MagicMock())
    ch = _text_channel()
    ch.edit = AsyncMock(side_effect=discord.Forbidden(MagicMock(status=403), "x"))
    ctx = _ctx(channel=ch)
    run(cog.slowmode.callback(cog, ctx, 30))  # tidak boleh raise
    pesan = ctx.send.call_args.args[0]
    assert "❌" in pesan and "Manage Channels" in pesan


def test_slowmode_info_tampilkan_jeda():
    cog = Slowmode(MagicMock())
    ctx = _ctx(channel=_text_channel(slowmode_delay=120))
    run(cog.slowmode_info.callback(cog, ctx))
    embed = ctx.send.call_args.kwargs["embed"]
    assert "2 menit" in embed.description


def test_slowmode_info_mati():
    cog = Slowmode(MagicMock())
    ctx = _ctx(channel=_text_channel(slowmode_delay=0))
    run(cog.slowmode_info.callback(cog, ctx))
    embed = ctx.send.call_args.kwargs["embed"]
    assert "Tidak ada slowmode" in embed.description


def test_standar_embed_maks_satu_emoji_judul():
    import re

    cog = Slowmode(MagicMock())
    ctx = _ctx(channel=_text_channel(slowmode_delay=30))
    run(cog.slowmode_info.callback(cog, ctx))
    judul = ctx.send.call_args.kwargs["embed"].title
    emoji = re.findall(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF]", judul)
    assert len(emoji) <= 1


# ---------- cog_check / toggle ----------

def test_cog_check_toggle_off_ditolak():
    _set("slowmode_enabled", "0")
    try:
        cog = Slowmode(MagicMock())
        assert run(cog.cog_check(_ctx())) is False
    finally:
        _bersih()


def test_cog_check_toggle_off_kirim_pesan():
    _set("slowmode_enabled", "0")
    try:
        cog = Slowmode(MagicMock())
        ctx = _ctx()
        assert run(cog.cog_check(ctx)) is False
        pesan = ctx.send.call_args.args[0]
        assert "slowmode" in pesan.lower()
    finally:
        _bersih()


def test_cog_check_toggle_nyala_lolos():
    _bersih()
    _set("slowmode_enabled", "1")
    try:
        cog = Slowmode(MagicMock())
        assert run(cog.cog_check(_ctx())) is True
    finally:
        _bersih()
