"""Regression test audit gelombang-1 Worker C (track misc/utilitas).

Fokus: bug logika yang diperbaiki di putaran ini —
- loop scheduler yang mati selamanya saat DB error (events, birthday,
  youtube, twitch),
- kirim_pengumuman (dashboard_sync) yang crash oleh satu item rusak,
- backup_harian (utilitas) yang crash bila channel bukan teks,
- on_member_join (verification) yang mengunci bot di role unverified,
- fallback mention reminder yang tidak nge-ping (deny-by-default),
- tree /bantuan: tidak ada command yang hilang akibat edit.

Jalanin: python -m pytest tests/test_audit3_misc.py -q
"""
import asyncio
import datetime
import sqlite3
import tempfile
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.ext import commands, tasks

from src import store

# ---------------------------------------------------------------------------
# Helper DB temporer
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_tmp(monkeypatch):
    tmp = tempfile.TemporaryDirectory()
    monkeypatch.setattr(store, "DB_PATH", Path(tmp.name) / "finch.db")
    store.init_db()
    yield
    tmp.cleanup()


def _db_error(*a, **k):
    raise sqlite3.OperationalError("database is locked (simulasi)")


def _cog_baru(cls):
    cog = cls.__new__(cls)
    cog.bot = MagicMock()
    return cog


# ---------------------------------------------------------------------------
# 1. events.cek_event tahan DB error
# ---------------------------------------------------------------------------


def test_events_cek_event_tahan_db_error(db_tmp):
    from src.cogs.events import Events

    cog = _cog_baru(Events)
    with patch("src.cogs.events.get_connection", side_effect=_db_error):
        asyncio.run(cog.cek_event())  # tidak boleh raise
    # loop tetap "sehat": tidak ada exception yang lolos


def test_events_cek_event_rsvp_error_tidak_bunuh_loop(db_tmp):
    """SELECT event_rsvp yang gagal -> event dilewati, loop lanjut."""
    from src.cogs import events as ev_mod
    from src.cogs.events import Events

    now = datetime.datetime.now(datetime.timezone.utc)
    kapan = (now + datetime.timedelta(minutes=30)).isoformat()
    with store.get_connection() as conn:
        conn.execute(
            "INSERT INTO events (guild_id, channel_id, message_id, nama, kapan, deskripsi)"
            " VALUES (1, 2, 3, 'Rapat', ?, '')",
            (kapan,),
        )
        conn.commit()

    cog = _cog_baru(Events)
    channel = AsyncMock()
    channel.send = AsyncMock()
    cog.bot.get_channel.return_value = channel

    asli = ev_mod.get_connection

    def get_conn_rusak():
        # SELECT events OK, SELECT event_rsvp lempar
        class _Conn:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def execute(self, sql, params=()):
                if "event_rsvp" in sql:
                    raise sqlite3.OperationalError("rusak")
                return asli().execute(sql, params)

        return _Conn()

    with patch("src.cogs.events.get_connection", side_effect=lambda: get_conn_rusak()):
        asyncio.run(cog.cek_event())  # tidak boleh raise
    channel.send.assert_not_called()  # event dilewati, tidak dikirim


# ---------------------------------------------------------------------------
# 2. birthday.cek_ultah tahan DB error
# ---------------------------------------------------------------------------


def test_birthday_cek_ultah_tahan_db_error(db_tmp):
    from src.cogs.birthday import Birthday

    cog = _cog_baru(Birthday)
    with patch("src.cogs.birthday.get_connection", side_effect=_db_error):
        asyncio.run(cog.cek_ultah())  # tidak boleh raise


# ---------------------------------------------------------------------------
# 3. youtube.cek_youtube tahan DB error + HTTP error tidak bunuh loop
# ---------------------------------------------------------------------------


def _stub_wait(cog):
    cog.bot.wait_until_ready = AsyncMock()


def test_youtube_loop_tahan_db_error(db_tmp):
    from src.cogs.youtube import Youtube

    cog = _cog_baru(Youtube)
    cog.seeded = True  # lewati cabang seed, uji cabang utama
    _stub_wait(cog)
    with patch("src.cogs.youtube.get_connection", side_effect=_db_error):
        asyncio.run(cog.cek_youtube())  # tidak boleh raise


