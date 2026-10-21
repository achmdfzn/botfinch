"""Regresi audit P1 (lanjutan audit 5): isolasi guild + tipe channel di semua
jalur kirim, jadwal pengumuman, rekonsiliasi ack, dan kontrak get_connection.

Kontrak yang dijaga:
- Channel dari payload dashboard / setting per-guild hanya dipakai bila
  milik guild yang diproses DAN bertipe bisa-kirim-pesan (teks/news/thread).
  Voice/kategori/lintas-guild ditolak TANPA side effect (send tidak terpanggil).
- Welcome & goodbye jatuh ke system channel bila channel terkonfigurasi
  milik guild lain atau bukan channel teks.
- Pengumuman satu-kali tidak terkirim sebelum waktunya; interval menghormati
  last_sent_at; kegagalan ack TIDAK menghapus timestamp lokal.
- Rekonsiliasi mengirim ulang ack hanya bila lokal lebih baru dari remote.
- get_connection(): koneksi tertutup setelah blok, commit saat sukses,
  rollback saat exception.
"""
import asyncio
import datetime as dt
import io
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src import store
from src.cogs import dashboard_sync as ds

GID = 12345
GUILD_LAIN = 99999
CH_TEKS = 555001
SEKARANG = dt.datetime(2026, 10, 22, 12, 0, tzinfo=dt.timezone.utc)


@pytest.fixture()
def db_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "finch-audit6.db")
    store.init_db()
    with store.get_connection() as conn:
        conn.execute(ds.TABEL_SETTINGS)
        conn.execute(ds.TABEL_ANNOUNCEMENTS)
        conn.commit()


def _set_setting(key: str, value: str) -> None:
    with store.get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO dashboard_settings (guild_id, key, value)"
            " VALUES (?, ?, ?)",
            (str(GID), key, value),
        )
        conn.commit()


def _channel(gid=GID, tipe=0):
    return SimpleNamespace(
        guild=SimpleNamespace(id=gid), type=tipe, send=AsyncMock()
    )


def _guild(channel, gid=GID):
    return SimpleNamespace(
        id=gid,
        name="Server Uji",
        member_count=42,
        get_channel=lambda cid: channel if cid == CH_TEKS else None,
    )


def _cog(bot):
    cog = ds.DashboardSync.__new__(ds.DashboardSync)
    cog.bot = bot
    return cog


# ---------- helper: tipe channel ----------

def test_helper_menolak_tipe_non_teks_di_guild_yang_sama():
    assert not ds._channel_milik_guild(_channel(tipe=2), GID)   # voice
    assert not ds._channel_milik_guild(_channel(tipe=4), GID)   # kategori
    assert not ds._channel_milik_guild(_channel(tipe=13), GID)  # stage
    assert not ds._channel_milik_guild(_channel(tipe=15), GID)  # forum


def test_helper_menerima_news_dan_thread():
    assert ds._channel_milik_guild(_channel(tipe=5), GID)   # news
    assert ds._channel_milik_guild(_channel(tipe=11), GID)  # public thread


def test_helper_menolak_tipe_yang_tidak_dapat_ditentukan():
    tanpa_tipe = SimpleNamespace(guild=SimpleNamespace(id=GID))
    assert not ds._channel_milik_guild(tanpa_tipe, GID)


# ---------- jalur embed: tanpa side effect bila ditolak ----------

def _permintaan_embed():
    return [{
        "id": 7,
        "channel_id": CH_TEKS,
        "title": "Halo",
        "description": "Isi embed",
        "color": "2EC4B6",
        "fields": [],
    }]


@pytest.mark.usefixtures("db_tmp")
def test_embed_channel_guild_lain_ditolak_tanpa_kirim():
    channel = _channel(gid=GUILD_LAIN)
    cog = _cog(SimpleNamespace(fetch_channel=AsyncMock()))
    cog._ack_embed = AsyncMock()
    asyncio.run(cog._proses_embed(_guild(channel), _permintaan_embed()))
    channel.send.assert_not_called()
    cog._ack_embed.assert_awaited_once()
    assert cog._ack_embed.call_args.args[2] == "failed"


@pytest.mark.usefixtures("db_tmp")
def test_embed_channel_voice_ditolak_tanpa_kirim():
    channel = _channel(tipe=2)
    cog = _cog(SimpleNamespace(fetch_channel=AsyncMock()))
    cog._ack_embed = AsyncMock()
    asyncio.run(cog._proses_embed(_guild(channel), _permintaan_embed()))
    channel.send.assert_not_called()
    cog._ack_embed.assert_awaited_once()
    assert cog._ack_embed.call_args.args[2] == "failed"


