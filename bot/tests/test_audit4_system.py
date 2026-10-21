"""Regresi audit putaran-4 — area sistem.

Fokus: dashboard_sync (pull/push tahan error, ack done/failed, tanpa private
API), bot inti (error handler, allowed_mentions), store/config (migrasi,
validator), scheduler (loop selamat dari error), tempvc (yatim), responder
(substitusi aman), reminders (mention pemilik saja), dan keamanan mention
di command user-facing.

Jalankan: ~/workspace/finch/bot/.venv/bin/python -m pytest tests/test_audit4_system.py -q
"""
import ast
import asyncio
import datetime
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord
import pytest

from src import store
from src.bot import MENTIONS_AMAN, MENTIONS_PENGUMUMAN
from src.cogs import dashboard_sync as ds
from src.cogs import events as ev_mod
from src.cogs.achievement import field_achievement
from src.cogs.general import (
    COG_KE_KATEGORI,
    _bagi_ke_field,
    _baris_perintah,
    bangun_data_bantuan,
    build_serverinfo_embed,
    teks_roles_member,
)
from src.cogs.tempvc import _vc_cooldown, buang_cooldown_kedaluwarsa
from src.utils.teks import nama_member_atau_id
from src.utils.variabel import substitusi_variabel

SRC = Path(__file__).resolve().parent.parent / "src"


@pytest.fixture()
def db_tmp(monkeypatch):
    """DB SQLite sementara untuk semua test yang menyentuh store."""
    tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    monkeypatch.setattr(store, "DB_PATH", Path(tmp.name) / "finch.db")
    store.init_db()
    # Tabel milik dashboard_sync (dibuat di __init__ cog aslinya)
    with store.get_connection() as conn:
        conn.execute(ds.TABEL_SETTINGS)
        conn.execute(ds.TABEL_SELFROLES)
        conn.execute(ds.TABEL_ANNOUNCEMENTS)
        conn.commit()
    yield Path(tmp.name) / "finch.db"
    tmp.cleanup()


