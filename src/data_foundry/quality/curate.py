"""Record-level curation: raw scraped/enriched data -> validated records.

**Quarantine over crash**: validation-as-code fails fast per record (Pydantic), but one bad work
must not kill the run. `curate_works` isolates the failure into a `QuarantinedRecord` and keeps
going — correctness and robustness together. TODO(step-3): the orchestrator calls this once all
per-work enrichment (download/hash/describe/translate/cover) has landed for a work, or in a
barrier batch once every work is processed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from data_foundry.quality.normalize import (
    clean_text,
    normalize_lang,
    null_if_sentinel,
    parse_int_locale,
    parse_year,
)
from data_foundry.schemas import (
    EnrichedWork,
    LangField,
    LocalizedRecord,
    QuarantinedRecord,
    RawListingEntry,
    UniversalRecord,
    WorkDetail,
)


def build_localized(
    raw: RawListingEntry,
    title_translations: dict[str, str] | None = None,
    description: str | None = None,
    desc_translations: dict[str, str] | None = None,
) -> LocalizedRecord:
    title_translations = title_translations or {}
    desc_translations = desc_translations or {}
    return LocalizedRecord(
        id=raw.code,
        author=clean_text(null_if_sentinel(raw.author)),
        title=LangField(
            pt=clean_text(raw.title),
            en=clean_text(title_translations.get("en")),
            es=clean_text(title_translations.get("es")),
            fr=clean_text(title_translations.get("fr")),
        ),
        description=LangField(
            pt=clean_text(description),
            en=clean_text(desc_translations.get("en")),
            es=clean_text(desc_translations.get("es")),
            fr=clean_text(desc_translations.get("fr")),
        ),
    )


def _relative_cover_path(cover_path: str | None, data_dir: Path | None) -> str | None:
    """The persisted datasets must be portable — never bake this machine's absolute path in.

    Internal state (EnrichedWork, staging JSON) can stay absolute; only at the point a
    UniversalRecord is built do we relativize to `data_dir` (e.g. `raw/covers/<hash>.png`).
    """
    if cover_path is None or data_dir is None:
        return cover_path
    try:
        return str(Path(cover_path).relative_to(data_dir))
    except ValueError:
        return cover_path  # not under data_dir (e.g. an already-relative test path) -> leave as-is


def build_universal(
    raw: RawListingEntry,
    detail: WorkDetail | None,
    doc_hash: str | None,
    cover_path: str | None,
    size_bytes: int | None,
    run_id: str | None = None,
    data_dir: Path | None = None,
) -> UniversalRecord:
    detail = detail or WorkDetail(code=raw.code)
    return UniversalRecord(
        id=raw.code,
        document_hash=doc_hash,
        cover_path=_relative_cover_path(cover_path, data_dir),
        accesses=parse_int_locale(detail.accesses or raw.accesses),
        size_bytes=size_bytes,
        category=clean_text(null_if_sentinel(detail.category)),
        year=parse_year(null_if_sentinel(detail.year)),
        language=normalize_lang(null_if_sentinel(detail.language)),
        institution=clean_text(null_if_sentinel(detail.institution)),
        source=clean_text(null_if_sentinel(raw.source)),
        run_id=run_id,
    )


@dataclass
class CurateResult:
    localized: list[LocalizedRecord] = field(default_factory=list)
    universal: list[UniversalRecord] = field(default_factory=list)
    quarantined: list[QuarantinedRecord] = field(default_factory=list)


def curate_works(
    works: list[EnrichedWork], run_id: str | None = None, data_dir: Path | None = None
) -> CurateResult:
    """Build + validate both records per work; quarantine instead of raising on failure."""
    result = CurateResult()
    for work in works:
        try:
            localized = build_localized(
                raw=work.raw,
                title_translations=work.title_translations,
                description=work.description,
                desc_translations=work.description_translations,
            )
            universal = build_universal(
                raw=work.raw,
                detail=work.detail,
                doc_hash=work.document_hash,
                cover_path=work.cover_path,
                size_bytes=work.size_bytes,
                run_id=run_id,
                data_dir=data_dir,
            )
        except ValidationError as exc:
            result.quarantined.append(
                QuarantinedRecord(id=work.raw.code, reason=str(exc), raw=work.model_dump(mode="json"))
            )
            continue
        result.localized.append(localized)
        result.universal.append(universal)
    return result
