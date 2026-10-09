"""Tes regresi audit-4 untuk 3 cog baru (tidak duplikat file test lama).

Fokus: pertahanan mass-ping customcmd (sanitasi + AllowedMentions),
permission check cc-tambah/cc-hapus, race condition batas 50/guild,
Range detik /slowmode, dan pre-check izin autopublish.
Mock, tanpa koneksi Discord.

Jalanin:  python -m pytest tests/test_audit4_custom.py -q
"""
import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock

import discord
from discord.ext import commands

from src.cogs.autopublish import AutoPublish
from src.cogs.customcmd import (
    JUMLAH_MAKS,
    CustomCmd,
    _mention_aman,
    sanitasi_mention,
)
from src.cogs.dashboard_sync import TABEL_SETTINGS, modul_aktif
from src.cogs.slowmode import SLOWMODE_MAX, SLOWMODE_MIN, Slowmode
from src.store import get_connection, init_db

init_db()
with get_connection() as _c:
    _c.execute(TABEL_SETTINGS)
    _c.execute(
        "CREATE TABLE IF NOT EXISTS custom_commands "
        "(guild_id INTEGER NOT NULL, trigger TEXT NOT NULL, "
        "response TEXT NOT NULL, author_id INTEGER NOT NULL DEFAULT 0, "
        "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
        "PRIMARY KEY (guild_id, trigger))"
    )
    _c.commit()

GID = 515099  # guild id khusus file test ini


def _set_toggle(key, value):
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO dashboard_settings (guild_id, key, value)"
            " VALUES (?, ?, ?)",
            (GID, str(key), str(value)),
        )
        conn.commit()


def _bersih():
    with get_connection() as conn:
        conn.execute("DELETE FROM custom_commands WHERE guild_id = ?", (GID,))
        conn.execute("DELETE FROM dashboard_settings WHERE guild_id = ?", (GID,))
        conn.commit()


def _jumlah():
    with get_connection() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM custom_commands WHERE guild_id = ?", (GID,)
        ).fetchone()[0]


def _bot_palsu():
    bot = MagicMock()
    bot.all_commands = {}
    bot.tree.walk_commands.return_value = []
    return bot


def _ctx():
    ctx = MagicMock()
    ctx.guild.id = GID
    ctx.author.id = 7
    ctx.send = AsyncMock()
    return ctx


def _message(content, author_id=42, author_mention="<@42>"):
    message = MagicMock()
    message.author.bot = False
    message.author.id = author_id
    message.author.mention = author_mention
    message.guild.id = GID
    message.guild.name = "Server Uji"
    message.guild.member_count = 42
    message.channel.mention = "#umum"
    message.channel.send = AsyncMock()
    message.content = content
    return message


# ---------- sanitasi @everyone/@here ----------

def test_sanitasi_varian_kapital():
    assert "\u200b" in sanitasi_mention("@EVERYONE halo")
    assert "\u200b" in sanitasi_mention("@Here halo")
    assert "\u200b" in sanitasi_mention("@eVeRyOnE")


def test_sanitasi_multi_kejadian():
    hasil = sanitasi_mention("@everyone dan @here bareng")
    assert hasil.count("\u200b") == 2
    assert "@everyone" not in hasil and "@here" not in hasil


def test_sanitasi_teks_tanpa_mention_utuh():
    teks = "halo {user}, selamat datang di {server}!"
    assert sanitasi_mention(teks) == teks


# ---------- AllowedMentions deny-by-default ----------

def test_mention_aman_blokir_mass_ping():
    msg = MagicMock()
    msg.author.id = 42
    payload = _mention_aman(msg).to_dict()
    assert "everyone" not in payload.get("parse", [])
    assert "roles" not in payload.get("parse", [])
    assert payload["users"] == [42], "hanya pengirim yang boleh di-mention"


def test_render_tidak_bisa_mass_ping():
    """End-to-end: respons berisi @everyone + mention user/role lain
    dirender tanpa bisa nge-ping siapa pun kecuali pengirim."""
    _bersih()
    _set_toggle("customcmd_enabled", "1")
    try:
        cog = CustomCmd(_bot_palsu())
        # Simpan via jalur asli cc-tambah (sanitasi @everyone -> ZWSP di sini)
        ctx_simpan = _ctx()
        asyncio.run(
            cog.cc_tambah.callback(
                cog, ctx_simpan, "jahat",
                respons="@everyone halo <@&999> <@888>",
            )
        )
        msg = _message("!jahat")
        asyncio.run(cog.on_message(msg))
        assert msg.channel.send.await_count == 1
        kwargs = msg.channel.send.await_args.kwargs
        terkirim = msg.channel.send.await_args.args[0]
        # @everyone terputus oleh ZWSP saat disimpan
        assert "@everyone" not in terkirim
        assert "\u200b" in terkirim
        # AllowedMentions: everyone & roles mati total
        payload = kwargs["allowed_mentions"].to_dict()
        assert "everyone" not in payload.get("parse", [])
        assert "roles" not in payload.get("parse", [])
        assert payload["users"] == [42]
    finally:
        _bersih()


