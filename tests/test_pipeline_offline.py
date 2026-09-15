"""Full pipeline run, fully offline: SOURCE=fixtures + a deterministic mock LLM. No network."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from data_foundry import pipeline
from data_foundry.config import Settings
from data_foundry.llm.mock import MockProvider
from data_foundry.orchestrator.events import (
    CoverExtracted,
    Described,
    DescriptionTranslated,
    EventBus,
    Hashed,
    TitleTranslated,
    WorkFailed,
)


def _settings(tmp_path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        source="fixtures",
        llm_provider="mock",
        download_concurrency=2,
        llm_concurrency=2,
        max_retries=0,
    )


class _Recorder:
    """Collects the events a full run emits, for asserting on per-work enrichment directly
    (the curated/staged files are also inspected separately, in their own tests)."""

    def __init__(self) -> None:
        self.hashed: dict[str, str] = {}
        self.covers: dict[str, tuple[str, str]] = {}
        self.described: dict[str, str | None] = {}
        self.title_translated: dict[str, dict[str, str | None]] = {}
        self.description_translated: dict[str, dict[str, str | None]] = {}
        self.failures: list[WorkFailed] = []

    def attach(self, bus: EventBus) -> None:
        async def on_hashed(e: Hashed) -> None:
            self.hashed[e.work_id] = e.sha256

        async def on_cover(e: CoverExtracted) -> None:
            self.covers[e.work_id] = (str(e.cover_path), e.cover_hash)

        async def on_described(e: Described) -> None:
            self.described[e.work_id] = e.description

        async def on_title(e: TitleTranslated) -> None:
            self.title_translated.setdefault(e.work_id, {})[e.lang] = e.text

        async def on_desc(e: DescriptionTranslated) -> None:
            self.description_translated.setdefault(e.work_id, {})[e.lang] = e.text

        async def on_failed(e: WorkFailed) -> None:
            self.failures.append(e)

        bus.subscribe(Hashed, on_hashed)
        bus.subscribe(CoverExtracted, on_cover)
        bus.subscribe(Described, on_described)
        bus.subscribe(TitleTranslated, on_title)
        bus.subscribe(DescriptionTranslated, on_desc)
        bus.subscribe(WorkFailed, on_failed)


def _run_offline(tmp_path) -> tuple[Settings, _Recorder, object]:
    settings = _settings(tmp_path)
    bus = EventBus()
    recorder = _Recorder()
    recorder.attach(bus)

    ctx = asyncio.run(pipeline.run(settings, limit=3, provider=MockProvider(), bus=bus))
    return settings, recorder, ctx


def test_pipeline_run_offline_enriches_three_works_with_no_network(tmp_path):
    settings, recorder, ctx = _run_offline(tmp_path)

    assert ctx.manifest.status == "success"
    assert recorder.failures == []

    expected_ids = {"fixture-001", "fixture-002", "fixture-003"}
    assert set(recorder.hashed) == expected_ids
    assert set(recorder.covers) == expected_ids
    assert set(recorder.described) == expected_ids
    assert set(recorder.title_translated) == expected_ids
    assert set(recorder.description_translated) == expected_ids

    for digest in recorder.hashed.values():
        assert len(digest) == 64  # sha256 hex

    assert recorder.described["fixture-001"] == "[mock-description] A Cidade e as Serras (obra fixture-001)"
    assert recorder.title_translated["fixture-001"] == {
        "en": "[en] A Cidade e as Serras",
        "es": "[es] A Cidade e as Serras",
        "fr": "[fr] A Cidade e as Serras",
    }
    description = recorder.described["fixture-001"]
    assert recorder.description_translated["fixture-001"] == {
        "en": f"[en] {description}",
        "es": f"[es] {description}",
        "fr": f"[fr] {description}",
    }

    pdfs = sorted((settings.raw_dir / "pdfs").glob("*.pdf"))
    assert [p.stem for p in pdfs] == ["fixture-001", "fixture-002", "fixture-003"]

    counts = ctx.manifest.counts
    assert counts["discovered"] == 3
    assert counts["downloaded"] == 3
    assert counts["hashed"] == 3
    assert counts["covers"] == 3
    assert counts["described"] == 3
    assert counts["title_translated"] == 3
    assert counts["description_translated"] == 3
    assert counts.get("failed", 0) == 0


def test_pipeline_run_offline_universal_metadata_has_portable_cover_paths(tmp_path):
    """The persisted dataset must never bake in this machine's absolute path (regression: it did,
    via EnrichedWork.cover_path flowing straight through to UniversalRecord.cover_path)."""
    _, _, ctx = _run_offline(tmp_path)

    data = json.loads((ctx.run_dir / "universal_metadata.json").read_text(encoding="utf-8"))
    assert len(data) == 3
    for entry in data:
        cover_path = entry["cover_path"]
        assert cover_path is not None
        assert not Path(cover_path).is_absolute()
        assert cover_path.startswith("raw/covers/")


def test_pipeline_run_offline_is_deterministic_across_runs(tmp_path):
    _, recorder_1, _ = _run_offline(tmp_path / "run1")
    _, recorder_2, _ = _run_offline(tmp_path / "run2")

    assert recorder_1.hashed == recorder_2.hashed
    assert recorder_1.described == recorder_2.described
    assert recorder_1.title_translated == recorder_2.title_translated
    assert recorder_1.description_translated == recorder_2.description_translated
