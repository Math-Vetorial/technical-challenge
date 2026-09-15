"""Property-based tests for the pure normalizers in `data_foundry.quality.normalize`.

Invariants are derived from the real signatures/behavior of the functions (see normalize.py),
not assumed. One known deviation from an "ideal" invariant is called out explicitly rather than
silently patched:

- `fix_encoding` has signature `str` (not `str | None`) and its only caller (`clean_text`)
  already guards against `None` before calling it, so it is excluded from the None-robustness
  property and only exercised with `st.text()`.
"""

from __future__ import annotations

from datetime import UTC, datetime

from hypothesis import example, given, settings
from hypothesis import strategies as st

from data_foundry.quality.normalize import (
    clean_text,
    fix_encoding,
    normalize_lang,
    null_if_sentinel,
    parse_int_locale,
    parse_year,
)
from data_foundry.schemas import MIN_PLAUSIBLE_YEAR

MAX_PLAUSIBLE_YEAR = datetime.now(UTC).year + 1

_OPTIONAL_STR_FUNCS = [clean_text, null_if_sentinel, parse_int_locale, parse_year, normalize_lang]


# ---------------------------------------------------------------------------
# Robustness: no exceptions for arbitrary input.
# ---------------------------------------------------------------------------


@given(s=st.one_of(st.text(), st.none()))
@example(s=None)
@example(s="")
def test_optional_str_funcs_never_raise(s: str | None) -> None:
    for fn in _OPTIONAL_STR_FUNCS:
        fn(s)  # must not raise for any str or None


@given(s=st.text())
@example(s="")
def test_fix_encoding_never_raises_for_str(s: str) -> None:
    # fix_encoding's signature is `str`, not `str | None` — None is out of contract
    # (its only caller, clean_text, guards it before calling in).
    fix_encoding(s)


# ---------------------------------------------------------------------------
# fix_encoding: idempotent.
# ---------------------------------------------------------------------------


@given(s=st.text())
@example(s="SÃ£o Paulo")
@example(s="")
def test_fix_encoding_is_idempotent(s: str) -> None:
    once = fix_encoding(s)
    twice = fix_encoding(once)
    assert twice == once


# ---------------------------------------------------------------------------
# clean_text: post-conditions.
# ---------------------------------------------------------------------------


@given(s=st.one_of(st.text(), st.none()))
@example(s="  a\xa0 b ")
@example(s=None)
def test_clean_text_postconditions(s: str | None) -> None:
    result = clean_text(s)
    if result is None:
        return
    assert result != ""
    assert result == result.strip()
    assert "  " not in result


@example(s="aÂ\xa0b")
@given(s=st.one_of(st.text(), st.none()))
def test_clean_text_never_leaves_nbsp(s: str | None) -> None:
    result = clean_text(s)
    if result is not None:
        assert "\xa0" not in result


@given(s=st.text(alphabet=" \t\n\r\xa0"))
def test_clean_text_blank_ish_input_is_none(s: str) -> None:
    assert clean_text(s) is None


# ---------------------------------------------------------------------------
# null_if_sentinel: idempotent-ish / sentinel mapping already covered by example tests;
# no additional property beyond the general robustness check above.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# parse_int_locale: round-trip through pt-BR thousand-separator formatting, and typing.
# ---------------------------------------------------------------------------


@given(
    n=st.integers(min_value=0, max_value=10**12),
    suffix=st.text(alphabet=st.characters(whitelist_categories=("L",)), max_size=20),
)
@example(n=1234, suffix=" acessos")
@example(n=0, suffix="")
@settings(max_examples=200)
def test_parse_int_locale_round_trips_pt_br_thousands(n: int, suffix: str) -> None:
    formatted = f"{n:,}".replace(",", ".")
    if suffix:
        formatted = f"{formatted} {suffix}"
    assert parse_int_locale(formatted) == n


@given(s=st.one_of(st.text(), st.none()))
def test_parse_int_locale_never_returns_coerced_garbage(s: str | None) -> None:
    result = parse_int_locale(s)
    assert result is None or (isinstance(result, int) and result >= 0)


# ---------------------------------------------------------------------------
# parse_year: extraction within/outside the plausible range.
# ---------------------------------------------------------------------------


@given(
    year=st.integers(min_value=MIN_PLAUSIBLE_YEAR, max_value=MAX_PLAUSIBLE_YEAR),
    prefix=st.text(alphabet=st.characters(whitelist_categories=("L",)), max_size=10),
    suffix=st.text(alphabet=st.characters(whitelist_categories=("L",)), max_size=10),
)
@example(year=2005, prefix="Ano: ", suffix="")
def test_parse_year_extracts_year_in_range(year: int, prefix: str, suffix: str) -> None:
    s = f"{prefix}{year}{suffix}"
    assert parse_year(s) == year


@given(
    year=st.integers(min_value=0, max_value=9999).filter(
        lambda y: not (MIN_PLAUSIBLE_YEAR <= y <= MAX_PLAUSIBLE_YEAR)
    ),
    prefix=st.text(alphabet=st.characters(whitelist_categories=("L",)), max_size=10),
    suffix=st.text(alphabet=st.characters(whitelist_categories=("L",)), max_size=10),
)
@example(year=1200, prefix="Ano: ", suffix="")
@example(year=9999, prefix="", suffix="")
def test_parse_year_rejects_out_of_range_year(year: int, prefix: str, suffix: str) -> None:
    s = f"{prefix}{year:04d}{suffix}"
    assert parse_year(s) is None


# ---------------------------------------------------------------------------
# normalize_lang: never discards information; known variants map to the expected code.
# ---------------------------------------------------------------------------


@given(s=st.text().filter(lambda t: clean_text(t) is not None))
def test_normalize_lang_never_returns_empty_for_nonblank_input(s: str) -> None:
    result = normalize_lang(s)
    assert result is not None
    assert result != ""


_KNOWN_VARIANTS = [
    ("pt", "pt"),
    ("português", "pt"),
    ("portugues", "pt"),
    ("pt-br", "pt"),
    ("pt_br", "pt"),
    ("PT-BR", "pt"),
    ("en", "en"),
    ("english", "en"),
    ("inglês", "en"),
    ("ingles", "en"),
    ("es", "es"),
    ("español", "es"),
    ("espanhol", "es"),
    ("espanol", "es"),
    ("fr", "fr"),
    ("français", "fr"),
    ("francês", "fr"),
    ("frances", "fr"),
    ("french", "fr"),
]


@given(pair=st.sampled_from(_KNOWN_VARIANTS))
def test_normalize_lang_maps_known_variants(pair: tuple[str, str]) -> None:
    variant, expected = pair
    assert normalize_lang(variant) == expected