def _jalan(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# dashboard_sync: push/pull tahan error
# ---------------------------------------------------------------------------


class _FakeResp:
    status = 200

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _FakeSession:
    """Pengganti aiohttp.ClientSession — tidak ada HTTP sungguhan."""

    posted = None

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def post(self, url, json=None, headers=None, timeout=None):
        _FakeSession.posted = {"url": url, "json": json, "headers": headers}
        return _FakeResp()

    def get(self, url, headers=None, timeout=None):
        _FakeSession.posted = {"url": url, "headers": headers}
        return _FakeResp()


def test_push_snapshot_satu_guild_gagal_guild_lain_tetap_terkirim(monkeypatch):
    """KRITIS (audit4): _snapshot_guild yang raise untuk satu guild tidak
    boleh membunuh loop push 5-menit — guild lain tetap terkirim."""
    monkeypatch.setattr(ds.aiohttp, "ClientSession", _FakeSession)
    _FakeSession.posted = None
    cog = ds.DashboardSync.__new__(ds.DashboardSync)
    cog._jalan = True
    cog.bot = Mock()
    cog.bot.user = None
    g_rusak, g_bagus = Mock(), Mock()
    g_rusak.id, g_bagus.id = 111, 222

    def fake_snapshot(g):
        if g.id == 111:
            raise RuntimeError("DB error simulasi")
        return {"id": "222", "name": "Bagus"}

    cog._snapshot_guild = fake_snapshot
    _jalan(cog._kirim_snapshot([g_rusak, g_bagus], "test"))
    assert _FakeSession.posted is not None
    assert _FakeSession.posted["url"].endswith("/api/ingest")
    guilds = _FakeSession.posted["json"]["guilds"]
    assert len(guilds) == 1 and guilds[0]["id"] == "222"


def test_ack_status_hanya_done_atau_failed():
    """Syarat dashboard: ack hanya boleh 'done'/'failed' (status lain = 400).

    Verifikasi statis: setiap call site _ack_giveaway/_ack_embed di
    dashboard_sync.py memakai literal done/failed (atau IfExp keduanya).
    """
    tree = ast.parse((SRC / "cogs" / "dashboard_sync.py").read_text())

    def _ok(node):
        if isinstance(node, ast.Constant):
            return node.value in ("done", "failed")
        if isinstance(node, ast.IfExp):
            return _ok(node.body) and _ok(node.orelse)
        return False

    sites = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in ("_ack_giveaway", "_ack_embed"):
                sites += 1
                assert _ok(node.args[2]), (
                    f"status ack tak dikenal di {node.func.attr}: "
                    f"{ast.dump(node.args[2])}"
                )
    assert sites >= 6, "call site ack berubah drastis — periksa manual"


def test_ack_giveaway_tanpa_req_id_tidak_mengirim_http(monkeypatch):
    """req_id None (payload dashboard rusak) tidak boleh POST ke
    .../giveaway-requests/None."""
    calls = []

    class _Boom:
        def __init__(self, *a, **k):
            calls.append(1)
            raise AssertionError("HTTP tidak boleh dipanggil")

    monkeypatch.setattr(ds.aiohttp, "ClientSession", _Boom)
    _jalan(ds.DashboardSync._ack_giveaway(object(), 123, None, "done", ""))
    assert calls == []


def test_modul_aktif_default_nyala(db_tmp):
    gid = 888001
    with store.get_connection() as conn:
        conn.execute("DELETE FROM dashboard_settings WHERE guild_id = ?", (gid,))
        conn.commit()
    assert ds.modul_aktif(gid, "responder_enabled") is True
    assert ds.get_guild_setting_int(gid, "x", 7) == 7
    with store.get_connection() as conn:
        conn.execute(
            "INSERT INTO dashboard_settings (guild_id, key, value) VALUES (?, ?, ?)",
            (gid, "responder_enabled", "0"),
        )
        conn.execute(
            "INSERT INTO dashboard_settings (guild_id, key, value) VALUES (?, ?, ?)",
            (gid, "jelek", "bukan-angka"),
        )
        conn.commit()
    try:
        assert ds.modul_aktif(gid, "responder_enabled") is False
        assert ds.get_guild_setting_int(gid, "jelek", 7) == 7
    finally:
        with store.get_connection() as conn:
            conn.execute("DELETE FROM dashboard_settings WHERE guild_id = ?", (gid,))
            conn.commit()


def test_parse_id_list():
    assert ds.parse_id_list("123, 456, abc") == [123, 456]
    assert ds.parse_id_list(None) == []
    assert ds.parse_id_list("") == []


def test_bangun_embed_kosong_ditolak():
    assert ds._bangun_embed({}) is None
    assert ds._bangun_embed({"title": "  ", "description": ""}) is None


def test_bangun_embed_warna_invalid_jatuh_ke_brand():
    from src.utils.embeds import BRAND

    e = ds._bangun_embed({"title": "Halo", "color": "bukan-warna"})
    assert e is not None and e.color == BRAND
    e2 = ds._bangun_embed({"title": "Halo", "color": "#ff0000"})
    assert e2.color == discord.Color(0xFF0000)


def test_emoji_cocok():
    assert ds.emoji_cocok("👍", discord.PartialEmoji(name="👍"))
    assert not ds.emoji_cocok("👎", discord.PartialEmoji(name="👍"))
    assert ds.emoji_cocok("123", discord.PartialEmoji(name="x", id=123))
    assert not ds.emoji_cocok("", discord.PartialEmoji(name="👍"))


def test_substitusi_pengumuman():
    now = datetime.datetime(2026, 10, 10, tzinfo=datetime.timezone.utc)
    hasil = ds.substitusi_pengumuman(
        "Halo {server}, {date}, member {member_count}", "Kita", now, 42
    )
    assert hasil == "Halo Kita, 10 Oct 2026, member 42"


# ---------------------------------------------------------------------------
# bot inti: mention policy & error handler
# ---------------------------------------------------------------------------


def test_mentions_aman_deny_by_default():
    assert MENTIONS_AMAN.everyone is False
    assert MENTIONS_AMAN.users is True
    # MENTIONS_PENGUMUMAN memang mengizinkan everyone — tapi hanya dipakai
    # eksplisit untuk konten yang ditulis admin/mod.
    assert MENTIONS_PENGUMUMAN.everyone is True


def test_config_dashboard_url_tanpa_trailing_slash(monkeypatch):
    from src import config as cfg_mod

    monkeypatch.setenv("DASHBOARD_URL", "https://dash.example.com/")
    monkeypatch.setenv("DASHBOARD_SECRET", "rahasia")
    s = cfg_mod.Settings()
    assert s.dashboard_url == "https://dash.example.com"
    assert s.dashboard_secret == "rahasia"
    monkeypatch.delenv("DASHBOARD_URL", raising=False)
    monkeypatch.delenv("DASHBOARD_SECRET", raising=False)
    assert cfg_mod.Settings().dashboard_secret == ""  # default kosong, bukan hardcode


# ---------------------------------------------------------------------------
# Keamanan mention di command user-facing (tidak boleh nge-ping orang/role
# yang tidak terkait)
# ---------------------------------------------------------------------------


def test_teks_roles_member_tanpa_mention():
    member = SimpleNamespace(
        roles=[
            SimpleNamespace(name="@everyone"),
            SimpleNamespace(name="Admin", mention="<@&1>"),
            SimpleNamespace(name="Mabar", mention="<@&2>"),
        ]
    )
    hasil = teks_roles_member(member)
    assert "<@" not in hasil and "<@&" not in hasil
    assert "Admin" in hasil and "Mabar" in hasil


def test_nama_member_atau_id():
    assert nama_member_atau_id(None, 5) == "ID 5"
    guild = Mock()
    guild.get_member.return_value = None
    assert nama_member_atau_id(guild, 5) == "ID 5"
    guild.get_member.return_value = SimpleNamespace(display_name="Budi")
    assert nama_member_atau_id(guild, 5) == "Budi"


def test_build_serverinfo_tanpa_mention():
    guild = SimpleNamespace(
        name="Server Kita",
        icon=None,
        id=1,
        created_at=datetime.datetime(2020, 1, 1),
        owner=SimpleNamespace(display_name="Si Bos", mention="<@99>"),
        member_count=10,
        members=[],
        roles=[],
        emojis=[],
        text_channels=[],
        voice_channels=[],
        premium_tier=0,
        premium_subscription_count=0,
        filesize_limit=8 * 1048576,
    )
    embed = build_serverinfo_embed(guild)
    for f in embed.fields:
        assert "<@" not in f.value, f"field {f.name} me-mention!"
    owner_field = next(f for f in embed.fields if f.name == "Owner")
    assert owner_field.value == "Si Bos"


def test_substitusi_variabel_netralkan_mass_mention():
    # Nilai substitusi (nama server, dsb.) yang berisi @everyone/@here
    # tidak boleh memicu mass-ping.
    hasil = substitusi_variabel(
        "Halo {user}, selamat datang di {server}!",
        user="<@1>",
        server="@everyone",
    )
    assert "@everyone" not in hasil
    assert "@\u200beveryone" in hasil
    hasil2 = substitusi_variabel("Warga {server}", server="@here")
    assert "@here" not in hasil2
    assert "@\u200bhere" in hasil2
    # Template milik admin yang memang berisi @everyone tetap utuh
    # (itu disengaja — konten admin dikirim dengan MENTIONS_PENGUMUMAN).
    hasil3 = substitusi_variabel("@everyone rapat {server}", server="Kita")
    assert hasil3.startswith("@everyone rapat Kita")


# ---------------------------------------------------------------------------
# Scheduler: satu error tidak membunuh loop
# ---------------------------------------------------------------------------


def test_cek_event_channel_bukan_teks_dilewati_tanpa_crash(db_tmp):
    """events.cek_event: channel_id yang menunjuk ke kategori/forum
    (tak punya .send -> AttributeError) tidak boleh membunuh loop 5-menit."""
    cog = ev_mod.Events.__new__(ev_mod.Events)
    bot = Mock()
    kategori = Mock(spec=discord.CategoryChannel)  # spec: tak punya .send
    bot.get_channel = Mock(return_value=kategori)
    cog.bot = bot
    now = datetime.datetime.now(datetime.timezone.utc)
    kapan = (now + datetime.timedelta(minutes=30)).isoformat()
    with store.get_connection() as conn:
        conn.execute(
            "INSERT INTO events (guild_id, channel_id, message_id, nama, kapan, deskripsi)"
            " VALUES (1, 555, 666, 'Mabar', ?, '')",
            (kapan,),
        )
        conn.commit()
    try:
        _jalan(cog.cek_event.coro(cog))  # satu iterasi loop — tidak boleh raise
        with store.get_connection() as conn:
            row = conn.execute(
                "SELECT notif_terkirim FROM events WHERE guild_id = 1"
            ).fetchone()
        assert row[0] == 0  # dilewati, bukan ditandai terkirim
    finally:
        with store.get_connection() as conn:
            conn.execute("DELETE FROM events WHERE guild_id = 1")
            conn.commit()


def test_cek_event_happy_path_menandai_terkirim(db_tmp):
    cog = ev_mod.Events.__new__(ev_mod.Events)
    bot = Mock()
    teks = Mock(spec=discord.TextChannel)
    teks.send = AsyncMock(return_value=Mock(id=777))
    bot.get_channel = Mock(return_value=teks)
    cog.bot = bot
    now = datetime.datetime.now(datetime.timezone.utc)
    kapan = (now + datetime.timedelta(minutes=30)).isoformat()
    with store.get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO events (guild_id, channel_id, message_id, nama, kapan, deskripsi)"
            " VALUES (2, 556, 667, 'Mabar', ?, '')",
            (kapan,),
        )
        conn.commit()
        eid = cur.lastrowid
    _jalan(cog.cek_event.coro(cog))
    with store.get_connection() as conn:
        row = conn.execute(
            "SELECT notif_terkirim FROM events WHERE id = ?", (eid,)
        ).fetchone()
        conn.execute("DELETE FROM events WHERE id = ?", (eid,))
        conn.commit()
    assert row[0] == 1
    teks.send.assert_awaited_once()


