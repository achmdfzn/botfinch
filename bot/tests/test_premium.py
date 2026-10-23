"""Tes premium (Free/VIP): parser owner, tier efektif dari cache,
bypass owner, kuota fitur, dan hitung pemakaian.

Pola mengikuti repo: fixture db_tmp seperti test_audit6_p1.py
(monkeypatch store.DB_PATH + init_db + tabel dashboard_sync), Settings
baru setelah patch env seperti test_config.py, dan patch config.settings
via dataclasses.replace + patch.object seperti test_dashboard_sync.py.
"""
import datetime as dt
from dataclasses import replace
from unittest.mock import patch

import pytest

from src import config, store
from src.cogs import dashboard_sync as ds
from src.utils import premium

OWNER1 = 1531892469233487912
OWNER2 = 364980558893285377
MEMBER = 111222333444555666
GID = 987654321098765432
GID_LAIN = 123456789012345678

SEKARANG = dt.datetime.now(dt.timezone.utc)


def _iso(waktu: dt.datetime) -> str:
    return waktu.astimezone(dt.timezone.utc).isoformat()


@pytest.fixture()
def db_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "finch-premium.db")
    store.init_db()
    with store.get_connection() as conn:
        conn.execute(ds.TABEL_SETTINGS)
        conn.execute(ds.TABEL_SELFROLES)
        conn.execute(ds.TABEL_ANNOUNCEMENTS)
        conn.commit()


@pytest.fixture()
def settings_owner(monkeypatch):
    """config.settings dengan dua owner sah + max age cache 3600 detik."""
    baru = replace(
        config.settings,
        bot_owner_ids_env=f"{OWNER1},{OWNER2}",
        entitlement_cache_max_age_seconds=3600,
    )
    monkeypatch.setattr(config, "settings", baru)
    return baru


def _settings_dari_env(monkeypatch, nilai):
    monkeypatch.setenv("BOT_OWNER_IDS", nilai)
    from src.config import Settings

    return Settings()


def _ent_vip(**ubah):
    ent = {
        "tier": "vip",
        "status": "active",
        "starts_at": _iso(SEKARANG - dt.timedelta(hours=1)),
        "expires_at": _iso(SEKARANG + dt.timedelta(days=7)),
        "source": "tes",
    }
    ent.update(ubah)
    return ent


def _atur_fetched_at(guild_id, waktu: dt.datetime) -> None:
    with store.get_connection() as conn:
        conn.execute(
            "UPDATE guild_entitlement_cache SET fetched_at = ? WHERE guild_id = ?",
            (_iso(waktu), str(guild_id)),
        )
        conn.commit()


# ---------- parser BOT_OWNER_IDS ----------

def test_parser_mengakui_kedua_owner_dari_brief(monkeypatch):
    s = _settings_dari_env(monkeypatch, "1531892469233487912,364980558893285377")
    assert s.bot_owner_ids() == frozenset({OWNER1, OWNER2})


def test_parser_spasi_dan_elemen_kosong_ditoleransi(monkeypatch):
    s = _settings_dari_env(monkeypatch, f"  {OWNER1} ,, {OWNER2} , ")
    assert s.bot_owner_ids() == frozenset({OWNER1, OWNER2})


def test_parser_entri_invalid_dilewati(monkeypatch):
    s = _settings_dari_env(
        monkeypatch, f"abc,{OWNER1},123,12 34,-5,99999999999999999999999999"
    )
    assert s.bot_owner_ids() == frozenset({OWNER1})


def test_parser_env_kosong_fail_closed(monkeypatch):
    s = _settings_dari_env(monkeypatch, "")
    assert s.bot_owner_ids() == frozenset()


def test_parser_dedupe(monkeypatch):
    s = _settings_dari_env(monkeypatch, f"{OWNER1},{OWNER1}, {OWNER1}")
    assert s.bot_owner_ids() == frozenset({OWNER1})


def test_validate_memperingatkan_owner_ids_terisi_tapi_tidak_valid(monkeypatch):
    s = _settings_dari_env(monkeypatch, "abc,123")
    assert any("BOT_OWNER_IDS" in m for m in s.validate())


def test_validate_diam_bila_owner_ids_valid(monkeypatch):
    s = _settings_dari_env(monkeypatch, f"{OWNER1},{OWNER2}")
    assert not any("BOT_OWNER_IDS" in m for m in s.validate())


