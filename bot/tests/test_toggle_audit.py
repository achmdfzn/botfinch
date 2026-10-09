"""Regresi audit toggle (2026-10-09).

- giveaway `cek_rutin`: tidak memposting giveaway BARU saat `giveaway_enabled=0`
  (giveaway yang sudah berjalan tetap diselesaikan — sesuai docstring cog_check).
- leveling `on_reaction_add`: XP reaksi menghormati `leveling_enabled`
  (sebelumnya lolos tanpa cek, tidak seperti on_message).
- utilitas `embed_buat`: diblokir saat `embed_enabled=0`.

Jalanin: .venv/bin/python -m pytest tests/test_toggle_audit.py -q
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

from src.cogs.giveaway import Giveaway
from src.cogs.leveling import Leveling
from src.cogs.utilitas import Utilitas
from src.store import get_connection, init_db

init_db()

GID = 515002  # guild id khusus file test ini


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
        conn.execute("DELETE FROM giveaway_rutin WHERE guild_id = ?", (GID,))
        conn.execute("DELETE FROM users WHERE guild_id = ?", (GID,))
        conn.commit()


def _rutin_row(terakhir: str | None):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO giveaway_rutin (guild_id, channel_id, interval_detik,"
            " pemenang, hadiah, koin, host_id, terakhir)"
            " VALUES (?, 31337, 60, 1, 'hadiah', 0, 999, ?)",
            (GID, terakhir),
        )
        conn.commit()


# ---------- giveaway rutin ----------

def test_cek_rutin_lewati_guild_mati():
    """giveaway_enabled=0 -> rutin TIDAK memposting giveaway baru."""
    _bersih()
    _set("giveaway_enabled", "0")
    _rutin_row(None)  # jatuh tempo: belum pernah jalan
    bot = MagicMock()
    bot.get_channel = MagicMock(return_value=MagicMock())
    cog = Giveaway.__new__(Giveaway)
    cog.bot = bot
    asyncio.run(cog.cek_rutin.coro(cog))
    bot.get_channel.assert_not_called()


def test_cek_rutin_jalan_saat_nyala():
    """giveaway_enabled=1 -> rutin diproses normal (get_channel dipanggil)."""
    _bersih()
    _set("giveaway_enabled", "1")
    _rutin_row(None)
    channel = MagicMock()
    channel.send = AsyncMock(side_effect=Exception("jangan kirim beneran"))
    bot = MagicMock()
    bot.get_channel = MagicMock(return_value=channel)
    bot.user = MagicMock()
    bot.user.id = 1
    cog = Giveaway.__new__(Giveaway)
    cog.bot = bot
    asyncio.run(cog.cek_rutin.coro(cog))  # error kirim ditangkap loop -> get_channel tetap dipanggil
    bot.get_channel.assert_called_with(31337)


# ---------- reaction XP ----------

def _reaksi(uid: int):
    reaction = MagicMock()
    reaction.message.guild.id = GID
    user = MagicMock()
    user.bot = False
    user.id = uid
    return reaction, user


def _xp_user(uid: int) -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT xp FROM users WHERE user_id = ? AND guild_id = ?", (uid, GID)
        ).fetchone()
        return row[0] if row else 0


def test_reaction_xp_mati_saat_leveling_off():
    _bersih()
    _set("leveling_enabled", "0")
    cog = Leveling.__new__(Leveling)
    cog.bot = MagicMock()
    reaction, user = _reaksi(424201)
    asyncio.run(cog.on_reaction_add(reaction, user))
    assert _xp_user(424201) == 0


def test_reaction_xp_nyala_saat_leveling_on():
    _bersih()
    _set("leveling_enabled", "1")
    cog = Leveling.__new__(Leveling)
    cog.bot = MagicMock()
    reaction, user = _reaksi(424202)
    asyncio.run(cog.on_reaction_add(reaction, user))
    assert _xp_user(424202) > 0


# ---------- embed builder ----------

def _ctx_embed(interaction):
    ctx = MagicMock()
    ctx.guild.id = GID
    ctx.interaction = interaction
    ctx.send = AsyncMock()
    return ctx


def test_embed_buat_diblokir_saat_mati():
    _bersih()
    _set("embed_enabled", "0")
    cog = Utilitas(MagicMock())
    ctx = _ctx_embed(interaction=MagicMock())
    asyncio.run(cog.embed_buat.callback(cog, ctx))
    ctx.send.assert_called_once()
    # modal TIDAK dibuka
    ctx.interaction.response.send_modal.assert_not_called()


def test_embed_buat_nyala_buka_modal():
    _bersih()
    _set("embed_enabled", "1")
    cog = Utilitas(MagicMock())
    interaction = MagicMock()
    interaction.response.send_modal = AsyncMock()
    ctx = _ctx_embed(interaction=interaction)
    asyncio.run(cog.embed_buat.callback(cog, ctx))
    interaction.response.send_modal.assert_called_once()
    ctx.send.assert_not_called()