# ---------------------------------------------------------------------------
# tempvc: cooldown tidak bocor memori
# ---------------------------------------------------------------------------


def test_buang_cooldown_kedaluwarsa():
    import time

    _vc_cooldown.clear()
    _vc_cooldown[(1, 10)] = time.time() - 400  # kedaluwarsa
    _vc_cooldown[(1, 11)] = time.time()  # masih segar
    assert buang_cooldown_kedaluwarsa() == 1
    assert (1, 10) not in _vc_cooldown
    assert (1, 11) in _vc_cooldown
    _vc_cooldown.clear()


# ---------------------------------------------------------------------------
# responder: validasi panjang input
# ---------------------------------------------------------------------------


def test_respon_add_validasi_panjang(db_tmp, monkeypatch):
    from src.cogs import responder as resp_mod

    async def _no_mirror(*a, **k):
        return None

    monkeypatch.setattr(resp_mod, "_mirror_dashboard", _no_mirror)
    cog = resp_mod.Responder(bot=None)

    def _ctx():
        ctx = Mock()
        ctx.guild = SimpleNamespace(id=777002)
        ctx.send = AsyncMock()
        return ctx

    cb = resp_mod.Responder.respon_add.callback
    ctx = _ctx()
    _jalan(cb(cog, ctx, "x" * 101, respons="ok"))
    pesan = ctx.send.await_args_list[0].args[0]
    assert "100" in pesan

    ctx = _ctx()
    _jalan(cb(cog, ctx, "halo", respons="y" * 1501))
    pesan = ctx.send.await_args_list[0].args[0]
    assert "1500" in pesan

    ctx = _ctx()
    _jalan(cb(cog, ctx, "halo", respons="Hai {user}!"))
    pesan = ctx.send.await_args_list[0].args[0]
    assert pesan.startswith("✅")
    with store.get_connection() as conn:
        row = conn.execute(
            "SELECT respons FROM autoresponder WHERE guild_id = ? AND trigger = ?",
            (777002, "halo"),
        ).fetchone()
        conn.execute("DELETE FROM autoresponder WHERE guild_id = ?", (777002,))
        conn.commit()
    assert row[0] == "Hai {user}!"