def test_default_entitlement_cache_max_age(monkeypatch):
    monkeypatch.delenv("ENTITLEMENT_CACHE_MAX_AGE_SECONDS", raising=False)
    from src.config import Settings

    assert Settings().entitlement_cache_max_age_seconds == 3600


# ---------- is_bot_owner ----------

@pytest.mark.usefixtures("settings_owner")
def test_is_bot_owner():
    assert premium.is_bot_owner(OWNER1)
    assert premium.is_bot_owner(OWNER2)
    assert premium.is_bot_owner(str(OWNER1))  # str digit diterima
    assert not premium.is_bot_owner(MEMBER)
    assert not premium.is_bot_owner(None)
    assert not premium.is_bot_owner("bukan-angka")
    assert not premium.is_bot_owner("")


# ---------- tier efektif dari cache ----------

@pytest.mark.usefixtures("db_tmp", "settings_owner")
def test_tier_vip_jendela_valid():
    premium.simpan_entitlement_cache(GID, _ent_vip())
    assert premium.get_effective_tier(GID) == "vip"


@pytest.mark.usefixtures("db_tmp", "settings_owner")
def test_tier_vip_tanpa_batas_waktu():
    premium.simpan_entitlement_cache(GID, _ent_vip(starts_at=None, expires_at=None))
    assert premium.get_effective_tier(GID) == "vip"


@pytest.mark.usefixtures("db_tmp", "settings_owner")
def test_tier_starts_at_masa_depan_jadi_free():
    premium.simpan_entitlement_cache(
        GID, _ent_vip(starts_at=_iso(SEKARANG + dt.timedelta(days=1)))
    )
    assert premium.get_effective_tier(GID) == "free"


@pytest.mark.usefixtures("db_tmp", "settings_owner")
def test_tier_kedaluwarsa_jadi_free():
    premium.simpan_entitlement_cache(
        GID, _ent_vip(expires_at=_iso(SEKARANG - dt.timedelta(hours=1)))
    )
    assert premium.get_effective_tier(GID) == "free"


@pytest.mark.parametrize("status", ["revoked", "suspended", "cancelled"])
@pytest.mark.usefixtures("db_tmp", "settings_owner")
def test_tier_status_bukan_active_jadi_free(status):
    premium.simpan_entitlement_cache(GID, _ent_vip(status=status))
    assert premium.get_effective_tier(GID) == "free"


@pytest.mark.usefixtures("db_tmp", "settings_owner")
def test_tier_free_tetap_free():
    premium.simpan_entitlement_cache(GID, _ent_vip(tier="free"))
    assert premium.get_effective_tier(GID) == "free"


@pytest.mark.usefixtures("db_tmp", "settings_owner")
def test_tier_cache_basi_jadi_free():
    premium.simpan_entitlement_cache(GID, _ent_vip())
    _atur_fetched_at(GID, SEKARANG - dt.timedelta(seconds=3601))
    assert premium.get_effective_tier(GID) == "free"


@pytest.mark.usefixtures("db_tmp")
def test_tier_cache_basi_terhadap_max_age_yang_diubah():
    # Max age diperkecil lewat replace + patch.object (pola test_dashboard_sync).
    kecil = replace(
        config.settings,
        bot_owner_ids_env=f"{OWNER1},{OWNER2}",
        entitlement_cache_max_age_seconds=60,
    )
    with patch.object(config, "settings", kecil):
        premium.simpan_entitlement_cache(GID, _ent_vip())
        _atur_fetched_at(GID, SEKARANG - dt.timedelta(seconds=120))
        assert premium.get_effective_tier(GID) == "free"


@pytest.mark.usefixtures("db_tmp", "settings_owner")
def test_tier_guild_tak_dikenal_free():
    assert premium.get_effective_tier(GID_LAIN) == "free"


@pytest.mark.usefixtures("db_tmp", "settings_owner")
def test_tier_cache_kosong_free():
    assert premium.ambil_entitlement_cache(GID) is None
    assert premium.get_effective_tier(GID) == "free"


