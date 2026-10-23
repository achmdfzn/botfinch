"""Tes cog premium Free/VIP (src/cogs/premium.py) + gate kuota di cog lain.

Pola mengikuti test_audit6_p1.py: cog dibuat via __new__ tanpa __init__,
mock SimpleNamespace/AsyncMock, DB SQLite tmp via monkeypatch store.DB_PATH
+ init_db + TABEL_* dashboard_sync.

Kontrak yang dijaga:
- pull dashboard menyimpan entitlement ke cache lokal (tier berubah).
- Giveaway dari dashboard digate kuota giveaways_active (free 3 aktif),
  termasuk penghitungan batch dalam satu pull; guild VIP lolos.
- Semua subcommand /vip menolak non-owner (walau admin Discord sekalipun —
  penjaga hanya percaya premium.is_bot_owner).
- grant/extend/revoke memvalidasi input & jujur saat dashboard gagal /
  tidak terkonfigurasi (tidak pernah mengaku sukses).
- cc-tambah & respon-add digate kuota hanya untuk trigger BARU.
- Helper kuota giveaway lokal & gate panel self-role bekerja.
"""
import asyncio
import datetime as dt
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src import config, store
from src.cogs import dashboard_sync as ds
from src.cogs import responder as resp_mod
from src.cogs.customcmd import CustomCmd
from src.cogs.giveaway import Giveaway
from src.cogs.premium import (
    Premium,
    format_kedaluwarsa,
    validasi_durasi,
    validasi_guild_id,
)
from src.cogs.responder import Responder
from src.cogs.selfroles import SelfRoles
from src.utils import premium

GID = 777001
GID_VIP = 777002
GID_CC = 777003
CH_TEKS = 555001
OWNER = 424242
BUKAN_OWNER = 7

pytestmark = pytest.mark.usefixtures("db_tmp")


@pytest.fixture()
def db_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "finch-premium-cogs.db")
    store.init_db()
    with store.get_connection() as conn:
        conn.execute(ds.TABEL_SETTINGS)
        conn.execute(ds.TABEL_SELFROLES)
        conn.execute(ds.TABEL_ANNOUNCEMENTS)
        conn.commit()


@pytest.fixture()
def owner(monkeypatch):
    """Jadikan OWNER satu-satunya owner bot selama tes."""
    monkeypatch.setattr(premium, "is_bot_owner", lambda uid: uid == OWNER)


def _simpan_vip(gid: int) -> None:
    premium.simpan_entitlement_cache(
        gid, {"tier": "vip", "status": "active", "expires_at": None}
    )


def _isi_giveaway_aktif(gid: int, jumlah: int, awal: int = 900000) -> None:
    with store.get_connection() as conn:
        for i in range(jumlah):
            conn.execute(
                "INSERT INTO giveaways (message_id, channel_id, guild_id, ends_at,"
                " winners_count, prize, host_id, ended)"
                " VALUES (?, ?, ?, '2999-01-01T00:00:00+00:00', 1, 'Nitro', 1, 0)",
                (gid * 100 + i + 1, CH_TEKS, gid),
            )
        conn.commit()


def _jumlah_aktif_giveaway(gid: int) -> int:
    with store.get_connection() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM giveaways WHERE guild_id = ? AND ended = 0",
            (gid,),
        ).fetchone()[0]


# ---------------------------------------------------------------------------
# dashboard_sync: entitlement tersimpan dari alur pull
# ---------------------------------------------------------------------------

def _cog_ds(bot):
    cog = ds.DashboardSync.__new__(ds.DashboardSync)
    cog.bot = bot
    return cog


def test_simpan_entitlement_mengubah_tier_efektif():
    cog = _cog_ds(SimpleNamespace())
    assert premium.get_effective_tier(GID) == "free"
    cog._simpan_entitlement(
        GID,
        {
            "settings": {},
            "entitlement": {"tier": "vip", "status": "active", "expires_at": None},
        },
    )
    assert premium.get_effective_tier(GID) == "vip"


def test_simpan_entitlement_none_tidak_mengubah_cache():
    cog = _cog_ds(SimpleNamespace())
    _simpan_vip(GID)
    # Dashboard lama: payload tanpa entitlement -> no-op, cache dipertahankan.
    cog._simpan_entitlement(GID, {"settings": {}})
    cog._simpan_entitlement(GID, {})
    assert premium.get_effective_tier(GID) == "vip"