@pytest.mark.usefixtures("db_tmp")
def test_embed_channel_teks_valid_terkirim():
    channel = _channel()
    cog = _cog(SimpleNamespace(fetch_channel=AsyncMock()))
    cog._ack_embed = AsyncMock()
    asyncio.run(cog._proses_embed(_guild(channel), _permintaan_embed()))
    channel.send.assert_awaited_once()
    assert cog._ack_embed.call_args.args[2] == "done"


# ---------- jalur giveaway: tanpa side effect bila ditolak ----------

def _permintaan_giveaway():
    return [{
        "id": 3,
        "channel_id": CH_TEKS,
        "duration_minutes": 5,
        "winners": 1,
        "prize": "Nitro",
    }]


def _bot_giveaway(cog_giveaway):
    return SimpleNamespace(
        get_cog=lambda nama: cog_giveaway,
        user=SimpleNamespace(id=999),
        fetch_channel=AsyncMock(),
    )


@pytest.mark.usefixtures("db_tmp")
def test_giveaway_channel_guild_lain_ditolak_tanpa_posting():
    channel = _channel(gid=GUILD_LAIN)
    gw = SimpleNamespace(posting_giveaway=AsyncMock(return_value=1))
    cog = _cog(_bot_giveaway(gw))
    cog._ack_giveaway = AsyncMock()
    asyncio.run(cog._proses_giveaway(_guild(channel), _permintaan_giveaway()))
    gw.posting_giveaway.assert_not_called()
    assert cog._ack_giveaway.call_args.args[2] == "failed"


@pytest.mark.usefixtures("db_tmp")
def test_giveaway_channel_kategori_ditolak_tanpa_posting():
    channel = _channel(tipe=4)
    gw = SimpleNamespace(posting_giveaway=AsyncMock(return_value=1))
    cog = _cog(_bot_giveaway(gw))
    cog._ack_giveaway = AsyncMock()
    asyncio.run(cog._proses_giveaway(_guild(channel), _permintaan_giveaway()))
    gw.posting_giveaway.assert_not_called()
    assert cog._ack_giveaway.call_args.args[2] == "failed"


@pytest.mark.usefixtures("db_tmp")
def test_giveaway_channel_teks_valid_diposting():
    channel = _channel()
    gw = SimpleNamespace(posting_giveaway=AsyncMock(return_value=123456))
    cog = _cog(_bot_giveaway(gw))
    cog._ack_giveaway = AsyncMock()
    asyncio.run(cog._proses_giveaway(_guild(channel), _permintaan_giveaway()))
    gw.posting_giveaway.assert_awaited_once()
    assert cog._ack_giveaway.call_args.args[2] == "done"


# ---------- jalur pengumuman terjadwal ----------

def _sisip_pengumuman(last_sent_at=None):
    with store.get_connection() as conn:
        conn.execute(
            "INSERT INTO dashboard_announcements "
            "(id, guild_id, channel_id, message, run_at, interval_minutes, enabled, last_sent_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (9, str(GID), str(CH_TEKS), "Halo {server}", None, None, 1, last_sent_at),
        )
        conn.commit()


def _cog_pengumuman(channel):
    guild = _guild(channel)
    bot = SimpleNamespace(
        get_guild=lambda gid: guild, fetch_channel=AsyncMock(return_value=None)
    )
    cog = _cog(bot)
    cog._ack_announcement = AsyncMock(return_value=True)
    return cog


def _last_sent_db():
    with store.get_connection() as conn:
        row = conn.execute(
            "SELECT last_sent_at FROM dashboard_announcements WHERE id = 9"
        ).fetchone()
    return row[0] if row else None


@pytest.mark.usefixtures("db_tmp")
def test_pengumuman_satu_kali_belum_waktunya_tidak_terkirim():
    _sisip_pengumuman()
    channel = _channel()
    cog = _cog_pengumuman(channel)
    asyncio.run(cog._kirim_satu_pengumuman(
        SEKARANG, 9, str(GID), str(CH_TEKS), "Halo {server}",
        "2026-10-22T13:00:00+00:00", None, None,
    ))
    channel.send.assert_not_called()


