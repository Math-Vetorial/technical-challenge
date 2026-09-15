"""Pydantic contracts: domain models, the two output datasets, and the run manifest."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, RootModel, field_validator

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
MIN_PLAUSIBLE_YEAR = 1400


class LangField(BaseModel):
    """A value that varies by language."""

    pt: str | None = None
    en: str | None = None
    es: str | None = None
    fr: str | None = None


# --- Domain / intermediate models (used by later stages) ------------------------------------


class RawListingEntry(BaseModel):
    """As scraped from the catalog listing. Strings as-is — cleaning happens in Step 2."""

    code: str
    title: str
    author: str | None = None
    source: str | None = None
    format: str | None = None
    size: str | None = None
    accesses: str | None = None


class WorkDetail(BaseModel):
    """As scraped from a work's detail page."""

    code: str
    category: str | None = None
    language: str | None = None
    institution: str | None = None
    year: str | None = None
    accesses: str | None = None
    download_url: str | None = None


# --- Output models — the hard contract -------------------------------------------------------


class LocalizedRecord(BaseModel):
    id: str
    author: str | None = None
    title: LangField
    description: LangField = Field(default_factory=LangField)

    @field_validator("title")
    @classmethod
    def _title_pt_required(cls, v: LangField) -> LangField:
        if not v.pt or not v.pt.strip():
            raise ValueError("title.pt must be non-empty")
        return v


class UniversalRecord(BaseModel):
    id: str
    document_hash: str | None = None
    cover_path: str | None = None
    accesses: int | None = None
    size_bytes: int | None = None
    category: str | None = None
    year: int | None = None
    # optional expansion fields (challenge allows expanding, never shrinking, the contract)
    language: str | None = None
    institution: str | None = None
    source: str | None = None
    run_id: str | None = None

    @field_validator("document_hash")
    @classmethod
    def _validate_document_hash(cls, v: str | None) -> str | None:
        if v is not None and not _HEX64.match(v):
            raise ValueError("document_hash must be 64 hex characters")
        return v

    @field_validator("year")
    @classmethod
    def _validate_year(cls, v: int | None) -> int | None:
        if v is not None and not (MIN_PLAUSIBLE_YEAR <= v <= datetime.now(UTC).year + 1):
            raise ValueError(f"year out of plausible range: {v}")
        return v


class EnrichedWork(BaseModel):
    """Everything gathered about one work before curation — the silver layer.

    Built by `staging.accumulator.WorkAccumulator` from enrichment events as a run progresses,
    flushed to `data/staging/works/<code>.json`, and handed to `quality.curate.curate_works` at
    assembly time.
    """

    raw: RawListingEntry
    detail: WorkDetail | None = None
    pdf_path: str | None = None
    document_hash: str | None = None
    cover_path: str | None = None
    cover_hash: str | None = None
    size_bytes: int | None = None
    description: str | None = None  # PT description, as produced by the vision LLM
    title_translations: dict[str, str] = Field(default_factory=dict)
    description_translations: dict[str, str] = Field(default_factory=dict)


class QuarantinedRecord(BaseModel):
    """A work that failed validation during curation — isolated, not dropped silently."""

    id: str
    reason: str
    raw: dict[str, Any]


class DuplicateGroup(BaseModel):
    """Ids that share a content hash. `canonical` is kept, the rest are duplicates of it."""

    hash: str
    ids: list[str]
    canonical: str


class QualityReport(BaseModel):
    total_works: int
    valid_works: int
    quarantined: list[QuarantinedRecord] = Field(default_factory=list)
    duplicate_document_groups: list[DuplicateGroup] = Field(default_factory=list)
    duplicate_cover_groups: list[DuplicateGroup] = Field(default_factory=list)
    missing_by_field: dict[str, int] = Field(default_factory=dict)
    coverage: dict[str, float] = Field(default_factory=dict)


class LocalizedCatalog(RootModel[list[LocalizedRecord]]):
    pass


class UniversalMetadata(RootModel[list[UniversalRecord]]):
    pass


# --- Manifest ("datasheet") -------------------------------------------------------------------


class RunManifest(BaseModel):
    run_id: str
    started_at: datetime
    finished_at: datetime | None = None
    status: Literal["running", "success", "failed"] = "running"
    git_sha: str | None = None
    config_snapshot: dict[str, Any] = Field(default_factory=dict)
    source_url: str | None = None
    counts: dict[str, int] = Field(default_factory=dict)
    quality: dict[str, Any] = Field(default_factory=dict)  # TODO(step-2): filled by the quality report
    outputs: dict[str, str] = Field(default_factory=dict)  # TODO(step-5): logical name -> relative path
    output_hashes: dict[str, str] = Field(default_factory=dict)  # TODO(step-5): logical name -> sha256
    tool_versions: dict[str, str] = Field(default_factory=dict)


def dump_json(model: BaseModel, path: Path) -> None:
    """Write a Pydantic model as UTF-8 JSON, non-ASCII preserved, 2-space indent."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(model.model_dump_json(indent=2), encoding="utf-8")
