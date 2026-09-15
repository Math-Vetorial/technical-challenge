from data_foundry.schemas import EnrichedWork, RawListingEntry, WorkDetail
from data_foundry.stages.assemble import assemble


def _work(code: str, title: str = "Título", document_hash: str | None = None) -> EnrichedWork:
    return EnrichedWork(
        raw=RawListingEntry(code=code, title=title, author="Autor"),
        detail=WorkDetail(code=code, category="Romance", language="Português", year="1900"),
        document_hash=document_hash,
        cover_path=f"covers/{code}.png",
        cover_hash=f"coverhash-{code}",
        size_bytes=1024,
        description="Uma descrição.",
        title_translations={"en": "Title"},
        description_translations={"en": "A description."},
    )


def test_assemble_yields_consistent_id_sets():
    works = [_work("a", document_hash="a" * 64), _work("b", document_hash="b" * 64)]

    result = assemble(works, run_id="run-1")

    loc_ids = {r.id for r in result.localized.root}
    uni_ids = {r.id for r in result.universal.root}
    assert loc_ids == uni_ids == {"a", "b"}


def test_assemble_quarantines_invalid_work_and_surfaces_it_in_the_report():
    good = _work("a", document_hash="a" * 64)
    bad = EnrichedWork(raw=RawListingEntry(code="bad", title="   "))  # blank title -> invalid

    result = assemble([good, bad], run_id="run-1")

    assert {r.id for r in result.localized.root} == {"a"}
    assert len(result.quality.quarantined) == 1
    assert result.quality.quarantined[0].id == "bad"
    assert result.quality.total_works == 2
    assert result.quality.valid_works == 1


def test_assemble_drops_duplicate_document_hash_from_both_datasets():
    canonical = _work("a", document_hash="a" * 64)
    duplicate = _work("b", document_hash="a" * 64)  # same content as "a"
    unique = _work("c", document_hash="c" * 64)

    result = assemble([canonical, duplicate, unique], run_id="run-1")

    uni_ids = {r.id for r in result.universal.root}
    loc_ids = {r.id for r in result.localized.root}
    assert uni_ids == loc_ids == {"a", "c"}  # "b" dropped as a duplicate of "a"

    assert len(result.quality.duplicate_document_groups) == 1
    group = result.quality.duplicate_document_groups[0]
    assert group.hash == "a" * 64
    assert set(group.ids) == {"a", "b"}
    assert group.canonical == "a"

    # the report reflects everything curation found, duplicates included — not the post-dedup view
    assert result.quality.valid_works == 3


def test_assemble_reports_duplicate_covers_without_dropping_either_work():
    same_cover_a = _work("a", document_hash="a" * 64)
    same_cover_b = _work("b", document_hash="b" * 64).model_copy(update={"cover_hash": "coverhash-a"})

    result = assemble([same_cover_a, same_cover_b], run_id="run-1")

    assert {r.id for r in result.universal.root} == {"a", "b"}
    assert len(result.quality.duplicate_cover_groups) == 1
    assert set(result.quality.duplicate_cover_groups[0].ids) == {"a", "b"}