@pytest.mark.usefixtures("db_tmp")
def test_pengumuman_interval_belum_lewat_tidak_terkirim():
    terakhir = "2026-10-22T11:30:00+00:00"
    _sisip_pengumuman(last_sent_at=terakhir)
    channel = _channel()
    cog = _cog_pengumuman(channel)
    asyncio.run(cog._kirim_satu_pengumuman(
        SEKARANG, 9, str(GID), str(CH_TEKS), "Halo {server}", None, 60, terakhir,
    ))
    channel.send.assert_not_called()


@pytest.mark.usefixtures("db_tmp")
def test_pengumuman_interval_sudah_lewat_terkirim_sesuai_jadwal():
    terakhir = "2026-10-22T10:59:00+00:00"
    _sisip_pengumuman(last_sent_at=terakhir)
    channel = _channel()
    cog = _cog_pengumuman(channel)
    asyncio.run(cog._kirim_satu_pengumuman(
        SEKARANG, 9, str(GID), str(CH_TEKS), "Halo {server}", None, 60, terakhir,
    ))
    channel.send.assert_awaited_once()


@pytest.mark.usefixtures("db_tmp")
def test_pengumuman_channel_guild_lain_tidak_terkirim():
    _sisip_pengumuman()
    channel = _channel(gid=GUILD_LAIN)
    cog = _cog_pengumuman(channel)
    asyncio.run(cog._kirim_satu_pengumuman(
        SEKARANG, 9, str(GID), str(CH_TEKS), "Halo {server}",
        "2026-10-22T11:00:00+00:00", None, None,
    ))
    channel.send.assert_not_called()


@pytest.mark.usefixtures("db_tmp")
def test_pengumuman_channel_voice_tidak_terkirim():
    _sisip_pengumuman()
    channel = _channel(tipe=2)
    cog = _cog_pengumuman(channel)
    asyncio.run(cog._kirim_satu_pengumuman(
        SEKARANG, 9, str(GID), str(CH_TEKS), "Halo {server}",
        "2026-10-22T11:00:00+00:00", None, None,
    ))
    channel.send.assert_not_called()


@pytest.mark.usefixtures("db_tmp")
def test_ack_gagal_tidak_menghapus_timestamp_lokal():
    _sisip_pengumuman()
    channel = _channel()
    cog = _cog_pengumuman(channel)
    cog._ack_announcement = AsyncMock(return_value=False)  # dashboard tak terjangkau
    asyncio.run(cog._kirim_satu_pengumuman(
        SEKARANG, 9, str(GID), str(CH_TEKS), "Halo {server}",
        "2026-10-22T11:00:00+00:00", None, None,
    ))
    channel.send.assert_awaited_once()
    cog._ack_announcement.assert_awaited_once()
    tersimpan = _last_sent_db()
    assert tersimpan is not None
    # Timestamp lokal persis yang coba di-ack — bukti kirim tidak hilang.
    assert tersimpan == cog._ack_announcement.call_args.args[2]


# ---------- rekonsiliasi ack ----------

@pytest.mark.usefixtures("db_tmp")
def test_rekonsiliasi_mengirim_ulang_ack_bila_lokal_lebih_baru():
    lokal = "2026-10-22T10:00:00+00:00"
    _sisip_pengumuman(last_sent_at=lokal)
    cog = _cog(SimpleNamespace())
    cog._ack_announcement = AsyncMock(return_value=True)
    asyncio.run(cog._rekonsiliasi_pengumuman(
        GID, [{"id": 9, "last_sent_at": "2026-10-22T09:00:00+00:00"}]
    ))
    cog._ack_announcement.assert_awaited_once_with(GID, 9, lokal)


@pytest.mark.usefixtures("db_tmp")
def test_rekonsiliasi_diam_bila_remote_lebih_baru_atau_sama():
    _sisip_pengumuman(last_sent_at="2026-10-22T09:00:00+00:00")
    cog = _cog(SimpleNamespace())
    cog._ack_announcement = AsyncMock(return_value=True)
    asyncio.run(cog._rekonsiliasi_pengumuman(
        GID, [{"id": 9, "last_sent_at": "2026-10-22T10:00:00+00:00"}]
    ))
    asyncio.run(cog._rekonsiliasi_pengumuman(
        GID, [{"id": 9, "last_sent_at": "2026-10-22T09:00:00+00:00"}]
    ))
    cog._ack_announcement.assert_not_called()


# ---------- _simpan_pengumuman: merge monotonik dua arah ----------

