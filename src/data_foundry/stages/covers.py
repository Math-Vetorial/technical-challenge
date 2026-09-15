"""Cover stage: render a PDF's first page to PNG, content-addressed by image hash.

Idempotent by hash: two works whose cover renders to the same bytes (a reused scan, a shared
front matter page) share one file on disk — `dedup.find_duplicate_covers` surfaces that later.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pymupdf as fitz


def extract_cover(pdf_path: Path, out_dir: Path) -> tuple[Path, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(str(pdf_path))
    try:
        png_bytes = doc[0].get_pixmap(dpi=150).tobytes("png")
    finally:
        doc.close()

    image_hash = hashlib.sha256(png_bytes).hexdigest()
    cover_path = out_dir / f"{image_hash}.png"
    if not cover_path.exists():
        cover_path.write_bytes(png_bytes)
    return cover_path, image_hash
