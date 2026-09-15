"""Build a `QualityReport`: counts, missing-per-field, coverage, duplicates, quarantined.

`dump_json` (schemas.py) writes any Pydantic model, including this report, so it's already
dumpable. TODO(step-5): the orchestrator writes it to `quality_report.json` and feeds it to
`RunContext.set_quality(...)`.
"""

from __future__ import annotations

from collections.abc import Callable

from data_foundry.quality.curate import CurateResult
from data_foundry.schemas import (
    DuplicateGroup,
    LocalizedRecord,
    QualityReport,
    UniversalRecord,
)

_LANGS = ("pt", "en", "es", "fr")

_LOCALIZED_FIELDS: dict[str, Callable[[LocalizedRecord], object]] = {
    **{f"title_{lang}": (lambda r, lang=lang: getattr(r.title, lang)) for lang in _LANGS},
    **{f"description_{lang}": (lambda r, lang=lang: getattr(r.description, lang)) for lang in _LANGS},
}

_UNIVERSAL_FIELDS: dict[str, Callable[[UniversalRecord], object]] = {
    "cover": lambda r: r.cover_path,
    "document_hash": lambda r: r.document_hash,
    "year": lambda r: r.year,
    "category": lambda r: r.category,
    "accesses": lambda r: r.accesses,
}


def _coverage_and_missing(
    records: list, fields: dict[str, Callable[[object], object]]
) -> tuple[dict[str, float], dict[str, int]]:
    total = len(records)
    coverage: dict[str, float] = {}
    missing: dict[str, int] = {}
    for name, accessor in fields.items():
        present = sum(1 for r in records if accessor(r) not in (None, ""))
        coverage[name] = present / total if total else 0.0
        missing[name] = total - present
    return coverage, missing


def build_quality_report(
    curate_result: CurateResult,
    doc_groups: list[DuplicateGroup],
    cover_groups: list[DuplicateGroup],
) -> QualityReport:
    valid_works = len(curate_result.localized)
    total_works = valid_works + len(curate_result.quarantined)

    loc_coverage, loc_missing = _coverage_and_missing(curate_result.localized, _LOCALIZED_FIELDS)
    uni_coverage, uni_missing = _coverage_and_missing(curate_result.universal, _UNIVERSAL_FIELDS)

    return QualityReport(
        total_works=total_works,
        valid_works=valid_works,
        quarantined=curate_result.quarantined,
        duplicate_document_groups=doc_groups,
        duplicate_cover_groups=cover_groups,
        missing_by_field={**loc_missing, **uni_missing},
        coverage={**loc_coverage, **uni_coverage},
    )
