"""Regression test sistem welcome & goodbye Finch.

Kontrak yang dijaga:
- Welcome TIDAK PERNAH kirim DM dalam kondisi apa pun (DM welcome dihapus total;
  key lama `welcome_dm` tidak dipakai lagi). Welcome hanya ke channel.
- Goodbye bisa dikonfigurasi per-server via dashboard:
  `goodbye_enabled` ("1"/"0", default "1"),
  `goodbye_channel_id` (fallback: system channel),
  `goodbye_message` (template {user}/{server}).
- Log mod-log on_member_remove tetap jalan apa pun status goodbye.
- Embed goodbye mengikuti standar UI: teal brand, footer "Finch".

Jalanin: ~/workspace/.venv-finch/bin/python -m pytest tests/test_welcome_goodbye.py -q
"""
import asyncio
import io
from unittest.mock import AsyncMock, MagicMock, patch

from src.bot import FinchBot
from src.cogs.dashboard_sync import TABEL_SETTINGS
from src.store import get_connection, init_db
from src.utils.embeds import BRAND

init_db()  # seperti saat bot startup
with get_connection() as _c:
    _c.execute(TABEL_SETTINGS)
    _c.commit()

GID = 424242  # guild id khusus test ini


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


def _member():
    """Member mock + system channel mock (send-nya AsyncMock)."""
    sysch = MagicMock()
    sysch.send = AsyncMock()
    m = MagicMock()
    m.id = 123
    m.guild.id = GID
    m.guild.name = "Server Tes"
    m.guild.system_channel = sysch
    m.mention = "<@123>"
    m.display_name = "Budi"
    m.display_avatar.read = AsyncMock(return_value=b"avatar")
    m.display_avatar.url = "https://cdn.test/avatar.png"
    m.send = AsyncMock()
    return m, sysch


def _channel():
    ch = MagicMock()
    ch.send = AsyncMock()
    ch.guild.id = GID  # ownership guard: channel harus milik guild yang sama
    ch.type = 0  # channel teks — guard juga menolak tipe non-teks (voice/kategori)
    return ch


# ---------- welcome: tidak pernah DM ----------

def test_welcome_tidak_kirim_dm():
    _bersih()
    _set("welcome_enabled", "1")
    _set("welcome_dm", "1")  # sisa key lama: tetap tidak boleh memicu DM
    bot = FinchBot()
    bot.get_channel = MagicMock(return_value=None)  # paksa fallback system channel
    member, sysch = _member()
    with patch("src.bot.make_welcome_card", return_value=io.BytesIO(b"PNG")):
        asyncio.run(bot.on_member_join(member))
    member.send.assert_not_called()  # <-- inti: DM welcome mati total
    sysch.send.assert_called_once()  # welcome channel tetap terkirim


def test_welcome_mati_tidak_kirim_apa_pun():
    _bersih()
    _set("welcome_enabled", "0")
    bot = FinchBot()
    bot.get_channel = MagicMock(return_value=None)
    member, sysch = _member()
    with patch("src.bot.make_welcome_card", return_value=io.BytesIO(b"PNG")):
        asyncio.run(bot.on_member_join(member))
    member.send.assert_not_called()
    sysch.send.assert_not_called()


# ---------- goodbye ----------

def test_goodbye_ke_channel_terkonfigurasi():
    _bersih()
    _set("goodbye_enabled", "1")
    _set("goodbye_channel_id", "777")
    _set("goodbye_message", "Dadah {user}, sampai jumpa di {server}!")
    bot = FinchBot()
    ch = _channel()
    bot.get_channel = MagicMock(return_value=ch)
    member, sysch = _member()
    with patch("src.utils.modlog.log_event", new=AsyncMock()) as logm:
        asyncio.run(bot.on_member_remove(member))
    logm.assert_called_once()  # mod-log tetap jalan
    sysch.send.assert_not_called()  # bukan ke system channel
    ch.send.assert_called_once()
    embed = ch.send.call_args.kwargs["embed"]
    assert "Dadah <@123>" in embed.description
    assert "Server Tes" in embed.description
    assert "{user}" not in embed.description and "{server}" not in embed.description
    # standar UI: teal konsisten, footer minimalis
    assert embed.color == BRAND
    assert embed.footer.text == "Finch"


def test_goodbye_nonaktif_tetap_modlog():
    _bersih()
    _set("goodbye_enabled", "0")
    bot = FinchBot()
    ch = _channel()
    bot.get_channel = MagicMock(return_value=ch)
    member, sysch = _member()
    with patch("src.utils.modlog.log_event", new=AsyncMock()) as logm:
        asyncio.run(bot.on_member_remove(member))
    logm.assert_called_once()  # mod-log tetap jalan meski goodbye mati
    ch.send.assert_not_called()
    sysch.send.assert_not_called()


def test_goodbye_fallback_system_channel():
    _bersih()
    _set("goodbye_enabled", "1")
    _set("goodbye_channel_id", "999999")  # id tidak dikenal -> get_channel None
    bot = FinchBot()
    bot.get_channel = MagicMock(return_value=None)
    member, sysch = _member()
    with patch("src.utils.modlog.log_event", new=AsyncMock()):
        asyncio.run(bot.on_member_remove(member))
    sysch.send.assert_called_once()
    embed = sysch.send.call_args.kwargs["embed"]
    # template default: perpisahan sopan Bahasa Indonesia
    assert "Budi" in embed.description
    assert "Server Tes" in embed.description


def test_goodbye_tanpa_channel_diam():
    _bersih()
    _set("goodbye_enabled", "1")
    bot = FinchBot()
    bot.get_channel = MagicMock(return_value=None)
    member, _ = _member()
    member.guild.system_channel = None
    with patch("src.utils.modlog.log_event", new=AsyncMock()) as logm:
        asyncio.run(bot.on_member_remove(member))  # tidak raise, tidak kirim
    logm.assert_called_once()