def test_youtube_http_error_tidak_bunuh_loop(db_tmp):
    """channel.send melempar HTTPException (non-Forbidden) -> loop lanjut."""
    from src.cogs import youtube as yt_mod
    from src.cogs.youtube import Youtube

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<feed xmlns="http://www.w3.org/2005/Atom"'
        ' xmlns:yt="http://www.youtube.com/xml/schemas/2015">'
        "<entry><yt:videoId>abc123</yt:videoId><title>V1</title></entry>"
        "<entry><yt:videoId>def456</yt:videoId><title>V2</title></entry>"
        "</feed>"
    )

    class _Resp:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def text(self):
            return xml

    class _Sess:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def get(self, *a, **k):
            return _Resp()

    cog = _cog_baru(Youtube)
    cog.seeded = True
    _stub_wait(cog)
    channel = AsyncMock(spec=discord.TextChannel)
    channel.send = AsyncMock(
        side_effect=[discord.HTTPException(MagicMock(status=500), "err"), None]
    )
    cog.bot.get_channel.return_value = channel

    settings = SimpleNamespace(
        yt_channel_id="UCxxx", yt_notify_channel_id=999,
        yt_check_minutes=15, yt_ping_role_id=0,
    )
    with patch("src.cogs.youtube.config") as cfg, patch(
        "aiohttp.ClientSession", _Sess
    ):
        cfg.settings = settings
        asyncio.run(cog.cek_youtube())  # tidak boleh raise

    # video pertama gagal HTTP -> tetap ditandai + lanjut ke video kedua
    assert channel.send.await_count == 2
    with yt_mod.get_connection() as conn:
        ada = {
            r[0]
            for r in conn.execute("SELECT video_id FROM yt_posts").fetchall()
        }
    assert {"abc123", "def456"} <= ada


# ---------------------------------------------------------------------------
# 4. twitch.cek_twitch tahan DB error
# ---------------------------------------------------------------------------


def test_twitch_loop_tahan_db_error(db_tmp):
    from src.cogs.twitch import Twitch

    class _Resp:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def json(self):
            return {"data": [{"id": "s1", "title": "t", "game_name": "g",
                              "thumbnail_url": ""}]}

    class _Sess:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def get(self, *a, **k):
            return _Resp()

    cog = _cog_baru(Twitch)
    _stub_wait(cog)
    cog._get_token = AsyncMock(return_value="tok")
    cog.bot.get_channel.return_value = MagicMock()  # bukan TextChannel -> skip kirim
    settings = SimpleNamespace(
        twitch_client_id="id", twitch_client_secret="s", twitch_channel="ch",
        twitch_notify_channel_id=123, twitch_check_minutes=15,
    )
    with patch("src.cogs.twitch.config") as cfg, patch(
        "aiohttp.ClientSession", _Sess
    ), patch("src.cogs.twitch.get_connection", side_effect=_db_error):
        cfg.settings = settings
        asyncio.run(cog.cek_twitch())  # tidak boleh raise


# ---------------------------------------------------------------------------
# 5-6. dashboard_sync.kirim_pengumuman: item rusak tidak bunuh loop;
#      happy path menandai last_sent_at
# ---------------------------------------------------------------------------


def _ds_cog():
    from src.cogs.dashboard_sync import DashboardSync, TABEL_ANNOUNCEMENTS

    cog = DashboardSync.__new__(DashboardSync)
    cog.bot = MagicMock()
    cog.bot.guilds = []
    with store.get_connection() as conn:
        conn.execute(TABEL_ANNOUNCEMENTS)
        conn.commit()
    return cog


