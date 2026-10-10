"""Test integrasi 4 setting baru bot <-> dashboard (IMPLEMENTER-3).

Mencakup: `automod_warn_max`, `voicexp_xp_per_min`, `economy_min_bet` /
`economy_max_bet`, `bank_bunga_harian`. Tiap setting diuji: baca override
dari dashboard, fallback ke default config bila key tidak ada, dan
clamp/abaikan bila nilai dashboard di luar rentang atau tak valid.
"""
from src import config
from src.cogs import automod, economy as eko_cog, minigames, voicexp
from src.store import get_connection, init_db

init_db()

GID = 515003  # guild id khusus file test ini


def _set(key: str, value: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO dashboard_settings (guild_id, key, value) VALUES (?, ?, ?)",
            (GID, str(key), str(value)),
        )
        conn.commit()


def _bersih() -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM dashboard_settings WHERE guild_id = ?", (GID,))
        conn.execute("DELETE FROM economy WHERE guild_id = ?", (GID,))
        conn.commit()


# ---------- automod_warn_max ----------

def test_warn_max_default():
    _bersih()
    assert automod.warn_max_guild(GID) == config.settings.warn_max == 3


def test_warn_max_override():
    _bersih()
    _set("automod_warn_max", "5")
    try:
        assert automod.warn_max_guild(GID) == 5
    finally:
        _bersih()


def test_warn_max_clamp_dan_tak_valid():
    _bersih()
    try:
        _set("automod_warn_max", "99")
        assert automod.warn_max_guild(GID) == 10
        _set("automod_warn_max", "0")
        assert automod.warn_max_guild(GID) == 1
        _set("automod_warn_max", "rusak")
        assert automod.warn_max_guild(GID) == config.settings.warn_max
    finally:
        _bersih()


# ---------- voicexp_xp_per_min ----------

def test_voicexp_default():
    _bersih()
    assert voicexp.voicexp_per_menit(GID) == config.settings.voice_xp_per_min == 5


def test_voicexp_override():
    _bersih()
    _set("voicexp_xp_per_min", "20")
    try:
        assert voicexp.voicexp_per_menit(GID) == 20
    finally:
        _bersih()


def test_voicexp_clamp_dan_tak_valid():
    _bersih()
    try:
        _set("voicexp_xp_per_min", "999")
        assert voicexp.voicexp_per_menit(GID) == 60
        _set("voicexp_xp_per_min", "0")
        assert voicexp.voicexp_per_menit(GID) == 0  # 0 = voice tak beri XP
        _set("voicexp_xp_per_min", "-7")
        assert voicexp.voicexp_per_menit(GID) == 0
        _set("voicexp_xp_per_min", "abc")
        assert voicexp.voicexp_per_menit(GID) == config.settings.voice_xp_per_min
    finally:
        _bersih()


# ---------- economy_min_bet / economy_max_bet ----------

def test_bet_default():
    _bersih()
    assert minigames.batas_bet_guild(GID) == (
        config.settings.economy_min_bet,
        config.settings.economy_max_bet,
    ) == (10, 5000)


def test_bet_override():
    _bersih()
    _set("economy_min_bet", "100")
    _set("economy_max_bet", "2000")
    try:
        assert minigames.batas_bet_guild(GID) == (100, 2000)
    finally:
        _bersih()


def test_bet_terbalik_ditukar():
    """min > max (terbalik) -> ditukar, selaras /kerja."""
    _bersih()
    _set("economy_min_bet", "5000")
    _set("economy_max_bet", "100")
    try:
        assert minigames.batas_bet_guild(GID) == (100, 5000)
    finally:
        _bersih()


def test_cek_taruhan_pakai_guild():
    _bersih()
    _set("economy_min_bet", "100")
    _set("economy_max_bet", "2000")
    try:
        assert minigames._cek_taruhan(10000, 50, GID) is not None  # di bawah min
        assert minigames._cek_taruhan(10000, 5000, GID) is not None  # di atas max
        assert minigames._cek_taruhan(10000, 500, GID) is None
        assert "100" in minigames._cek_taruhan(10000, 50, GID)
        assert "2000" in minigames._cek_taruhan(10000, 5000, GID)
    finally:
        _bersih()