# ---------------------------------------------------------------------------
# dashboard_sync: gate kuota giveaway
# ---------------------------------------------------------------------------

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


def _bot_giveaway(cog_giveaway):
    return SimpleNamespace(
        get_cog=lambda nama: cog_giveaway,
        user=SimpleNamespace(id=999),
        fetch_channel=AsyncMock(),
    )


def _permintaan_giveaway(req_id=3):
    return [{
        "id": req_id,
        "channel_id": CH_TEKS,
        "duration_minutes": 5,
        "winners": 1,
        "prize": "Nitro",
    }]


def test_giveaway_dashboard_ditolak_saat_kuota_free_penuh():
    _isi_giveaway_aktif(GID, 3)  # limit free giveaways_active = 3
    gw = SimpleNamespace(posting_giveaway=AsyncMock(return_value=1))
    cog = _cog_ds(_bot_giveaway(gw))
    cog._ack_giveaway = AsyncMock()
    asyncio.run(cog._proses_giveaway(_guild(_channel()), _permintaan_giveaway()))
    gw.posting_giveaway.assert_not_called()
    cog._ack_giveaway.assert_awaited_once()
    args = cog._ack_giveaway.call_args.args
    assert args[2] == "failed"
    assert "Batas" in args[3]  # note kuota penuh dari premium.pesan_kuota_penuh


def test_giveaway_dashboard_vip_lolos_kuota():
    _simpan_vip(GID_VIP)
    _isi_giveaway_aktif(GID_VIP, 3)  # free penuh, tapi VIP limit 25
    gw = SimpleNamespace(posting_giveaway=AsyncMock(return_value=123456))
    cog = _cog_ds(_bot_giveaway(gw))
    cog._ack_giveaway = AsyncMock()
    asyncio.run(
        cog._proses_giveaway(_guild(_channel(GID_VIP), GID_VIP), _permintaan_giveaway())
    )
    gw.posting_giveaway.assert_awaited_once()
    assert cog._ack_giveaway.call_args.args[2] == "done"


def test_giveaway_dashboard_batch_ikut_terhitung():
    _isi_giveaway_aktif(GID, 2)  # sisa kuota free = 1
    gw = SimpleNamespace(posting_giveaway=AsyncMock(return_value=123456))
    cog = _cog_ds(_bot_giveaway(gw))
    cog._ack_giveaway = AsyncMock()
    reqs = _permintaan_giveaway(11) + _permintaan_giveaway(12)
    asyncio.run(cog._proses_giveaway(_guild(_channel()), reqs))
    gw.posting_giveaway.assert_awaited_once()  # hanya request pertama
    status = [c.args[2] for c in cog._ack_giveaway.call_args_list]
    assert status == ["done", "failed"]


# ---------------------------------------------------------------------------
# /vip: penjaga owner
# ---------------------------------------------------------------------------

def _interaction(user_id, guild_id=GID):
    return SimpleNamespace(
        user=SimpleNamespace(id=user_id),
        guild=SimpleNamespace(id=guild_id, name="Server Uji"),
        response=SimpleNamespace(
            send_message=AsyncMock(),
            defer=AsyncMock(),
            is_done=lambda: False,
        ),
        followup=SimpleNamespace(send=AsyncMock()),
    )


def _cog_premium():
    cog = Premium.__new__(Premium)
    cog.bot = SimpleNamespace()
    return cog


def _vip_cmd(nama: str):
    return next(c for c in Premium.vip.commands if c.name == nama)


@pytest.mark.usefixtures("owner")
def test_penjaga_menolak_bukan_owner():
    cog = _cog_premium()
    inter = _interaction(BUKAN_OWNER)
    assert asyncio.run(cog._tolak_bukan_owner(inter)) is True
    inter.response.send_message.assert_awaited_once()
    assert inter.response.send_message.call_args.kwargs["ephemeral"] is True


@pytest.mark.usefixtures("owner")
def test_penjaga_meloloskan_owner():
    cog = _cog_premium()
    inter = _interaction(OWNER)
    assert asyncio.run(cog._tolak_bukan_owner(inter)) is False
    inter.response.send_message.assert_not_called()


@pytest.mark.usefixtures("owner")
def test_grant_callback_menolak_bukan_owner():
    cog = _cog_premium()
    cog._post_entitlement = AsyncMock(return_value=(200, {}, None))
    inter = _interaction(BUKAN_OWNER)
    asyncio.run(
        _vip_cmd("grant").callback(
            cog, inter, guild_id="123456789012345678", duration_days=None, reason=None
        )
    )
    inter.response.send_message.assert_awaited_once()
    assert inter.response.send_message.call_args.kwargs["ephemeral"] is True
    cog._post_entitlement.assert_not_called()
    inter.followup.send.assert_not_called()


