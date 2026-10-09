"""Filter teks murni (tanpa dependency Discord) — gampang di-unit-test."""
import re
from functools import lru_cache

# Cocok: discord.gg/abc123, https://discord.gg/abc123,
#       discord.com/invite/abc123, www.discord.gg/abc123
_INVITE_RE = re.compile(
    r"(?:https?://)?(?:www\.)?discord(?:\.gg|\.com/invite)/[a-zA-Z0-9-]+",
    re.IGNORECASE,
)


def contains_invite_link(text: str) -> bool:
    """True kalau teks mengandung link invite Discord."""
    return bool(_INVITE_RE.search(text or ""))


@lru_cache(maxsize=8)
def _bad_word_re(words: tuple[str, ...]) -> "re.Pattern | None":
    if not words:
        return None
    pola = r"\b(" + "|".join(re.escape(w) for w in words) + r")\b"
    return re.compile(pola, re.IGNORECASE)


def contains_bad_word(text: str, bad_words: list[str]) -> bool:
    """True kalau teks mengandung kata kasar (whole-word, case-insensitive)."""
    rx = _bad_word_re(tuple(bad_words))
    return bool(rx and rx.search(text or ""))


def find_bad_word(text: str, bad_words: list[str]) -> str | None:
    """Kata kasar pertama yang ketemu (untuk log moderator)."""
    rx = _bad_word_re(tuple(bad_words))
    if not rx:
        return None
    m = rx.search(text or "")
    return m.group(1) if m else None


_DURASI_RE = re.compile(r"^(\d+)(s|m|h|d)$")
_SATUAN = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def parse_durasi(teks: str) -> int | None:
    """'10m' -> 600 (detik). Return None kalau format salah.

    Dipakai giveaway, polls, reminders — taruh di utils biar cog tidak import cog lain.
    """
    m = _DURASI_RE.match(teks.strip().lower())
    if not m:
        return None
    return int(m.group(1)) * _SATUAN[m.group(2)]