def test_cari_respons():
    from src.cogs.responder import cari_respons

    daftar = [("ip mabar", "IP: 1.2.3.4"), ("jadwal", "Jumat")]
    assert cari_respons(daftar, "minta IP MABAR dong") == "IP: 1.2.3.4"
    assert cari_respons(daftar, "halo") is None
    assert cari_respons([], "halo") is None


# ---------------------------------------------------------------------------
# achievement: cap 25 field
# ---------------------------------------------------------------------------


def test_field_achievement_maks_25():
    daftar = [(f"k{i}", f"Badge {i}", "t") for i in range(30)]
    terkunci = [f"h{i}" for i in range(10)]
    fields = field_achievement(daftar, terkunci)
    assert len(fields) <= 25
    assert any("+10 lainnya" in n for n, _ in fields)
    assert field_achievement([], []) == []
    kecil = field_achievement([("a", "A", "t")], ["h1"])
    assert kecil == [("A", "✅"), ("???", "🔒")]


# ---------------------------------------------------------------------------
# general: /bantuan coverage & helper
# ---------------------------------------------------------------------------


def test_cog_ke_kategori_mencakup_semua_cog():
    """Komentar di general.py: COG_KE_KATEGORI WAJIB mencakup semua cog."""
    kelas = {}
    for f in sorted(SRC.glob("cogs/*.py")):
        if f.name == "__init__.py":
            continue
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                if any("Cog" in ast.unparse(b) for b in node.bases):
                    kelas[node.name] = f.name
    tak_peta = set(kelas) - set(COG_KE_KATEGORI)
    yatim = set(COG_KE_KATEGORI) - set(kelas)
    assert not tak_peta, f"cog tak terpetakan di /bantuan: {tak_peta}"
    assert not yatim, f"mapping yatim: {yatim}"