def test_pengumuman_item_rusak_tidak_bunuh_loop(db_tmp):

    cog = _ds_cog()
    with store.get_connection() as conn:
        conn.execute(
            "INSERT INTO dashboard_announcements (id, guild_id, channel_id, message,"
            " run_at, interval_minutes, enabled) VALUES (1, '111', '222', 'Halo', ?, 0, 1)",
            ((datetime.datetime.now(datetime.timezone.utc)
              - datetime.timedelta(minutes=1)).isoformat(),),
        )
        conn.commit()
    guild = MagicMock()
    guild.id = 111
    cog.bot.get_guild.return_value = guild
    # modul_aktif meledak (simulasi DB/setting korup)
    with patch("src.cogs.dashboard_sync.modul_aktif", side_effect=RuntimeError("boom")):
        asyncio.run(cog.kirim_pengumuman())  # tidak boleh raise
    # baris tetap ada & belum terkirim (tidak ditandai sukses palsu)
    with store.get_connection() as conn:
        row = conn.execute(
            "SELECT last_sent_at FROM dashboard_announcements WHERE id = 1"
        ).fetchone()
    assert row[0] is None


def test_pengumuman_terkirim_menandai_last_sent(db_tmp):

    cog = _ds_cog()
    with store.get_connection() as conn:
        conn.execute(
            "INSERT INTO dashboard_announcements (id, guild_id, channel_id, message,"
            " run_at, interval_minutes, enabled) VALUES (2, '111', '222', 'Halo {server}', ?, 0, 1)",
            ((datetime.datetime.now(datetime.timezone.utc)
              - datetime.timedelta(minutes=1)).isoformat(),),
        )
        conn.commit()
    guild = MagicMock()
    guild.id = 111
    guild.name = "ServerQ"
    guild.member_count = 42
    channel = AsyncMock()
    channel.send = AsyncMock()
    channel.guild.id = 111  # ownership guard: channel milik guild yang sama
    guild.get_channel.return_value = channel
    cog.bot.get_guild.return_value = guild
    with patch("src.cogs.dashboard_sync.modul_aktif", return_value=True):
        asyncio.run(cog.kirim_pengumuman())
    channel.send.assert_awaited_once()
    teks = channel.send.call_args.args[0]
    assert "ServerQ" in teks  # substitusi {server} jalan
    with store.get_connection() as conn:
        row = conn.execute(
            "SELECT last_sent_at FROM dashboard_announcements WHERE id = 2"
        ).fetchone()
    assert row[0] is not None


# ---------------------------------------------------------------------------
# 7. utilitas.backup_harian: channel bukan teks -> fail-soft
# ---------------------------------------------------------------------------


def test_backup_channel_bukan_teks_tidak_crash(db_tmp):
    from src.cogs.utilitas import Utilitas

    cog = _cog_baru(Utilitas)
    voice = MagicMock(spec=discord.VoiceChannel)  # bukan TextChannel
    cog.bot.get_channel.return_value = voice
    settings = SimpleNamespace(backup_channel_id=12345)
    with patch("src.cogs.utilitas.config") as cfg:
        cfg.settings = settings
        asyncio.run(cog.backup_harian())  # tidak boleh raise
    voice.send.assert_not_called()


# ---------------------------------------------------------------------------
# 8. verification.on_member_join lewati bot
# ---------------------------------------------------------------------------


def test_verifikasi_lewati_bot():
    from src.cogs.verification import Verification

    cog = _cog_baru(Verification)
    member = MagicMock()
    member.bot = True
    member.add_roles = AsyncMock()
    asyncio.run(cog.on_member_join(member))
    member.add_roles.assert_not_called()


# ---------------------------------------------------------------------------
# 9. reminders: fallback mention harus benar-benar nge-ping
# ---------------------------------------------------------------------------


def test_reminder_fallback_mention_nge_ping(db_tmp):
    from src.cogs.reminders import Reminders

    cog = _cog_baru(Reminders)
    cog.bot.get_user.return_value = None
    cog.bot.fetch_user = AsyncMock(
        side_effect=discord.NotFound(MagicMock(status=404), "x")
    )
    channel = AsyncMock()
    channel.send = AsyncMock()
    cog.bot.get_channel.return_value = channel

    now = discord.utils.utcnow()
    with store.get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO reminders (user_id, guild_id, channel_id, message, remind_at)"
            " VALUES (777, 1, 888, 'tes', ?)",
            ((now - datetime.timedelta(minutes=1)).isoformat(),),
        )
        conn.commit()
        rid = cur.lastrowid

    asyncio.run(cog._kirim(rid, 777, 888, "tes"))
    channel.send.assert_awaited_once()
    args, kwargs = channel.send.call_args
    assert "<@777>" in args[0]
    am = kwargs.get("allowed_mentions")
    # Hardening (audit-3 Worker D): hanya pemilik reminder (777) yang boleh
    # di-ping — users=True lama memungkinkan ping orang lain lewat teks
    # reminder buatan user.
    assert isinstance(am, discord.AllowedMentions)
    assert [getattr(u, "id", u) for u in (am.users or [])] == [777]