def test_cek_taruhan_tanpa_guild_kompatibel():
    """Pemanggil lama tanpa guild_id tetap jalan (default global)."""
    _bersih()
    assert minigames._cek_taruhan(10000, 500) is None
    assert minigames._cek_taruhan(10000, 5) is not None


# ---------- bank_bunga_harian ----------

def test_bunga_default():
    _bersih()
    assert eko_cog.bunga_guild(GID) == config.settings.bank_bunga_harian == 2


def test_bunga_override():
    _bersih()
    _set("bank_bunga_harian", "5")
    try:
        assert eko_cog.bunga_guild(GID) == 5
    finally:
        _bersih()


def test_bunga_clamp_dan_tak_valid():
    _bersih()
    try:
        _set("bank_bunga_harian", "150")
        assert eko_cog.bunga_guild(GID) == 100
        _set("bank_bunga_harian", "0")
        assert eko_cog.bunga_guild(GID) == 0
        _set("bank_bunga_harian", "abc")
        assert eko_cog.bunga_guild(GID) == config.settings.bank_bunga_harian
    finally:
        _bersih()


def test_bunga_override_map():
    """Peta override: nilai valid di-clamp, 0/tak valid dilewati."""
    _bersih()
    try:
        with get_connection() as conn:
            for gid, val in [(GID, "7"), (GID + 1, "200"), (GID + 2, "0"), (GID + 3, "xx")]:
                conn.execute(
                    "INSERT OR REPLACE INTO dashboard_settings (guild_id, key, value)"
                    " VALUES (?, 'bank_bunga_harian', ?)",
                    (gid, val),
                )
            conn.commit()
            hasil = eko_cog.bunga_override_map(conn)
        assert hasil == {GID: 7, GID + 1: 100}
    finally:
        with get_connection() as conn:
            conn.execute(
                "DELETE FROM dashboard_settings WHERE key = 'bank_bunga_harian'"
                " AND guild_id BETWEEN ? AND ?",
                (GID, GID + 3),
            )
            conn.commit()


def _isi_bank(gid: int, uid: int, bank: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO economy (user_id, guild_id, balance, bank)"
            " VALUES (?, ?, 0, ?)",
            (uid, gid, bank),
        )
        conn.commit()


def _baca_bank(gid: int, uid: int) -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT bank FROM economy WHERE user_id = ? AND guild_id = ?",
            (uid, gid),
        ).fetchone()
    return row[0] if row else 0


def test_terapkan_bunga_per_guild():
    """Guild override dibayar rate-nya sendiri; sisanya rate global; yang mati dilewati."""
    g1, g2, g3 = GID, GID + 10, GID + 11
    _isi_bank(g1, 1, 1000)   # override 10% -> +100
    _isi_bank(g2, 2, 1000)   # global 2% -> +20
    _isi_bank(g3, 3, 1000)   # mati -> +0
    try:
        with get_connection() as conn:
            total = eko_cog.terapkan_bunga_bank(conn, 2, {g1: 10}, {g3})
            conn.commit()
        assert total == 2
        assert _baca_bank(g1, 1) == 1100
        assert _baca_bank(g2, 2) == 1020
        assert _baca_bank(g3, 3) == 1000
    finally:
        with get_connection() as conn:
            conn.execute("DELETE FROM economy WHERE guild_id IN (?, ?, ?)", (g1, g2, g3))
            conn.commit()


def test_terapkan_bunga_global_nol_override_jalan():
    """Global 0 tapi ada override -> override tetap dibayar."""
    g1 = GID + 20
    _isi_bank(g1, 1, 1000)
    try:
        with get_connection() as conn:
            total = eko_cog.terapkan_bunga_bank(conn, 0, {g1: 5}, set())
            conn.commit()
        assert total == 1
        assert _baca_bank(g1, 1) == 1050
    finally:
        with get_connection() as conn:
            conn.execute("DELETE FROM economy WHERE guild_id = ?", (g1,))
            conn.commit()