def test_bangun_data_bantuan_cache():
    tree = Mock()
    tree.get_commands.return_value = []
    d1 = bangun_data_bantuan(tree)
    d2 = bangun_data_bantuan(tree)
    assert d1 is d2  # cache dipakai bila jumlah sama


def test_baris_perintah_dipotong():
    baris = _baris_perintah("/x", "d" * 200)
    # "`/x` — " (7 char) + 90 char deskripsi + "…" = 98
    assert len(baris) == 7 + 90 + 1
    assert baris.endswith("…")
    assert _baris_perintah("/x", "") == "`/x`"


def test_bagi_ke_field_batas():
    baris = [f"baris-{i}-" + "x" * 100 for i in range(30)]
    fields = _bagi_ke_field(baris)
    assert len(fields) > 1
    for f in fields:
        assert sum(len(b) + 1 for b in f) <= 950 + 101


# ---------------------------------------------------------------------------
# store: validator identifier DDL
# ---------------------------------------------------------------------------


def test_ident_aman_menolak_injeksi():
    assert store._IDENT_AMAN.match("users")
    assert store._IDENT_AMAN.match("_tabel1")
    assert not store._IDENT_AMAN.match("users; DROP TABLE x--")
    assert not store._IDENT_AMAN.match("1abc")
    assert not store._IDENT_AMAN.match("a-b")


def test_definisi_aman_menolak_injeksi():
    assert store._DEFINISI_AMAN.match("INTEGER DEFAULT 0")
    assert store._DEFINISI_AMAN.match("TEXT DEFAULT 'umum'")
    assert not store._DEFINISI_AMAN.match("INTEGER; DROP TABLE users--")
    assert not store._DEFINISI_AMAN.match("TEXT); DELETE FROM users;--")


def test_init_db_idempoten(db_tmp):
    """init_db dua kali beruntun tidak boleh error (IF NOT EXISTS + guard kolom)."""
    store.init_db()
    store.init_db()
    with store.get_connection() as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for wajib in ("users", "dashboard_announcements", "mod_actions", "autoresponder"):
        assert wajib in tables


# ---------------------------------------------------------------------------
# util murni lain di area
# ---------------------------------------------------------------------------