# ---------------------------------------------------------------------------
# 10. /bantuan: tidak ada command yang hilang dari tree akibat edit
# ---------------------------------------------------------------------------

# (nama modul, nama class cog, daftar command slash yang wajib ada)
_COG_WAJIB = [
    ("general", "General", ["status", "serverinfo", "userinfo", "bantuan"]),
    ("utilitas", "Utilitas", ["grafik", "embed-buat", "rutin"]),
    ("profil", "Profil", ["profil"]),
    ("polls", "Polls", ["poll", "poll-rutin", "poll-rutin-list", "poll-rutin-hapus"]),
    ("reminders", "Reminders", ["remind", "remind-list", "remind-batal",
                                "remind-rutin", "remind-rutin-list", "remind-rutin-hapus"]),
    ("saran", "Saran", ["saran", "saran-status", "saran-top"]),
    ("selfroles", "SelfRoles", ["panel-role"]),
    ("sticky", "Sticky", ["sticky-set", "sticky-hapus"]),
    ("verification", "Verification", ["verifikasi"]),
    ("invites", "Invites", ["invites", "invite-lb"]),
    ("events", "Events", ["event", "event-list"]),
    ("bump", "Bump", ["bump"]),
    ("afk", "Afk", ["afk"]),
    ("birthday", "Birthday", ["ultah"]),
    ("counting", "Counting", ["counting-reset"]),
    ("responder", "Responder", ["respon-add", "respon-del", "respon-list"]),
    ("leaderboard", "Leaderboard", ["leaderboard"]),
    ("dashboard_sync", "DashboardSync", []),
    ("youtube", "Youtube", []),
    ("twitch", "Twitch", []),
    ("serverstats", "ServerStats", []),
    ("report", "Report", []),  # context menu, bukan slash
]

_SUB_WAJIB = {
    "grafik": ["level", "voice"],
    "rutin": ["buat", "list", "hapus"],
}


def _nama_tree(cmd):
    if isinstance(cmd, discord.app_commands.Group):
        return {cmd.name} | {f"{cmd.name} {sub.name}" for sub in cmd.commands}
    return {cmd.name}


def test_tree_command_tidak_hilang(db_tmp):
    import importlib

    async def _main():
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
        for mod_name, cls_name, _wajib in _COG_WAJIB:
            mod = importlib.import_module(f"src.cogs.{mod_name}")
            cls = getattr(mod, cls_name)
            if cls_name == "Utilitas":
                # jangan start server dashboard aiohttp saat tes
                with patch.object(cls, "cog_load", lambda self: asyncio.sleep(0)):
                    await bot.add_cog(cls(bot))
            else:
                await bot.add_cog(cls(bot))
        ada = set()
        for cmd in bot.tree.get_commands():
            ada |= _nama_tree(cmd)
        # matikan semua loop biar tidak menggantung
        for cog in list(bot.cogs):
            for attr in dir(cog):
                loop = getattr(cog, attr, None)
                if isinstance(loop, tasks.Loop) and loop.is_running():
                    loop.cancel()
        await bot.close()
        return ada

    ada = asyncio.run(_main())
    for mod_name, cls_name, wajib in _COG_WAJIB:
        for nama in wajib:
            assert nama in ada, f"command /{nama} HILANG dari tree ({mod_name})"
    for grup, subs in _SUB_WAJIB.items():
        for sub in subs:
            assert f"{grup} {sub}" in ada, f"subcommand /{grup} {sub} HILANG"
    # context menu "Laporkan ke Mod" tetap terdaftar
    assert "Laporkan ke Mod" in ada
