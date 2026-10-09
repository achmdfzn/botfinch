"""Test wiring dashboard: embed_requests, announcements, mod_actions/modlog."""
import dataclasses
from unittest.mock import MagicMock

import discord

from src import config
from src.cogs.dashboard_sync import (
    TABEL_ANNOUNCEMENTS,
    DashboardSync,
    _bangun_embed,
    _int_aman,
    _parse_warna,
)
from src.store import get_connection, init_db
from src.utils import modactions
from src.utils.embeds import BRAND

init_db()  # seperti saat bot startup
with get_connection() as _c:
    _c.execute(TABEL_ANNOUNCEMENTS)
    _c.commit()


def _cog():
    return DashboardSync(MagicMock())


def _bersih_ann(gid: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM dashboard_announcements WHERE guild_id = ?", (str(gid),))
        conn.commit()


def _bersih_mod(gid: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM mod_actions WHERE guild_id = ?", (str(gid),))
        conn.commit()


def _dashboard_mati(monkeypatch):
    # Settings frozen -> ganti objeknya, bukan atributnya
    monkeypatch.setattr(
        config, "settings",
        dataclasses.replace(config.settings, dashboard_url="", dashboard_secret=""),
    )


def _dashboard_nyala(monkeypatch):
    monkeypatch.setattr(
        config, "settings",
        dataclasses.replace(
            config.settings, dashboard_url="http://dash.test", dashboard_secret="s3cr3t"),
    )


# ---------- _parse_warna ----------

def test_parse_warna_valid():
    assert _parse_warna("ff0000") == discord.Color(0xFF0000)
    assert _parse_warna("#00ff00") == discord.Color(0x00FF00)
    assert _parse_warna("0") == discord.Color(0)


def test_parse_warna_invalid():
    assert _parse_warna(None) is None
    assert _parse_warna("") is None
    assert _parse_warna("bukan-warna") is None
    assert _parse_warna("1000000") is None  # > 0xFFFFFF
    assert _parse_warna("#") is None


# ---------- _bangun_embed ----------

def test_bangun_embed_full():
    e = _bangun_embed({
        "title": "Halo",
        "description": "Deskripsi",
        "color": "ff0000",
        "fields": [
            {"name": "A", "value": "B", "inline": True},
            {"name": "", "value": "kosong-dilewati"},
            {"rusak": True},
        ],
        "footer": "kaki",
        "image_url": "https://x.test/i.png",
        "thumbnail_url": "https://x.test/t.png",
    })
    assert isinstance(e, discord.Embed)
    assert e.title == "Halo"
    assert e.description == "Deskripsi"
    assert e.color == discord.Color(0xFF0000)
    assert len(e.fields) == 1  # field kosong/rusak dilewati
    assert e.fields[0].name == "A" and e.fields[0].value == "B"
    assert e.fields[0].inline is True
    assert e.footer.text == "kaki"
    assert e.image.url == "https://x.test/i.png"
    assert e.thumbnail.url == "https://x.test/t.png"


def test_bangun_embed_kosong():
    assert _bangun_embed({}) is None
    assert _bangun_embed({"title": "   ", "description": ""}) is None


def test_bangun_embed_warna_invalid_tetap_terkirim():
    # Warna invalid/kosong -> fallback warna brand Finch (konsisten UI).
    e = _bangun_embed({"title": "T", "color": "ngaco"})
    assert isinstance(e, discord.Embed)
    assert e.color == BRAND
    e2 = _bangun_embed({"title": "T"})
    assert isinstance(e2, discord.Embed)
    assert e2.color == BRAND
    # Warna valid dari dashboard tetap dipakai.
    e3 = _bangun_embed({"title": "T", "color": "ff0000"})
    assert e3.color == discord.Color(0xFF0000)


def test_bangun_embed_batas_field():
    e = _bangun_embed({
        "title": "T",
        "fields": [{"name": f"n{i}", "value": "v"} for i in range(40)],
    })
    assert len(e.fields) == 25


def test_int_aman():
    assert _int_aman("123") == 123
    assert _int_aman(None) == 0
    assert _int_aman("ngaco") == 0
    assert _int_aman("ngaco", 7) == 7


# ---------- _simpan_pengumuman (mirror) ----------

def test_simpan_pengumuman_mirror():
    gid = 991001
    _bersih_ann(gid)
    cog = _cog()
    try:
        cog._simpan_pengumuman(gid, [
            {"id": 1, "channel_id": "111", "message": "sekali",
             "run_at": "2026-10-09T00:00:00+00:00", "enabled": True},
            {"id": 2, "channel_id": "222", "message": "rutin",
             "interval_minutes": 60, "enabled": 1},
            {"id": 3, "channel_id": "333", "message": "   "},  # kosong -> lewati
            {"id": 4},  # tanpa message -> lewati
        ])
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT id, channel_id, message, run_at, interval_minutes, enabled, last_sent_at"
                " FROM dashboard_announcements WHERE guild_id = ? ORDER BY id",
                (str(gid),),
            ).fetchall()
        assert len(rows) == 2
        assert rows[0][0] == 1 and rows[0][2] == "sekali"
        assert rows[0][3] == "2026-10-09T00:00:00+00:00"  # run_at dinormalisasi
        assert rows[0][4] is None and rows[0][5] == 1
        assert rows[1][0] == 2 and rows[1][4] == 60
        # mirror: pull kedua mengganti total (hapus via web ikut berlaku)
        cog._simpan_pengumuman(gid, [{"id": 9, "channel_id": "999", "message": "baru"}])
        with get_connection() as conn:
            ids = [r[0] for r in conn.execute(
                "SELECT id FROM dashboard_announcements WHERE guild_id = ?", (str(gid),))]
        assert ids == [9]
    finally:
        _bersih_ann(gid)


# ---------- modactions.catat_mod_action ----------

def test_catat_mod_action_mati_tanpa_dashboard(monkeypatch):
    _dashboard_mati(monkeypatch)
    gid = 991002
    _bersih_mod(gid)
    modactions.catat_mod_action(gid, 1, 2, "warn", "tes")
    with get_connection() as conn:
        n = conn.execute(
            "SELECT COUNT(*) FROM mod_actions WHERE guild_id = ?", (str(gid),)).fetchone()[0]
    assert n == 0


def test_catat_mod_action_tulis(monkeypatch):
    _dashboard_nyala(monkeypatch)
    gid = 991003
    _bersih_mod(gid)
    try:
        modactions.catat_mod_action(gid, 111, 222, "mute", "auto-mute: spam")
        with get_connection() as conn:
            row = conn.execute(
                "SELECT user_id, mod_id, aksi, alasan, waktu FROM mod_actions"
                " WHERE guild_id = ?", (str(gid),)).fetchone()
        assert row[0] == "111" and row[1] == "222"
        assert row[2] == "mute" and row[3] == "auto-mute: spam"
        assert row[4]  # waktu ISO terisi
    finally:
        _bersih_mod(gid)


def test_modlog_guild_nama_fallback(monkeypatch):
    _dashboard_nyala(monkeypatch)
    gid = 991004
    _bersih_mod(gid)
    try:
        modactions.catat_mod_action(gid, 555, 666, "warn", "tes")
        guild = MagicMock()
        guild.id = gid
        guild.get_member.return_value = None  # member tidak di-cache
        # _modlog_guild tidak butuh instance jalan -> panggil unbound
        hasil = DashboardSync._modlog_guild(None, guild)
        assert len(hasil) == 1
        assert hasil[0]["aksi"] == "warn"
        assert hasil[0]["user_name"] == "555"  # fallback ke ID
        assert hasil[0]["mod_name"] == "666"
        assert hasil[0]["waktu"]
    finally:
        _bersih_mod(gid)


def test_cog_mati_tanpa_dashboard(monkeypatch):
    _dashboard_mati(monkeypatch)
    cog = _cog()
    assert cog._jalan is False
    assert not cog.push_snapshot.is_running()
    assert not cog.pull_settings.is_running()
    assert not cog.kirim_pengumuman.is_running()
