"""Session-wide fixtures shared across the test suite.

`offline_curated_settings` runs the pipeline fully offline (SOURCE=fixtures + a deterministic mock
LLM, no network/GPU) once per test session, producing a genuine versioned curated run — the same
code path `make run` uses for real books — so `test_outputs.py` can validate the two contract
datasets end-to-end instead of relying on hand-built sample files.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from data_foundry import pipeline
from data_foundry.config import Settings
from data_foundry.llm.mock import MockProvider

OFFLINE_WORK_COUNT = 12  # >= test_outputs.py's MIN_ENTRIES


def _resolve_latest(curated_dir: Path) -> Path:
    latest = curated_dir / "latest"
    if latest.is_symlink() or latest.exists():
        return latest.resolve()
    run_id = (curated_dir / "latest.txt").read_text(encoding="utf-8").strip()
    return curated_dir / "runs" / run_id


@pytest.fixture(scope="session")
def offline_curated_settings(tmp_path_factory) -> Settings:
    """Settings for a fully offline pipeline run, isolated under a session-scoped temp dir."""
    data_dir = tmp_path_factory.mktemp("offline-pipeline") / "data"
    return Settings(data_dir=data_dir, source="fixtures", llm_provider="mock")


@pytest.fixture(scope="session")
def offline_curated_run(offline_curated_settings: Settings) -> Settings:
    """Runs the offline pipeline once for the session; returns the settings used (so callers can
    reach `raw_dir`/`curated_dir`/etc.). Session-scoped: every test sees the same run."""
    ctx = asyncio.run(
        pipeline.run(offline_curated_settings, limit=OFFLINE_WORK_COUNT, provider=MockProvider())
    )
    assert ctx.manifest.status == "success"
    return offline_curated_settings


@pytest.fixture(scope="session")
def curated_latest_dir(offline_curated_run: Settings) -> Path:
    return _resolve_latest(offline_curated_run.curated_dir)


@pytest.fixture(scope="session")
def raw_pdfs_dir(offline_curated_run: Settings) -> Path:
    return offline_curated_run.raw_dir / "pdfs"