@pytest.mark.usefixtures("db_tmp", "settings_owner")
def test_tier_timestamp_rusak_jadi_free():
    premium.simpan_entitlement_cache(GID, _ent_vip(starts_at="bukan-tanggal"))
    assert premium.get_effective_tier(GID) == "free"
    premium.simpan_entitlement_cache(GID, _ent_vip(expires_at="2026-13-45"))
    assert premium.get_effective_tier(GID) == "free"


@pytest.mark.usefixtures("db_tmp", "settings_owner")
def test_tier_timestamp_naive_dianggap_utc():
    naive_lampau = (SEKARANG - dt.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
    premium.simpan_entitlement_cache(
        GID, _ent_vip(starts_at=naive_lampau, expires_at=None)
    )
    assert premium.get_effective_tier(GID) == "vip"


# ---------- bypass owner: personal, bukan meng-VIP-kan guild ----------

@pytest.mark.usefixtures("db_tmp", "settings_owner")
def test_bypass_owner_personal():
    # Guild ini tidak punya cache sama sekali (= free).
    assert premium.get_effective_tier(GID, actor_id=OWNER1) == "vip"
    assert premium.get_effective_tier(GID, actor_id=OWNER2) == "vip"
    assert premium.get_effective_tier(GID, actor_id=MEMBER) == "free"
    assert premium.get_effective_tier(GID) == "free"


# ---------- katalog & kuota ----------

KATALOG = {
    "custom_commands": {"free": 10, "vip": 100},
    "autoresponders": {"free": 10, "vip": 100},
    "giveaways_active": {"free": 3, "vip": 25},
    "selfrole_panels": {"free": 3, "vip": 25},
    "announcements_active": {"free": 3, "vip": 25},
}


def test_katalog_angka_persis():
    assert premium.FEATURE_LIMITS == KATALOG


@pytest.mark.usefixtures("db_tmp", "settings_owner")
def test_get_feature_limit_kedua_tier():
    premium.simpan_entitlement_cache(GID, _ent_vip())
    for kode, batas in KATALOG.items():
        assert premium.get_feature_limit(GID_LAIN, kode) == batas["free"]
        assert premium.get_feature_limit(GID, kode) == batas["vip"]
        assert premium.get_feature_limit(GID_LAIN, kode, actor_id=OWNER1) == batas["vip"]


@pytest.mark.usefixtures("db_tmp", "settings_owner")
def test_get_feature_limit_tak_dikenal_keyerror():
    with pytest.raises(KeyError):
        premium.get_feature_limit(GID, "fitur_ngawur")


@pytest.mark.usefixtures("db_tmp", "settings_owner")
def test_can_use_feature():
    for kode in KATALOG:
        assert premium.can_use_feature(GID, kode)
        assert premium.can_use_feature(GID_LAIN, kode)
    assert not premium.can_use_feature(GID, "fitur_ngawur")


@pytest.mark.usefixtures("db_tmp", "settings_owner")
def test_kuota_free_di_bawah_dan_tepat_di_limit():
    assert premium.check_resource_quota(GID, "custom_commands", 9)
    assert not premium.check_resource_quota(GID, "custom_commands", 10)
    assert not premium.check_resource_quota(GID, "custom_commands", 11)


@pytest.mark.usefixtures("db_tmp", "settings_owner")
def test_kuota_vip_lebih_tinggi():
    premium.simpan_entitlement_cache(GID, _ent_vip())
    assert premium.check_resource_quota(GID, "custom_commands", 10)
    assert premium.check_resource_quota(GID, "custom_commands", 99)
    assert not premium.check_resource_quota(GID, "custom_commands", 100)


@pytest.mark.usefixtures("db_tmp", "settings_owner")
def test_kuota_owner_selalu_true():
    assert premium.check_resource_quota(GID, "custom_commands", 10, actor_id=OWNER1)
    assert premium.check_resource_quota(GID, "custom_commands", 99999, actor_id=OWNER2)
    assert not premium.check_resource_quota(GID, "custom_commands", 10, actor_id=MEMBER)


def test_pesan_kuota_penuh():
    pesan = premium.pesan_kuota_penuh("custom_commands", 10)
    assert premium.NAMA_FITUR["custom_commands"] in pesan
    assert "10" in pesan
    assert "VIP" in pesan
    assert "http" not in pesan.lower()
    assert "rp" not in pesan.lower()


# ---------- simpan / ambil cache ----------

@pytest.mark.usefixtures("db_tmp", "settings_owner")
def test_simpan_ambil_cache_roundtrip():
    premium.simpan_entitlement_cache(GID, _ent_vip(source="dashboard"))
    cache = premium.ambil_entitlement_cache(GID)
    assert cache is not None
    assert cache["guild_id"] == str(GID)
    assert cache["tier"] == "vip"
    assert cache["status"] == "active"
    assert cache["source"] == "dashboard"
    assert cache["fetched_at"]


@pytest.mark.usefixtures("db_tmp", "settings_owner")
def test_simpan_none_tidak_mengubah_cache():
    premium.simpan_entitlement_cache(GID, _ent_vip())
    sebelum = premium.ambil_entitlement_cache(GID)
    premium.simpan_entitlement_cache(GID, None)
    assert premium.ambil_entitlement_cache(GID) == sebelum
    premium.simpan_entitlement_cache(GID_LAIN, None)
    assert premium.ambil_entitlement_cache(GID_LAIN) is None


# ---------- hitung_pemakaian ----------

@pytest.mark.usefixtures("db_tmp", "settings_owner")
def test_hitung_pemakaian():
    with store.get_connection() as conn:
        for i in range(2):
            conn.execute(
                "INSERT INTO custom_commands (guild_id, trigger, response, author_id)"
                " VALUES (?, ?, ?, ?)",
                (GID, f"cmd{i}", "halo", MEMBER),
            )
        conn.execute(
            "INSERT INTO custom_commands (guild_id, trigger, response, author_id)"
            " VALUES (?, ?, ?, ?)",
            (GID_LAIN, "cmdx", "halo", MEMBER),
        )
        conn.execute(
            "INSERT INTO autoresponder (guild_id, trigger, respons) VALUES (?, ?, ?)",
            (GID, "pagi", "Pagi juga!"),
        )
        for i, selesai in enumerate((0, 0, 1)):
            conn.execute(
                "INSERT INTO giveaways (message_id, channel_id, guild_id, ends_at,"
                " prize, host_id, ended) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (1000 + i, 555, GID, _iso(SEKARANG + dt.timedelta(hours=1)),
                 "Nitro", MEMBER, selesai),
            )
        # Dua panel: message 111 (2 emoji) + message 222 (1 emoji) = 2 panel.
        for emoji, pesan_id in (("🔥", 111), ("🎉", 111), ("⭐", 222)):
            conn.execute(
                "INSERT INTO dashboard_selfroles (guild_id, message_id, emoji, role_id)"
                " VALUES (?, ?, ?, ?)",
                (GID, pesan_id, emoji, 777),
            )
        for i, aktif in enumerate((1, 1, 0)):
            conn.execute(
                "INSERT INTO dashboard_announcements (id, guild_id, channel_id,"
                " message, enabled) VALUES (?, ?, ?, ?, ?)",
                (2000 + i, str(GID), "555", "pengumuman", aktif),
            )
        conn.execute(
            "INSERT INTO dashboard_announcements (id, guild_id, channel_id,"
            " message, enabled) VALUES (?, ?, ?, ?, ?)",
            (3000, str(GID_LAIN), "555", "pengumuman lain", 1),
        )
        conn.commit()
    assert premium.hitung_pemakaian(GID) == {
        "custom_commands": 2,
        "autoresponders": 1,
        "giveaways_active": 2,
        "selfrole_panels": 2,
        "announcements_active": 2,
    }
    assert premium.hitung_pemakaian(GID_LAIN) == {
        "custom_commands": 1,
        "autoresponders": 0,
        "giveaways_active": 0,
        "selfrole_panels": 0,
        "announcements_active": 1,
    }


@pytest.mark.usefixtures("db_tmp", "settings_owner")
def test_hitung_pemakaian_guild_kosong_nol():
    assert premium.hitung_pemakaian(GID) == {kode: 0 for kode in KATALOG}


def test_hitung_pemakaian_tabel_belum_ada_nol(tmp_path, monkeypatch):
    # DB file baru TANPA init_db: semua query harus aman dan menghasilkan 0.
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "mentah.db")
    assert premium.hitung_pemakaian(GID) == {kode: 0 for kode in KATALOG}
