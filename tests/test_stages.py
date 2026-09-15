"""Offline-only slices of the stage functions. No network, no LLM."""

from __future__ import annotations

import hashlib

import pymupdf as fitz

from data_foundry.stages.covers import extract_cover
from data_foundry.stages.hash import sha256_pdf


def test_sha256_pdf_matches_hashlib(tmp_path):
    content = b"%PDF-1.4 not a real pdf, just bytes to hash\n" * 100
    path = tmp_path / "doc.pdf"
    path.write_bytes(content)

    assert sha256_pdf(path) == hashlib.sha256(content).hexdigest()


def _make_minimal_pdf(path) -> None:
    doc = fitz.open()
    try:
        page = doc.new_page()
        page.insert_text((72, 72), "Hello, cover.")
        doc.save(str(path))
    finally:
        doc.close()


def test_extract_cover_is_idempotent_by_hash(tmp_path):
    pdf_path = tmp_path / "book.pdf"
    _make_minimal_pdf(pdf_path)
    out_dir = tmp_path / "covers"

    cover_path, cover_hash = extract_cover(pdf_path, out_dir)

    assert cover_path.exists()
    assert cover_path.name == f"{cover_hash}.png"
    assert len(cover_hash) == 64

    # Extracting again (same content) reuses the same file instead of duplicating it.
    cover_path_2, cover_hash_2 = extract_cover(pdf_path, out_dir)
    assert cover_path_2 == cover_path
    assert cover_hash_2 == cover_hash
    assert len(list(out_dir.glob("*.png"))) == 1
