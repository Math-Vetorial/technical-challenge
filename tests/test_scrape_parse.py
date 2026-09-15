"""`parse_listing` against a recorded listing-HTML snippet. Offline, no network."""

from __future__ import annotations

from pathlib import Path

from data_foundry.stages.scrape import parse_listing

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def test_parse_listing_extracts_expected_entries():
    html = (FIXTURES_DIR / "listing.html").read_text(encoding="utf-8")

    entries = parse_listing(html)

    assert len(entries) == 2

    first = entries[0]
    assert first.code == "fixture-101"
    assert first.title == "A Cidade e as Serras"
    assert first.author == "Eça de Queirós"
    assert first.source == "Domínio Público"
    assert first.format == "PDF"
    assert first.size == "1.2 MB"
    assert first.accesses == "12.345"

    second = entries[1]
    assert second.code == "fixture-102"
    assert second.title == "Iracema"


def test_parse_listing_empty_html_yields_no_entries():
    assert parse_listing("<html><body>no table here</body></html>") == []