def test_parse_rss_youtube():
    from src.cogs.youtube import parse_rss

    assert parse_rss("bukan xml") == []
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom"
          xmlns:yt="http://www.youtube.com/xml/schemas/2015">
      <entry><yt:videoId>abc123</yt:videoId><title>Judul</title>
      <published>2026-10-01T00:00:00+00:00</published></entry>
      <entry><title>Tanpa ID</title></entry>
    </feed>"""
    hasil = parse_rss(xml)
    assert len(hasil) == 1 and hasil[0]["videoId"] == "abc123"


def test_format_interval_reminder():
    from src.cogs.reminders import _format_interval

    assert _format_interval(3600) == "1 jam"
    assert _format_interval(90000) == "1 hari 1 jam"
    assert _format_interval(0) == "0 menit"


def test_ambil_jatuh_tempo(db_tmp):
    from src.cogs.reminders import ambil_jatuh_tempo

    now = datetime.datetime.now(datetime.timezone.utc)
    lampau = (now - datetime.timedelta(minutes=1)).isoformat()
    depan = (now + datetime.timedelta(hours=1)).isoformat()
    with store.get_connection() as conn:
        conn.execute(
            "INSERT INTO reminders (user_id, guild_id, channel_id, message, remind_at)"
            " VALUES (1, 1, 1, 'a', ?)",
            (lampau,),
        )
        conn.execute(
            "INSERT INTO reminders (user_id, guild_id, channel_id, message, remind_at)"
            " VALUES (1, 1, 1, 'b', ?)",
            (depan,),
        )
        conn.commit()
        rows = ambil_jatuh_tempo(conn, now.isoformat())
        conn.execute("DELETE FROM reminders")
        conn.commit()
    assert [r[3] for r in rows] == ["a"]


def test_cek_hitungan():
    from src.cogs.counting import cek_hitungan

    assert cek_hitungan("5", 4, 10, 11) == (True, "")
    assert cek_hitungan("6", 4, 10, 11)[0] is False
    assert cek_hitungan("abc", 4, 10, 11) == (False, "bukan angka")
    assert cek_hitungan("5", 4, 11, 11)[0] is False  # 2x beruntun


def test_format_balas_afk_tanpa_mention_mentah():
    from src.cogs.afk import format_balas_afk

    teks = format_balas_afk("Budi", "makan @everyone dulu", "2026-10-10T00:00:00+00:00")
    assert "Budi" in teks and "makan" in teks
    # alasan AFK dikirim dengan AllowedMentions.none() di cog — pastikan
    # fungsi formatnya sendiri tidak menambahkan mention user
    assert "<@" not in teks


def test_parse_waktu_event():
    assert ev_mod.parse_waktu_event("25-12-2026 19:00") is not None
    assert ev_mod.parse_waktu_event("salah") is None
    dt = ev_mod.parse_waktu_event("25-12-2026 19:00")
    assert dt.utcoffset() == datetime.timedelta(0)  # dinormalisasi ke UTC


def test_fmt_interval_dan_bucket():
    from src.cogs.utilitas import _bucket_distribusi, _fmt_interval, _jatuh_tempo

    assert _fmt_interval(604800) == "7 hari"
    assert _fmt_interval(90) == "90 detik"
    buckets = _bucket_distribusi([1, 3, 7, 50])
    assert buckets[0] == ("Lv 1–5", 2)
    assert buckets[9] == ("Lv 46–50", 1)
    now = datetime.datetime.now(datetime.timezone.utc)
    assert _jatuh_tempo(None, 60, now) is True
    assert _jatuh_tempo("rusak", 60, now) is True
    assert _jatuh_tempo((now - datetime.timedelta(seconds=120)).isoformat(), 60, now) is True
    assert _jatuh_tempo((now - datetime.timedelta(seconds=10)).isoformat(), 60, now) is False


def test_render_dashboard_html_escape():
    from src.cogs.utilitas import _render_dashboard_html

    html = _render_dashboard_html("<b>Bot</b>", [("<i>G</i>", 5)], [], [])
    assert "<b>Bot</b>" not in html and "&lt;b&gt;Bot&lt;/b&gt;" in html
    assert "&lt;i&gt;G&lt;/i&gt;" in html