@pytest.mark.usefixtures("owner")
def test_grant_guild_id_rusak_ditolak_sebelum_http():
    cog = _cog_premium()
    cog._post_entitlement = AsyncMock(return_value=(200, {}, None))
    inter = _interaction(OWNER)
    asyncio.run(
        _vip_cmd("grant").callback(
            cog, inter, guild_id="bukan-angka", duration_days=None, reason=None
        )
    )
    cog._post_entitlement.assert_not_called()
    assert "tidak valid" in inter.response.send_message.call_args.args[0]


@pytest.mark.usefixtures("owner")
def test_extend_tanpa_durasi_ditolak():
    cog = _cog_premium()
    cog._post_entitlement = AsyncMock(return_value=(200, {}, None))
    inter = _interaction(OWNER)
    asyncio.run(
        _vip_cmd("extend").callback(
            cog, inter, guild_id="123456789012345678", duration_days=None, reason=None
        )
    )
    cog._post_entitlement.assert_not_called()
    assert "Durasi wajib" in inter.response.send_message.call_args.args[0]


@pytest.mark.usefixtures("owner")
def test_grant_sukses_menyegarkan_cache_lokal():
    cog = _cog_premium()
    ent = {"tier": "vip", "status": "active", "expires_at": None}
    cog._post_entitlement = AsyncMock(return_value=(200, {"entitlement": ent}, None))
    inter = _interaction(OWNER)
    asyncio.run(
        _vip_cmd("grant").callback(
            cog, inter, guild_id=str(GID), duration_days=30, reason="tes"
        )
    )
    cog._post_entitlement.assert_awaited_once()
    assert cog._post_entitlement.call_args.args[1] == "grant"
    inter.followup.send.assert_awaited_once()
    teks = inter.followup.send.call_args.args[0]
    assert str(GID) in teks and "vip" in teks
    # Cache lokal langsung segar tanpa menunggu pull berikutnya.
    assert premium.get_effective_tier(GID) == "vip"


@pytest.mark.usefixtures("owner")
def test_grant_gagal_http_tidak_mengaku_sukses():
    cog = _cog_premium()
    cog._post_entitlement = AsyncMock(
        return_value=(500, None, "dashboard menolak (HTTP 500)")
    )
    inter = _interaction(OWNER)
    asyncio.run(
        _vip_cmd("grant").callback(
            cog, inter, guild_id=str(GID), duration_days=None, reason=None
        )
    )
    teks = inter.followup.send.call_args.args[0]
    assert "Gagal" in teks and "500" in teks
    assert premium.get_effective_tier(GID) == "free"


def test_post_entitlement_tanpa_konfigurasi_jujur(monkeypatch):
    monkeypatch.setattr(
        config, "settings", replace(config.settings, dashboard_url="", dashboard_secret="")
    )
    cog = _cog_premium()
    status, _data, err = asyncio.run(
        cog._post_entitlement(GID, "grant", None, "", OWNER)
    )
    assert status is None
    assert "tidak terkonfigurasi" in err


@pytest.mark.usefixtures("owner")
def test_vip_status_cache_kosong_jujur():
    cog = _cog_premium()
    inter = _interaction(OWNER)
    asyncio.run(_vip_cmd("status").callback(cog, inter, guild_id=str(GID)))
    teks = inter.response.send_message.call_args.args[0]
    assert "Belum ada data" in teks


@pytest.mark.usefixtures("owner")
def test_vip_list_dari_cache():
    _simpan_vip(GID)
    _simpan_vip(GID_VIP)
    cog = _cog_premium()
    inter = _interaction(OWNER)
    asyncio.run(_vip_cmd("list").callback(cog, inter, page=1))
    teks = inter.response.send_message.call_args.args[0]
    assert str(GID) in teks and str(GID_VIP) in teks
    assert "cache" in teks.lower()


# ---------------------------------------------------------------------------
# /premium: embed status
# ---------------------------------------------------------------------------

def test_premium_cmd_di_dm_ditolak():
    cog = _cog_premium()
    inter = _interaction(BUKAN_OWNER)
    inter.guild = None
    asyncio.run(Premium.premium_cmd.callback(cog, inter))
    inter.response.send_message.assert_awaited_once()
    assert inter.response.send_message.call_args.kwargs["ephemeral"] is True


