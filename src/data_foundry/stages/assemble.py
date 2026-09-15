"""Assembly stage (refactor of scripts 07/08): curate -> dedup -> the two contract datasets +
quality report. Consumes the `EnrichedWork` records `staging.accumulator.WorkAccumulator` built
from the enrichment events — this is where the silver layer becomes the gold layer.
"""

from __future__ import annotations

from dataclasses import dataclass

from data_foundry.quality.curate import curate_works
from data_foundry.quality.dedup import dedup_by_document_hash, find_duplicate_covers
from data_foundry.quality.report import build_quality_report
from data_foundry.schemas import (
    EnrichedWork,
    LocalizedCatalog,
    QualityReport,
    UniversalMetadata,
)


@dataclass
class AssembleResult:
    localized: LocalizedCatalog
    universal: UniversalMetadata
    quality: QualityReport


def assemble(works: list[EnrichedWork], run_id: str | None = None) -> AssembleResult:
    """Curate every work, dedup by `document_hash`, keep both datasets aligned to one id set."""
    curate_result = curate_works(works, run_id=run_id)

    deduped_universal, doc_groups = dedup_by_document_hash(curate_result.universal)
    cover_groups = find_duplicate_covers({work.raw.code: work.cover_hash for work in works})

    # Consistency by construction: drop from `localized` whatever dedup dropped from `universal`,
    # so the two datasets always share exactly one id set — the invariant test_outputs.py checks.
    kept_ids = {record.id for record in deduped_universal}
    deduped_localized = [record for record in curate_result.localized if record.id in kept_ids]

    # The report reflects everything curation found, duplicates included as their own dimension —
    # not the post-dedup view. "Dedup surfaces, doesn't hide" applies to the report too.
    quality = build_quality_report(curate_result, doc_groups, cover_groups)

    return AssembleResult(
        localized=LocalizedCatalog(deduped_localized),
        universal=UniversalMetadata(deduped_universal),
        quality=quality,
    )
