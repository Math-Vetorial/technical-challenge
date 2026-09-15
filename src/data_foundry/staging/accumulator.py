"""`WorkAccumulator` is what makes the event bus functional rather than decorative: it subscribes
to the enrichment events and builds one `EnrichedWork` per work in memory, purely by reacting to
`Hashed`/`Described`/`CoverExtracted`/... — the silver layer falls out of the event stream itself.

Safe as a plain in-memory dict: asyncio is single-threaded/cooperative, and a handler never awaits
mid-mutation, so there's no interleaving to race. `flush()` is idempotent — it always overwrites
the per-work staging file with the current in-memory state.
"""

from __future__ import annotations

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
from data_foundry.schemas import EnrichedWork, dump_json


class WorkAccumulator:
    def __init__(self) -> None:
        self._works: dict[str, EnrichedWork] = {}

    def works(self) -> list[EnrichedWork]:
        return list(self._works.values())

    def _update(self, work_id: str, **changes: object) -> None:
        self._works[work_id] = self._works[work_id].model_copy(update=changes)

    async def _on_discovered(self, event: WorkDiscovered) -> None:
        self._works[event.work_id] = EnrichedWork(raw=event.raw)

    async def _on_downloaded(self, event: PdfDownloaded) -> None:
        size_bytes = event.pdf_path.stat().st_size if event.pdf_path.exists() else None
        self._update(event.work_id, pdf_path=str(event.pdf_path), detail=event.detail, size_bytes=size_bytes)

    async def _on_hashed(self, event: Hashed) -> None:
        self._update(event.work_id, document_hash=event.sha256)

    async def _on_cover_extracted(self, event: CoverExtracted) -> None:
        self._update(event.work_id, cover_path=str(event.cover_path), cover_hash=event.cover_hash)

    async def _on_described(self, event: Described) -> None:
        self._update(event.work_id, description=event.description)

    async def _on_title_translated(self, event: TitleTranslated) -> None:
        if not event.text:
            return
        work = self._works[event.work_id]
        self._update(event.work_id, title_translations={**work.title_translations, event.lang: event.text})

    async def _on_description_translated(self, event: DescriptionTranslated) -> None:
        if not event.text:
            return
        work = self._works[event.work_id]
        self._update(
            event.work_id, description_translations={**work.description_translations, event.lang: event.text}
        )

    def subscribe_to(self, bus: EventBus) -> None:
        bus.subscribe(WorkDiscovered, self._on_discovered)
        bus.subscribe(PdfDownloaded, self._on_downloaded)
        bus.subscribe(Hashed, self._on_hashed)
        bus.subscribe(CoverExtracted, self._on_cover_extracted)
        bus.subscribe(Described, self._on_described)
        bus.subscribe(TitleTranslated, self._on_title_translated)
        bus.subscribe(DescriptionTranslated, self._on_description_translated)

    def flush(self, staging_dir: Path) -> list[Path]:
        """Write every accumulated work to `staging_dir/works/<code>.json`. Idempotent."""
        works_dir = staging_dir / "works"
        works_dir.mkdir(parents=True, exist_ok=True)
        paths = []
        for work_id, work in self._works.items():
            path = works_dir / f"{work_id}.json"
            dump_json(work, path)
            paths.append(path)
        return paths
