"""Validates the two contract datasets against a real curated run, produced offline
(SOURCE=fixtures + mock LLM, see `conftest.py`'s `offline_curated_run` fixture) — no network, no
GPU, and no skip. `make run` produces the exact same shape from >=10 real books.

Path note: this used to read the legacy flat `data/output/`. Since Step 5 it reads
`data/curated/<run_id>/` via the `latest` pointer (resolving the symlink or `latest.txt`).
"""

from __future__ import annotations

import json
from pathlib import Path

MIN_ENTRIES = 10

EXPECTED_FILES = ["localized_catalog.json", "universal_metadata.json", "quality_report.json"]


def _load_json(output_dir: Path, name: str):
    with open(output_dir / name, encoding="utf-8") as f:
        return json.load(f)


def test_output_files_exist(curated_latest_dir):
    for filename in EXPECTED_FILES:
        path = curated_latest_dir / filename
        assert path.exists() and path.stat().st_size > 0, f"{filename} missing or empty"


def test_minimum_pdfs(raw_pdfs_dir):
    assert len(list(raw_pdfs_dir.glob("*.pdf"))) >= MIN_ENTRIES


def test_localized_catalog(curated_latest_dir):
    data = _load_json(curated_latest_dir, "localized_catalog.json")
    assert len(data) >= MIN_ENTRIES
    for entry in data:
        assert entry.get("id") and entry.get("title", {}).get("pt")


def test_universal_metadata(curated_latest_dir):
    data = _load_json(curated_latest_dir, "universal_metadata.json")
    assert len(data) >= MIN_ENTRIES
    for entry in data:
        assert entry.get("id") and entry.get("document_hash")


def test_outputs_consistent(curated_latest_dir):
    loc_ids = {e["id"] for e in _load_json(curated_latest_dir, "localized_catalog.json")}
    uni_ids = {e["id"] for e in _load_json(curated_latest_dir, "universal_metadata.json")}
    assert loc_ids == uni_ids
