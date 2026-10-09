"""Test logika baru wiring dashboard: emoji_cocok, caps filter, setting int."""
from types import SimpleNamespace

from src.cogs.dashboard_sync import emoji_cocok, _parse_emoji, get_guild_setting_int, TABEL_SETTINGS
from src.cogs.moderation import _caps_berlebihan
from src.store import get_connection


class _UniEmoji:
    """Meniru discord.PartialEmoji untuk emoji unicode: str() = karakternya."""

    def __init__(self, s):
        self.id = None
        self.name = s

    def __str__(self):
        return self.name


def _emoji_unicode(s):
    return _UniEmoji(s)


def _emoji_custom(name, eid):
    return SimpleNamespace(id=eid, name=name)


def test_emoji_cocok_unicode():
    assert emoji_cocok("👍", _emoji_unicode("👍"))
    assert not emoji_cocok("👍", _emoji_unicode("👎"))
    assert not emoji_cocok("", _emoji_unicode("👍"))


def test_emoji_cocok_custom_by_id():
    e = _emoji_custom("finch", 12345)
    assert emoji_cocok("12345", e)
    assert emoji_cocok("<:finch:12345>", e)
    assert emoji_cocok("finch:12345", e)
    assert not emoji_cocok("99999", e)


def test_emoji_cocok_custom_by_name():
    e = _emoji_custom("finch", 12345)
    assert emoji_cocok("finch", e)


def test_parse_emoji():
    assert _parse_emoji("👍") == "👍"
    assert _parse_emoji("<:finch:123>") == "<:finch:123>"
    assert _parse_emoji("") is None
    assert _parse_emoji("   ") is None


def test_caps_berlebihan():
    assert _caps_berlebihan("INI CAPS SEMUA PANJANG BANGET YA")
    assert not _caps_berlebihan("Halo apa kabar")
    assert not _caps_berlebihan("OK")  # terlalu pendek
    assert not _caps_berlebihan("Ini Campuran Biasa Saja Kok Ya")
    assert not _caps_berlebihan("")


def test_get_guild_setting_int():
    with get_connection() as conn:
        conn.execute(TABEL_SETTINGS)
        conn.execute(
            "INSERT OR REPLACE INTO dashboard_settings (guild_id, key, value) VALUES (1, 'k_int', '150')"
        )
        conn.execute(
            "INSERT OR REPLACE INTO dashboard_settings (guild_id, key, value) VALUES (1, 'k_rusak', 'abc')"
        )
        conn.commit()
    try:
        assert get_guild_setting_int(1, "k_int", 100) == 150
        assert get_guild_setting_int(1, "k_rusak", 100) == 100
        assert get_guild_setting_int(1, "k_tidak_ada", 42) == 42
    finally:
        with get_connection() as conn:
            conn.execute("DELETE FROM dashboard_settings WHERE guild_id = 1 AND key LIKE 'k_%'")
            conn.commit()
