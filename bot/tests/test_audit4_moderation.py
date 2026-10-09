"""Regresi audit-4 area moderasi (tanpa koneksi Discord).

Kontrak yang dijaga:
- /lockdown: alasan dipotong ke 200 char (audit-log Discord menolak >512,
  dan reason kepanjangan membuat SEMUA set_permissions gagal diam-diam).
- Pesan peringatan automod/moderation tidak crash listener bila bot tidak
  bisa kirim pesan (Forbidden) — helper _kirim_aman.
- automod._mute: DB error setelah timeout sukses tidak melempar keluar
  (mute Discord tetap jalan, warning tercatat).
- automod: DB error saat catat warning tidak crash listener.
- Voice log (moderasi_plus.on_voice_state_update) hormat toggle
  msglog_enabled (default nyala, mati -> tidak ada log_event).
- tickets._buat_tiket: HTTPException dari buat_tiket -> followup error,
  bukan exception tak tertangani.
- _strip_hoist: tidak false-positive ke nama normal (unicode alnum,
  diawali digit), nama kosong -> None.

Jalanin: .venv/bin/python -m pytest tests/test_audit4_moderation.py -q
"""
import asyncio
import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from src.cogs.automod import _kirim_aman as _kirim_aman_automod
from src.cogs.automod import _mute, _strip_hoist
from src.cogs.moderasi_plus import ModerasiPlus
from src.cogs.moderation import (
    ALASAN_MAKS,
    _batasi_alasan,
    _kirim_aman,
)
from src.cogs import tickets as tickets_mod
from src.store import get_connection, init_db

init_db()

GID = 717171  # guild id khusus file test ini


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


# ---------- /lockdown: batas panjang alasan ----------


def test_batasi_alasan_dipotong():
    assert _batasi_alasan("x" * 5000) == "x" * ALASAN_MAKS
    assert ALASAN_MAKS == 200


def test_batasi_alasan_kosong_jadi_default():
    assert _batasi_alasan("") == "Lockdown oleh admin"
    assert _batasi_alasan(None) == "Lockdown oleh admin"
    assert _batasi_alasan("   ") == "Lockdown oleh admin"


def test_batasi_alasan_normal_utuh():
    assert _batasi_alasan("Raid semalam") == "Raid semalam"


# ---------- _kirim_aman tidak crash ----------


def _channel_gagal():
    ch = MagicMock()
    ch.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "nope"))
    return ch


def test_kirim_aman_moderation_telan_forbidden():
    asyncio.run(_kirim_aman(_channel_gagal(), "halo", delete_after=10))


def test_kirim_aman_automod_telan_forbidden():
    asyncio.run(_kirim_aman_automod(_channel_gagal(), "halo", delete_after=10))


def test_kirim_aman_kirim_normal():
    ch = MagicMock()
    ch.send = AsyncMock()
    asyncio.run(_kirim_aman(ch, "halo"))
    ch.send.assert_awaited_once()


# ---------- automod._mute: DB error tidak melempar ----------


def _member_mute_ok():
    m = MagicMock()
    m.id = 4242
    m.guild.id = GID
    m.timeout = AsyncMock()
    return m


def test_mute_db_gagal_tetap_return_teks():
    member = _member_mute_ok()

    def _conn_gagal():
        raise sqlite3.OperationalError("database is locked")

    with patch("src.cogs.automod.get_connection", side_effect=_conn_gagal):
        hasil = asyncio.run(_mute(member, "test mute", 10))
    # Timeout Discord sudah jalan -> teks info tetap dikembalikan, tanpa raise.
    assert hasil == " 🔇 Di-mute 10 menit."
    member.timeout.assert_awaited_once()


def test_mute_forbidden_return_kosong():
    member = _member_mute_ok()
    member.timeout = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "nope"))
    hasil = asyncio.run(_mute(member, "test mute", 10))
    assert hasil == ""


# ---------- automod on_message: DB warning gagal -> teguran tanpa hitungan ----------