def test_premium_cmd_embed_status_free():
    cog = _cog_premium()
    inter = _interaction(BUKAN_OWNER)
    asyncio.run(Premium.premium_cmd.callback(cog, inter))
    inter.response.send_message.assert_awaited_once()
    embed = inter.response.send_message.call_args.kwargs["embed"]
    nilai = {f.name: f.value for f in embed.fields}
    assert "Free" in nilai["Tier server"]
    assert "Custom command" in nilai["Pemakaian"]
    assert "10" in nilai["Pemakaian"]  # limit free custom_commands
    # Tanpa PREMIUM_UPGRADE_URL: info upgrade manual via owner, tanpa URL palsu.
    assert "manual melalui owner bot" in nilai["Upgrade ke VIP"]


# ---------------------------------------------------------------------------
# Helper validasi & format premium cog
# ---------------------------------------------------------------------------

def test_validasi_guild_id():
    assert validasi_guild_id("12345") == 12345
    assert validasi_guild_id("1" * 25) is not None
    assert validasi_guild_id("1234") is None
    assert validasi_guild_id("1" * 26) is None
    assert validasi_guild_id("12a45") is None
    assert validasi_guild_id("") is None
    assert validasi_guild_id(None) is None


def test_validasi_durasi():
    assert validasi_durasi(None, wajib=False) is None
    assert validasi_durasi(None, wajib=True) is not None
    assert validasi_durasi(0, wajib=False) is not None
    assert validasi_durasi(3651, wajib=False) is not None
    assert validasi_durasi(30, wajib=True) is None


def test_format_kedaluwarsa():
    assert format_kedaluwarsa(None) == "Permanen"
    sekarang = dt.datetime(2026, 10, 13, tzinfo=dt.timezone.utc)
    assert format_kedaluwarsa("2026-11-12T00:00:00+00:00", sekarang) == (
        "berakhir 12 Nov 2026 (30 hari lagi)"
    )
    assert "sudah lewat" in format_kedaluwarsa("2026-10-01T00:00:00+00:00", sekarang)


# ---------------------------------------------------------------------------
# customcmd: gate kuota custom_commands
# ---------------------------------------------------------------------------

def _bot_cc():
    bot = MagicMock()
    bot.all_commands = {}
    bot.tree.walk_commands.return_value = []
    return bot


def _ctx(gid=GID, author=BUKAN_OWNER):
    ctx = MagicMock()
    ctx.guild.id = gid
    ctx.author.id = author
    ctx.send = AsyncMock()
    return ctx


def _isi_custom_commands(gid: int, jumlah: int) -> None:
    with store.get_connection() as conn:
        for i in range(jumlah):
            conn.execute(
                "INSERT INTO custom_commands (guild_id, trigger, response, author_id)"
                " VALUES (?, ?, 'x', 7)",
                (gid, f"cmd{i:02d}"),
            )
        conn.commit()


def _jumlah_custom_commands(gid: int) -> int:
    with store.get_connection() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM custom_commands WHERE guild_id = ?", (gid,)
        ).fetchone()[0]


def test_cc_tambah_ditolak_saat_kuota_free_penuh():
    _isi_custom_commands(GID_CC, 10)  # limit free custom_commands = 10
    cog = CustomCmd(_bot_cc())
    ctx = _ctx(GID_CC)
    asyncio.run(cog.cc_tambah.callback(cog, ctx, "baru", respons="Halo!"))
    assert _jumlah_custom_commands(GID_CC) == 10  # tidak ada baris baru
    assert "Batas" in ctx.send.call_args.args[0]


def test_cc_tambah_update_trigger_lama_lolos_saat_penuh():
    _isi_custom_commands(GID_CC, 10)
    cog = CustomCmd(_bot_cc())
    ctx = _ctx(GID_CC)
    asyncio.run(cog.cc_tambah.callback(cog, ctx, "cmd00", respons="Baru!"))
    assert _jumlah_custom_commands(GID_CC) == 10
    assert "diperbarui" in ctx.send.call_args.args[0]


def test_cc_tambah_di_bawah_kuota_lolos():
    _isi_custom_commands(GID_CC, 9)
    cog = CustomCmd(_bot_cc())
    ctx = _ctx(GID_CC)
    asyncio.run(cog.cc_tambah.callback(cog, ctx, "baru", respons="Halo!"))
    assert _jumlah_custom_commands(GID_CC) == 10
    assert "ditambahkan" in ctx.send.call_args.args[0]


