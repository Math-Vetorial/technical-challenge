"""Download stage: fetch a work's PDF into the raw (bronze) layer, idempotently.

Retry+backoff and concurrency limiting are the engine's job (`orchestrator.engine.with_retry`,
called by `pipeline.py` around this function) — this module only knows how to fetch one PDF and
raises on a bad response, so the engine can isolate and retry the failure per work.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from curl_cffi import requests as cffi_requests

from data_foundry.config import Settings
from data_foundry.schemas import RawListingEntry, WorkDetail

_SESSION = cffi_requests.Session(impersonate="chrome")
_MIN_VALID_PDF_BYTES = 1000


def _download_sync(url: str, timeout: int) -> bytes:
    resp = _SESSION.get(url, timeout=timeout)
    if resp.status_code != 200 or len(resp.content) < _MIN_VALID_PDF_BYTES:
        raise ConnectionError(f"bad download response status={resp.status_code} bytes={len(resp.content)}")
    return resp.content


async def download_pdf(raw: RawListingEntry, detail: WorkDetail, settings: Settings) -> Path:
    """Download `detail.download_url` to `data/raw/pdfs/<code>.pdf`. Skips if already present."""
    pdf_dir = settings.raw_dir / "pdfs"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = pdf_dir / f"{raw.code}.pdf"
    if pdf_path.exists():
        return pdf_path

    if not detail.download_url:
        raise ValueError(f"no download_url for work {raw.code}")

    content = await asyncio.to_thread(_download_sync, detail.download_url, settings.request_timeout_s)
    pdf_path.write_bytes(content)
    return pdf_path