def _pesan_badword():
    msg = MagicMock()
    msg.author.bot = False
    msg.author.id = 777
    msg.author.mention = "<@777>"
    msg.author.guild_permissions.manage_messages = False
    msg.guild.id = GID
    msg.content = "kamu goblok banget"
    msg.delete = AsyncMock()
    msg.channel.send = AsyncMock()
    return msg


def test_on_message_db_warning_gagal_tidak_crash():
    from src.cogs.automod import AutoMod

    cog = AutoMod.__new__(AutoMod)
    cog.bot = MagicMock()
    msg = _pesan_badword()
    _bersih()  # default toggle nyala

    def _conn_gagal():
        raise sqlite3.OperationalError("boom")

    with patch("src.cogs.automod.get_connection", side_effect=_conn_gagal):
        asyncio.run(cog.on_message(msg))  # tidak boleh raise
    # Teguran generik (tanpa hitungan) tetap terkirim.
    msg.channel.send.assert_awaited_once()
    teks = msg.channel.send.call_args.args[0]
    assert "bahasa tidak pantas" in teks


# ---------- voice log hormat toggle msglog_enabled ----------


def _voice_state(nama):
    vs = MagicMock()
    vs.channel = MagicMock()
    vs.channel.name = nama
    return vs


def _member_voice():
    m = MagicMock()
    m.guild.id = GID
    m.mention = "<@99>"
    return m


def test_voice_log_mati_saat_toggle_off():
    cog = ModerasiPlus.__new__(ModerasiPlus)
    cog.bot = MagicMock()
    _set("msglog_enabled", "0")
    try:
        with patch("src.cogs.moderasi_plus.modlog.log_event", new=AsyncMock()) as logm:
            asyncio.run(
                cog.on_voice_state_update(
                    _member_voice(), _voice_state("Lobi"), _voice_state("Ruang 1")
                )
            )
        logm.assert_not_awaited()
    finally:
        _bersih()


def test_voice_log_nyala_default():
    cog = ModerasiPlus.__new__(ModerasiPlus)
    cog.bot = MagicMock()
    _bersih()  # default "1"
    with patch("src.cogs.moderasi_plus.modlog.log_event", new=AsyncMock()) as logm:
        asyncio.run(
            cog.on_voice_state_update(
                _member_voice(), _voice_state("Lobi"), _voice_state("Ruang 1")
            )
        )
    logm.assert_awaited_once()


# ---------- tickets._buat_tiket: HTTPException -> followup, bukan crash ----------


def test_buat_tiket_http_exception_ditangani():
    async def _jalan():
        interaction = MagicMock()
        interaction.guild = MagicMock()
        interaction.guild.id = GID
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.bot = False
        interaction.user.id = 31337
        interaction.response = AsyncMock()
        interaction.followup = AsyncMock()
        resp = MagicMock(status=500, reason="err")
        with patch(
            "src.cogs.tickets.buat_tiket",
            new=AsyncMock(side_effect=discord.HTTPException(resp, "boom")),
        ):
            await tickets_mod._buat_tiket(interaction)
        return interaction

    interaction = asyncio.run(_jalan())
    interaction.followup.send.assert_awaited_once()
    teks = interaction.followup.send.call_args.args[0]
    assert "Gagal membuat tiket" in teks


# ---------- _strip_hoist: tanpa false-positive ----------


@pytest.mark.parametrize(
    "nama",
    [
        "Budi",
        "1337Gamer",
        "Álvaro",
        "日本語ユーザー",
        "محمد",
        "xX Dark Knight Xx",
        "",
    ],
)
def test_strip_hoist_nama_normal_tidak_disentuh(nama):
    assert _strip_hoist(nama) is None


@pytest.mark.parametrize(
    "nama,hasil",
    [
        ("!Budi", "Budi"),
        ("!!!Budi", "Budi"),
        ("...", "Member"),
        ("_Kaito", "Kaito"),
    ],
)
def test_strip_hoist_dekorasi_di_strip(nama, hasil):
    assert _strip_hoist(nama) == hasil
