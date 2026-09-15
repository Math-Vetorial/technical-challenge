"""Describe stage: render page(s) to images, ask the injected LLM provider for a PT description.

The provider is a Protocol (`llm.base.LLMProvider`) — this module never imports a concrete
client. Rate limiting (one `llm_concurrency` semaphore) and retry live in `pipeline.py`, around
the call to `describe(...)`.
"""

from __future__ import annotations

import base64
from pathlib import Path

import pymupdf as fitz

from data_foundry.llm.base import LLMProvider
from data_foundry.schemas import RawListingEntry, WorkDetail

MAX_PAGES = 1


def render_pages_base64(pdf_path: Path, max_pages: int = MAX_PAGES) -> list[str]:
    doc = fitz.open(str(pdf_path))
    try:
        return [
            base64.b64encode(doc[i].get_pixmap(dpi=150).tobytes("png")).decode("utf-8")
            for i in range(min(max_pages, len(doc)))
        ]
    finally:
        doc.close()


def _metadata_context(raw: RawListingEntry, detail: WorkDetail | None) -> dict[str, str]:
    fields = {
        "code": raw.code,
        "category": detail.category if detail else None,
        "language": detail.language if detail else None,
        "institution": detail.institution if detail else None,
        "year": detail.year if detail else None,
    }
    return {k: v for k, v in fields.items() if v}


async def describe(
    pdf_path: Path, raw: RawListingEntry, detail: WorkDetail | None, provider: LLMProvider
) -> str | None:
    images = render_pages_base64(pdf_path)
    if not images:
        return None
    return await provider.describe(images, raw.title, _metadata_context(raw, detail))