def _baris_remote(last_sent_at):
    return [{
        "id": 9,
        "channel_id": str(CH_TEKS),
        "message": "pesan",
        "run_at": None,
        "interval_minutes": 60,
        "enabled": True,
        "last_sent_at": last_sent_at,
    }]


@pytest.mark.usefixtures("db_tmp")
def test_simpan_pengumuman_remote_lebih_lama_tidak_menimpa_lokal():
    lokal = "2026-10-22T10:00:00+00:00"
    _sisip_pengumuman(last_sent_at=lokal)
    cog = _cog(SimpleNamespace())
    cog._simpan_pengumuman(GID, _baris_remote("2026-10-22T09:00:00+00:00"))
    assert _last_sent_db() == lokal


@pytest.mark.usefixtures("db_tmp")
def test_simpan_pengumuman_remote_lebih_baru_menang():
    _sisip_pengumuman(last_sent_at="2026-10-22T09:00:00+00:00")
    cog = _cog(SimpleNamespace())
    cog._simpan_pengumuman(GID, _baris_remote("2026-10-22T10:00:00+00:00"))
    assert _last_sent_db() == "2026-10-22T10:00:00+00:00"


# ---------- welcome & goodbye: isolasi guild + tipe ----------

def _member_dan_system():
    sysch = MagicMock()
    sysch.send = AsyncMock()
    m = MagicMock()
    m.id = 123
    m.guild.id = GID
    m.guild.name = "Server Uji"
    m.guild.member_count = 10
    m.guild.system_channel = sysch
    m.mention = "<@123>"
    m.display_name = "Budi"
    m.display_avatar.read = AsyncMock(return_value=b"avatar")
    m.display_avatar.url = "https://cdn.test/avatar.png"
    m.send = AsyncMock()
    return m, sysch


@pytest.mark.usefixtures("db_tmp")
def test_welcome_channel_guild_lain_jatuh_ke_system_channel():
    from src.bot import FinchBot

    _set_setting("welcome_enabled", "1")
    _set_setting("welcome_channel_id", "777")
    asing = MagicMock()
    asing.guild.id = GUILD_LAIN
    asing.type = 0
    asing.send = AsyncMock()
    bot = FinchBot()
    bot.get_channel = MagicMock(return_value=asing)
    member, sysch = _member_dan_system()
    with patch("src.bot.make_welcome_card", return_value=io.BytesIO(b"PNG")):
        asyncio.run(bot.on_member_join(member))
    asing.send.assert_not_called()
    sysch.send.assert_called_once()


@pytest.mark.usefixtures("db_tmp")
def test_goodbye_channel_voice_jatuh_ke_system_channel():
    from src.bot import FinchBot

    _set_setting("goodbye_enabled", "1")
    _set_setting("goodbye_channel_id", "777")
    voice = MagicMock()
    voice.guild.id = GID
    voice.type = 2
    voice.send = AsyncMock()
    bot = FinchBot()
    bot.get_channel = MagicMock(return_value=voice)
    member, sysch = _member_dan_system()
    with patch("src.utils.modlog.log_event", new=AsyncMock()):
        asyncio.run(bot.on_member_remove(member))
    voice.send.assert_not_called()
    sysch.send.assert_called_once()


# ---------- kontrak get_connection ----------

@pytest.mark.usefixtures("db_tmp")
def test_get_connection_tertutup_setelah_blok():
    with store.get_connection() as conn:
        conn.execute("SELECT 1")
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")


@pytest.mark.usefixtures("db_tmp")
def test_get_connection_commit_saat_sukses():
    with store.get_connection() as conn:
        conn.execute("CREATE TABLE kontrak_commit (v INTEGER)")
        conn.execute("INSERT INTO kontrak_commit VALUES (1)")
    with store.get_connection() as conn:
        assert conn.execute("SELECT v FROM kontrak_commit").fetchone()[0] == 1


@pytest.mark.usefixtures("db_tmp")
def test_get_connection_rollback_saat_exception():
    with store.get_connection() as conn:
        conn.execute("CREATE TABLE kontrak_rollback (v INTEGER)")
    with pytest.raises(RuntimeError):
        with store.get_connection() as conn:
            conn.execute("INSERT INTO kontrak_rollback VALUES (1)")
            raise RuntimeError("boom")
    with store.get_connection() as conn:
        jumlah = conn.execute("SELECT COUNT(*) FROM kontrak_rollback").fetchone()[0]
    assert jumlah == 0
