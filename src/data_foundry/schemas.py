"""Pydantic contracts: domain models, the two output datasets, and the run manifest."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, RootModel, field_validator

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_MIN_YEAR = 1400


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
        if v is not None and not (_MIN_YEAR <= v <= datetime.now(UTC).year + 1):
            raise ValueError(f"year out of plausible range: {v}")
        return v


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