# ---------------------------------------------------------------------------
# responder: gate kuota autoresponders
# ---------------------------------------------------------------------------

def _isi_responder(gid: int, jumlah: int) -> None:
    with store.get_connection() as conn:
        for i in range(jumlah):
            conn.execute(
                "INSERT INTO autoresponder (guild_id, trigger, respons) VALUES (?, ?, 'x')",
                (gid, f"trig{i:02d}"),
            )
        conn.commit()


def _jumlah_responder(gid: int) -> int:
    with store.get_connection() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM autoresponder WHERE guild_id = ?", (gid,)
        ).fetchone()[0]


def test_respon_add_ditolak_saat_kuota_free_penuh(monkeypatch):
    mirror = AsyncMock()
    monkeypatch.setattr(resp_mod, "_mirror_dashboard", mirror)
    _isi_responder(GID, 10)  # limit free autoresponders = 10
    cog = Responder(SimpleNamespace())
    ctx = _ctx(GID)
    asyncio.run(cog.respon_add.callback(cog, ctx, "baru", respons="halo"))
    assert _jumlah_responder(GID) == 10
    assert "Batas" in ctx.send.call_args.args[0]
    mirror.assert_not_called()  # tanpa insert -> tanpa mirror dashboard


def test_respon_add_update_lolos_saat_penuh(monkeypatch):
    mirror = AsyncMock()
    monkeypatch.setattr(resp_mod, "_mirror_dashboard", mirror)
    _isi_responder(GID, 10)
    cog = Responder(SimpleNamespace())
    ctx = _ctx(GID)
    asyncio.run(cog.respon_add.callback(cog, ctx, "trig00", respons="baru"))
    assert _jumlah_responder(GID) == 10
    assert ctx.send.call_args.args[0].startswith("✅")
    mirror.assert_awaited_once()


# ---------------------------------------------------------------------------
# giveaway lokal: helper kuota
# ---------------------------------------------------------------------------

def test_helper_kuota_giveaway():
    cog = Giveaway.__new__(Giveaway)
    assert cog._kuota_giveaway_penuh(GID) is False
    _isi_giveaway_aktif(GID, 3)
    assert cog._kuota_giveaway_penuh(GID) is True
    _simpan_vip(GID_VIP)
    _isi_giveaway_aktif(GID_VIP, 3)
    assert cog._kuota_giveaway_penuh(GID_VIP) is False  # VIP limit 25


# ---------------------------------------------------------------------------
# selfroles: gate panel (hitungan dari panel dashboard)
# ---------------------------------------------------------------------------

def _isi_panel_dashboard(gid: int, jumlah: int) -> None:
    with store.get_connection() as conn:
        for i in range(jumlah):
            conn.execute(
                "INSERT INTO dashboard_selfroles (guild_id, message_id, emoji, role_id)"
                " VALUES (?, ?, '⭐', 1)",
                (gid, 600000 + i),
            )
        conn.commit()


def test_panel_role_ditolak_saat_kuota_penuh(monkeypatch):
    monkeypatch.setattr(
        config, "settings", replace(config.settings, self_roles="Pioneer")
    )
    _isi_panel_dashboard(GID, 3)  # limit free selfrole_panels = 3
    cog = SelfRoles(SimpleNamespace())
    ctx = SimpleNamespace(
        guild=SimpleNamespace(id=GID, roles=[SimpleNamespace(name="Pioneer")]),
        author=SimpleNamespace(id=BUKAN_OWNER),
        send=AsyncMock(),
    )
    asyncio.run(cog.panel_role.callback(cog, ctx))
    ctx.send.assert_awaited_once()
    assert "Batas" in ctx.send.call_args.args[0]
    assert "embed" not in ctx.send.call_args.kwargs  # panel tidak terkirim


def test_panel_role_lolos_di_bawah_kuota(monkeypatch):
    monkeypatch.setattr(
        config, "settings", replace(config.settings, self_roles="Pioneer")
    )
    cog = SelfRoles(SimpleNamespace())
    ctx = SimpleNamespace(
        guild=SimpleNamespace(id=GID, roles=[SimpleNamespace(name="Pioneer")]),
        author=SimpleNamespace(id=BUKAN_OWNER),
        send=AsyncMock(),
    )
    asyncio.run(cog.panel_role.callback(cog, ctx))
    assert "embed" in ctx.send.call_args.kwargs  # panel terkirim
