"""Tes custom commands (src/cogs/customcmd.py): validasi, sanitasi,
substitusi variabel, toggle, dan batas kuota premium/guild. Mock, tanpa Discord.

Jalanin:  python -m pytest tests/test_customcmd.py -q
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

from src.cogs.customcmd import (
    CustomCmd,
    sanitasi_mention,
    substitusi_variabel,
    tabrakan_command,
    validasi_trigger,
)
from src.cogs.dashboard_sync import TABEL_SETTINGS
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

GID = 515002  # guild id khusus file test ini


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


def _simpan(trigger, respons, author_id=7):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO custom_commands (guild_id, trigger, response, author_id)"
            " VALUES (?, ?, ?, ?)",
            (GID, trigger, respons, author_id),
        )
        conn.commit()


def _bot_palsu(commands_prefix=("ping",), commands_slash=("rank",)):
    bot = MagicMock()
    bot.all_commands = {nama: MagicMock() for nama in commands_prefix}
    slash = [MagicMock(name=nama) for nama in commands_slash]
    for m, nama in zip(slash, commands_slash):
        m.name = nama
    bot.tree.walk_commands.return_value = slash
    return bot


def _message(content, author_mention="@Penanya"):
    message = MagicMock()
    message.author.bot = False
    message.author.mention = author_mention
    message.guild.id = GID
    message.guild.name = "Server Uji"
    message.guild.member_count = 42
    message.channel.mention = "#umum"
    message.channel.send = AsyncMock()
    message.content = content
    return message


def _ctx():
    ctx = MagicMock()
    ctx.guild.id = GID
    ctx.author.id = 7
    ctx.send = AsyncMock()
    return ctx


# ---------- validasi trigger ----------

def test_trigger_valid():
    for t in ("halo", "a1", "sapaan-pagi", "info_bot", "x" * 32):
        ok, err = validasi_trigger(t)
        assert ok, f"{t!r} seharusnya valid: {err}"


def test_trigger_invalid():
    for t in ("", "a", "x" * 33, "Halo", "sapa an", "sapa!", "sapa.an", "é"):
        ok, _ = validasi_trigger(t)
        assert not ok, f"{t!r} seharusnya tidak valid"


# ---------- tabrakan command ----------

def test_tabrakan_prefix():
    assert tabrakan_command(_bot_palsu(), "ping") is True


def test_tabrakan_slash():
    assert tabrakan_command(_bot_palsu(), "rank") is True


def test_tidak_tabrakan():
    assert tabrakan_command(_bot_palsu(), "sapaan") is False


# ---------- sanitasi mention ----------

def test_sanitasi_everyone():
    hasil = sanitasi_mention("Halo @everyone!")
    assert "@everyone" not in hasil
    assert "@\u200beveryone" in hasil


def test_sanitasi_here_case_insensitive():
    hasil = sanitasi_mention("penting @Here @HERE")
    assert "@Here" not in hasil and "@HERE" not in hasil


def test_sanitasi_teks_biasa_utuh():
    assert sanitasi_mention("Halo semua!") == "Halo semua!"


# ---------- substitusi variabel ----------

def test_substitusi_semua_variabel():
    m = _message("!x")
    hasil = substitusi_variabel(
        "{user} selamat datang di {server} ({member_count} member), lihat {channel}",
        m,
    )
    assert hasil == "@Penanya selamat datang di Server Uji (42 member), lihat #umum"


def test_variabel_tak_dikenal_dibiarkan():
    m = _message("!x")
    assert substitusi_variabel("nilai {foo} tetap", m) == "nilai {foo} tetap"


# ---------- on_message: toggle ----------

def test_on_message_toggle_mati_diam():
    _bersih()
    _set_toggle("customcmd_enabled", "0")
    _simpan("sapaan", "Halo!")
    cog = CustomCmd(_bot_palsu())
    msg = _message("!sapaan")
    asyncio.run(cog.on_message(msg))
    msg.channel.send.assert_not_called()


def test_on_message_kirim_dengan_substitusi():
    _bersih()
    _simpan("sapaan", "Halo {user} di {server}!")
    cog = CustomCmd(_bot_palsu())
    msg = _message("!sapaan")
    asyncio.run(cog.on_message(msg))
    msg.channel.send.assert_called_once()
    kwargs = msg.channel.send.call_args
    assert kwargs.args[0] == "Halo @Penanya di Server Uji!"
    mentions = kwargs.kwargs["allowed_mentions"]
    assert mentions.everyone is False
    assert mentions.roles is False
    assert mentions.users == [msg.author]


def test_on_message_akhiran_teks_tidak_cocok():
    _bersih()
    _simpan("sapa", "Halo!")
    cog = CustomCmd(_bot_palsu())
    msg = _message("!sapaan")  # 'sapaan' != 'sapa' -> tidak cocok
    asyncio.run(cog.on_message(msg))
    msg.channel.send.assert_not_called()


def test_on_message_dengan_argumen_cocok():
    _bersih()
    _simpan("sapa", "Halo!")
    cog = CustomCmd(_bot_palsu())
    msg = _message("!sapa pagi semua")
    asyncio.run(cog.on_message(msg))
    msg.channel.send.assert_called_once()


def test_on_message_abaikan_bot_dan_dm():
    _bersih()
    _simpan("sapaan", "Halo!")
    cog = CustomCmd(_bot_palsu())
    msg = _message("!sapaan")
    msg.author.bot = True
    asyncio.run(cog.on_message(msg))
    msg.channel.send.assert_not_called()
    msg2 = _message("!sapaan")
    msg2.guild = None
    asyncio.run(cog.on_message(msg2))
    msg2.channel.send.assert_not_called()


# ---------- /cc-tambah: batas & tabrakan ----------

def test_cc_tambah_tabrakan_ditolak():
    _bersih()
    cog = CustomCmd(_bot_palsu())
    ctx = _ctx()
    asyncio.run(cog.cc_tambah.callback(cog, ctx, "ping", respons="x"))
    ctx.send.assert_called_once()
    assert "menabrak" in ctx.send.call_args.args[0]


def test_cc_tambah_batas_free_10():
    """Kuota Free custom_commands = 10 (katalog premium): trigger ke-11 ditolak."""
    _bersih()
    for i in range(10):
        _simpan(f"cmd{i:02d}", "Halo!")
    cog = CustomCmd(_bot_palsu(commands_prefix=(), commands_slash=()))
    ctx = _ctx()
    asyncio.run(cog.cc_tambah.callback(cog, ctx, "baru", respons="Halo!"))
    ctx.send.assert_called_once()
    pesan = ctx.send.call_args.args[0]
    assert "Batas" in pesan and "(10" in pesan


def test_cc_tambah_update_lolos_walau_penuh():
    _bersih()
    for i in range(50):
        _simpan(f"cmd{i:02d}", "Halo!")
    cog = CustomCmd(_bot_palsu(commands_prefix=(), commands_slash=()))
    ctx = _ctx()
    asyncio.run(cog.cc_tambah.callback(cog, ctx, "cmd00", respons="Baru!"))
    ctx.send.assert_called_once()
    assert "diperbarui" in ctx.send.call_args.args[0]
    with get_connection() as conn:
        row = conn.execute(
            "SELECT response FROM custom_commands WHERE guild_id = ? AND trigger = ?",
            (GID, "cmd00"),
        ).fetchone()
    assert row[0] == "Baru!"


def test_cc_tambah_sanitasi_tersimpan():
    _bersih()
    cog = CustomCmd(_bot_palsu(commands_prefix=(), commands_slash=()))
    ctx = _ctx()
    asyncio.run(cog.cc_tambah.callback(cog, ctx, "info", respons="Halo @everyone"))
    with get_connection() as conn:
        row = conn.execute(
            "SELECT response FROM custom_commands WHERE guild_id = ? AND trigger = ?",
            (GID, "info"),
        ).fetchone()
    assert "@everyone" not in row[0]
    assert "@\u200beveryone" in row[0]


def test_cc_tambah_trigger_invalid_ditolak():
    _bersih()
    cog = CustomCmd(_bot_palsu())
    ctx = _ctx()
    asyncio.run(cog.cc_tambah.callback(cog, ctx, "X", respons="Halo"))
    ctx.send.assert_called_once()
    assert "❌" in ctx.send.call_args.args[0]


# ---------- /cc-hapus & /cc-list ----------

def test_cc_hapus_ada_dan_tidak_ada():
    _bersih()
    _simpan("sapaan", "Halo!")
    cog = CustomCmd(_bot_palsu())
    ctx = _ctx()
    asyncio.run(cog.cc_hapus.callback(cog, ctx, "sapaan"))
    assert "dihapus" in ctx.send.call_args.args[0]
    ctx2 = _ctx()
    asyncio.run(cog.cc_hapus.callback(cog, ctx2, "sapaan"))
    assert "Tidak ada" in ctx2.send.call_args.args[0]


def test_cc_list_embed():
    _bersih()
    _simpan("sapaan", "Halo!")
    _simpan("aturan", "Baca ini.")
    cog = CustomCmd(_bot_palsu())
    ctx = _ctx()
    asyncio.run(cog.cc_list.callback(cog, ctx))
    ctx.send.assert_called_once()
    embed = ctx.send.call_args.kwargs["embed"]
    assert embed.color.value == 0x2EC4B6
    assert "!sapaan" in embed.description and "!aturan" in embed.description


def test_cc_list_kosong():
    _bersih()
    cog = CustomCmd(_bot_palsu())
    ctx = _ctx()
    asyncio.run(cog.cc_list.callback(cog, ctx))
    assert "Belum ada" in ctx.send.call_args.args[0]
