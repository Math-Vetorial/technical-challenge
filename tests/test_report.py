from data_foundry.quality.curate import CurateResult
from data_foundry.quality.report import build_quality_report
from data_foundry.schemas import (
    DuplicateGroup,
    LangField,
    LocalizedRecord,
    QuarantinedRecord,
    UniversalRecord,
)


def test_build_quality_report_computes_coverage_and_missing():
    localized = [
        LocalizedRecord(id="a", title=LangField(pt="A", en="A"), description=LangField(pt="Desc")),
        LocalizedRecord(id="b", title=LangField(pt="B"), description=LangField()),
    ]
    universal = [
        UniversalRecord(id="a", document_hash="a" * 64, cover_path="cover_a.png", year=1900),
        UniversalRecord(id="b", document_hash=None, cover_path=None, year=None),
    ]
    quarantined = [QuarantinedRecord(id="c", reason="title.pt must be non-empty", raw={})]
    curate_result = CurateResult(localized=localized, universal=universal, quarantined=quarantined)

    doc_groups = [DuplicateGroup(hash="a" * 64, ids=["a"], canonical="a")]
    cover_groups: list[DuplicateGroup] = []

    report = build_quality_report(curate_result, doc_groups, cover_groups)

    assert report.total_works == 3
    assert report.valid_works == 2
    assert report.quarantined == quarantined
    assert report.duplicate_document_groups == doc_groups
    assert report.duplicate_cover_groups == []

    assert report.coverage["title_pt"] == 1.0
    assert report.coverage["title_en"] == 0.5
    assert report.coverage["description_pt"] == 0.5
    assert report.coverage["cover"] == 0.5
    assert report.coverage["document_hash"] == 0.5

    assert report.missing_by_field["title_en"] == 1
    assert report.missing_by_field["description_pt"] == 1
    assert report.missing_by_field["cover"] == 1


def test_build_quality_report_empty_input_does_not_divide_by_zero():
    report = build_quality_report(CurateResult(), [], [])

    assert report.total_works == 0
    assert report.valid_works == 0
    assert report.coverage["title_pt"] == 0.0