# ---------- permission check cc-tambah / cc-hapus ----------

def test_cc_tambah_butuh_manage_guild():
    predikat = CustomCmd.cc_tambah.checks[0]
    ctx_ok = MagicMock()
    ctx_ok.permissions = discord.Permissions(manage_guild=True)
    assert predikat(ctx_ok) is True
    ctx_no = MagicMock()
    ctx_no.permissions = discord.Permissions(manage_guild=False)
    try:
        predikat(ctx_no)
        gagal = False
    except commands.MissingPermissions:
        gagal = True
    assert gagal, "tanpa manage_guild harus MissingPermissions"


def test_cc_hapus_butuh_manage_guild():
    predikat = CustomCmd.cc_hapus.checks[0]
    ctx_no = MagicMock()
    ctx_no.permissions = discord.Permissions(manage_guild=False)
    try:
        predikat(ctx_no)
        gagal = False
    except commands.MissingPermissions:
        gagal = True
    assert gagal, "tanpa manage_guild harus MissingPermissions"


# ---------- race condition batas 50 ----------

def _tambah_di_thread(cog, trigger, hasil, idx):
    ctx = _ctx()
    try:
        asyncio.run(cog.cc_tambah.callback(cog, ctx, trigger, respons="x"))
    except Exception as e:  # noqa: BLE001 - catat saja, jangan sembunyikan
        hasil[idx] = f"EXC {type(e).__name__}: {e}"
        return
    hasil[idx] = ctx.send.await_args.args[0]


def test_batas_50_tahan_dua_tambah_paralel():
    """Isi 49, lalu dua /cc-tambah paralel: total tidak boleh > 50,
    satu harus ditolak dengan pesan batas."""
    _bersih()
    try:
        with get_connection() as conn:
            conn.executemany(
                "INSERT INTO custom_commands (guild_id, trigger, response, author_id)"
                " VALUES (?, ?, ?, ?)",
                [(GID, f"cmd{i:02d}", "x", 7) for i in range(JUMLAH_MAKS - 1)],
            )
            conn.commit()
        assert _jumlah() == JUMLAH_MAKS - 1

        cog = CustomCmd(_bot_palsu())
        hasil = [None, None]
        threads = [
            threading.Thread(
                target=_tambah_di_thread, args=(cog, f"race-{i}", hasil, i)
            )
            for i in range(2)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        assert all(h is not None for h in hasil), f"thread gagal: {hasil}"

        assert _jumlah() <= JUMLAH_MAKS, "batas 50 terlampaui (race!)"
        assert sum("ditambahkan" in h for h in hasil) == 1, hasil
        assert sum("Batas" in h for h in hasil) == 1, hasil
    finally:
        _bersih()


# ---------- /slowmode: Range di level Discord UI ----------

def test_slowmode_detik_punya_range_0_21600():
    import inspect

    annot = inspect.signature(Slowmode.slowmode.callback).parameters["detik"].annotation
    assert getattr(annot, "min_value", None) == SLOWMODE_MIN
    assert getattr(annot, "max_value", None) == SLOWMODE_MAX


# ---------- autopublish: pre-check izin ----------

def _pesan_news(manage_messages=True):
    msg = MagicMock()
    msg.guild.id = GID
    msg.guild.me = MagicMock()
    msg.author.bot = False
    ch = MagicMock(spec=discord.TextChannel)
    ch.is_news.return_value = True
    ch.permissions_for.return_value.manage_messages = manage_messages
    msg.channel = ch
    msg.publish = AsyncMock()
    return msg


def test_autopublish_tanpa_izin_skip_tanpa_api_call():
    _bersih()
    _set_toggle("autopublish_enabled", "1")
    try:
        cog = AutoPublish(MagicMock())
        msg = _pesan_news(manage_messages=False)
        asyncio.run(cog.on_message(msg))
        msg.publish.assert_not_awaited()
    finally:
        _bersih()


def test_autopublish_dengan_izin_tetap_publish():
    _bersih()
    _set_toggle("autopublish_enabled", "1")
    try:
        assert modul_aktif(GID, "autopublish_enabled") is True
        cog = AutoPublish(MagicMock())
        msg = _pesan_news(manage_messages=True)
        asyncio.run(cog.on_message(msg))
        assert msg.publish.await_count == 1
    finally:
        _bersih()
