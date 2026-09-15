"""Field-level cleaners: pure, typed, individually testable. No I/O, no validation.

Never silently coerce garbage into a plausible-looking value (e.g. 0 for an unparsable count) —
a wrong number is worse than a missing one, so these return `None` when the input can't be trusted.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

import ftfy

from data_foundry.schemas import MIN_PLAUSIBLE_YEAR

SENTINELS = frozenset({"", "-", "--", "n/a", "na", "null", "none", "\xa0", "sem informação"})

_WHITESPACE_RE = re.compile(r"\s+")
_NUMBER_RE = re.compile(r"\d[\d.,\s]*\d|\d")
_YEAR_RE = re.compile(r"\d{4}")

_LANG_MAP = {
    "pt": "pt",
    "português": "pt",
    "portugues": "pt",
    "pt-br": "pt",
    "pt_br": "pt",
    "en": "en",
    "english": "en",
    "inglês": "en",
    "ingles": "en",
    "es": "es",
    "español": "es",
    "espanhol": "es",
    "espanol": "es",
    "fr": "fr",
    "français": "fr",
    "francês": "fr",
    "frances": "fr",
    "french": "fr",
}


def fix_encoding(s: str) -> str:
    """Repair mojibake (e.g. `SÃ£o` -> `São`). Idempotent on already-clean text."""
    return ftfy.fix_text(s)


def clean_text(s: str | None) -> str | None:
    """Strip, collapse whitespace (including nbsp), fix encoding. `None` if the result is empty."""
    if s is None:
        return None
    text = fix_encoding(s)
    text = text.replace("\xa0", " ")
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text or None


def null_if_sentinel(s: str | None) -> str | None:
    """Map placeholder strings (`"-"`, `"n/a"`, ...) to `None`, case-insensitively."""
    if s is None:
        return None
    if s.strip().lower() in SENTINELS:
        return None
    return s


def parse_int_locale(s: str | None) -> int | None:
    """Parse locale-formatted counts (`"1.234"`, `"1,234"`, `"12.345 acessos"`) -> int.

    Returns `None` when no digits are found — never silently returns 0 for garbage.
    """
    if s is None:
        return None
    match = _NUMBER_RE.search(s)
    if not match:
        return None
    digits = re.sub(r"\D", "", match.group())
    return int(digits) if digits else None


def parse_year(s: str | None) -> int | None:
    """Extract a plausible 4-digit year from strings like `"Ano: 2005"`. `None` if implausible."""
    if s is None:
        return None
    match = _YEAR_RE.search(s)
    if not match:
        return None
    year = int(match.group())
    if MIN_PLAUSIBLE_YEAR <= year <= datetime.now(UTC).year + 1:
        return year
    return None


def normalize_lang(s: str | None) -> str | None:
    """Map common language names/codes to ISO 639-1 (`pt`, `en`, `es`, `fr`).

    Unknown values are cleaned but returned as-is — we never drop information we can't map.
    """
    cleaned = clean_text(s)
    if cleaned is None:
        return None
    return _LANG_MAP.get(cleaned.lower(), cleaned)
