import asyncio
import json
from pathlib import Path

from data_foundry.orchestrator.events import (
    CoverExtracted,
    Described,
    DescriptionTranslated,
    EventBus,
    Hashed,
    PdfDownloaded,
    TitleTranslated,
    WorkDiscovered,
)
from data_foundry.schemas import RawListingEntry, WorkDetail
from data_foundry.staging.accumulator import WorkAccumulator


def test_accumulator_builds_enriched_work_from_a_sequence_of_events(tmp_path):
    async def scenario() -> None:
        pdf_path = tmp_path / "obra1.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 fake bytes")

        raw = RawListingEntry(code="obra1", title="Dom Casmurro", author="Machado de Assis")
        detail = WorkDetail(code="obra1", category="Romance", language="Português", year="1899")

        bus = EventBus()
        acc = WorkAccumulator()
        acc.subscribe_to(bus)

        bus.publish(WorkDiscovered(work_id="obra1", raw=raw))
        bus.publish(PdfDownloaded(work_id="obra1", pdf_path=pdf_path, detail=detail))
        bus.publish(Hashed(work_id="obra1", sha256="a" * 64))
        bus.publish(CoverExtracted(work_id="obra1", cover_path=tmp_path / "obra1.png", cover_hash="b" * 64))
        bus.publish(Described(work_id="obra1", description="Um romance clássico."))
        bus.publish(TitleTranslated(work_id="obra1", lang="en", text="Dom Casmurro"))
        bus.publish(DescriptionTranslated(work_id="obra1", lang="en", text="A classic novel."))
        await bus.drain()

        works = acc.works()
        assert len(works) == 1
        work = works[0]

        assert work.raw.code == "obra1"
        assert work.detail is not None and work.detail.category == "Romance"
        assert work.pdf_path == str(pdf_path)
        assert work.size_bytes == pdf_path.stat().st_size
        assert work.document_hash == "a" * 64
        assert work.cover_hash == "b" * 64
        assert work.description == "Um romance clássico."
        assert work.title_translations == {"en": "Dom Casmurro"}
        assert work.description_translations == {"en": "A classic novel."}

        paths = acc.flush(tmp_path / "staging")
        assert len(paths) == 1
        flushed = json.loads(paths[0].read_text(encoding="utf-8"))
        assert flushed["raw"]["code"] == "obra1"
        assert flushed["document_hash"] == "a" * 64

    asyncio.run(scenario())


def test_accumulator_flush_is_idempotent(tmp_path):
    async def scenario() -> None:
        bus = EventBus()
        acc = WorkAccumulator()
        acc.subscribe_to(bus)

        bus.publish(WorkDiscovered(work_id="obra1", raw=RawListingEntry(code="obra1", title="Título")))
        await bus.drain()

        staging_dir = tmp_path / "staging"
        first = acc.flush(staging_dir)
        second = acc.flush(staging_dir)

        assert first == second
        assert len(list((staging_dir / "works").glob("*.json"))) == 1

    asyncio.run(scenario())


def test_accumulator_ignores_missing_or_empty_translations(tmp_path):
    async def scenario() -> None:
        bus = EventBus()
        acc = WorkAccumulator()
        acc.subscribe_to(bus)

        bus.publish(WorkDiscovered(work_id="obra1", raw=RawListingEntry(code="obra1", title="Título")))
        bus.publish(TitleTranslated(work_id="obra1", lang="en", text=None))
        bus.publish(TitleTranslated(work_id="obra1", lang="es", text=""))
        await bus.drain()

        work = acc.works()[0]
        assert work.title_translations == {}

    asyncio.run(scenario())


def test_flush_creates_staging_directory(tmp_path: Path):
    acc = WorkAccumulator()
    staging_dir = tmp_path / "does" / "not" / "exist" / "yet"
    paths = acc.flush(staging_dir)
    assert paths == []
    assert (staging_dir / "works").is_dir()
