from data_foundry.quality.curate import build_localized, build_universal, curate_works
from data_foundry.schemas import EnrichedWork, RawListingEntry, WorkDetail


def _raw(code: str = "obra1", title: str = "Dom Casmurro") -> RawListingEntry:
    return RawListingEntry(code=code, title=title, author="Machado de Assis", accesses="1.234")


def test_build_localized_well_formed():
    record = build_localized(
        raw=_raw(),
        title_translations={"en": "Dom Casmurro", "es": "Dom Casmurro", "fr": "Dom Casmurro"},
        description="Um romance clássico.",
        desc_translations={"en": "A classic novel."},
    )
    assert record.id == "obra1"
    assert record.title.pt == "Dom Casmurro"
    assert record.title.en == "Dom Casmurro"
    assert record.description.pt == "Um romance clássico."
    assert record.description.en == "A classic novel."


def test_build_universal_well_formed():
    record = build_universal(
        raw=_raw(),
        detail=WorkDetail(code="obra1", category="Romance", language="Português", year="Ano: 1899"),
        doc_hash="a" * 64,
        cover_path="covers/obra1.png",
        size_bytes=12345,
        run_id="20260101T000000Z-aaaaaaaa",
    )
    assert record.year == 1899
    assert record.language == "pt"
    assert record.accesses == 1234
    assert record.category == "Romance"
    assert record.run_id == "20260101T000000Z-aaaaaaaa"


def test_build_universal_without_detail_falls_back_to_raw():
    record = build_universal(
        raw=_raw(),
        detail=None,
        doc_hash=None,
        cover_path=None,
        size_bytes=None,
    )
    assert record.accesses == 1234  # from raw.accesses
    assert record.year is None
    assert record.document_hash is None


def test_curate_works_quarantines_invalid_without_raising():
    good = EnrichedWork(raw=_raw(code="obra1", title="Dom Casmurro"))
    bad = EnrichedWork(raw=_raw(code="obra2", title="   "))  # blank -> None pt title -> invalid

    result = curate_works([good, bad])

    assert len(result.localized) == 1
    assert result.localized[0].id == "obra1"
    assert len(result.universal) == 1
    assert len(result.quarantined) == 1
    assert result.quarantined[0].id == "obra2"
    assert result.quarantined[0].reason
    assert result.quarantined[0].raw["raw"]["code"] == "obra2"
