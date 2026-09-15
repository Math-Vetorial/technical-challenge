"""Wires the concrete work graph onto the generic engine primitives.

    scrape (paginated) --WorkDiscovered--> [bounded queue] --> per-work lifecycle:
        ├─ translate_title                       (independent of the download branch)
        └─ download --PdfDownloaded--> ┌─ hash ────────Hashed
                                        ├─ cover ───────CoverExtracted
                                        └─ describe ────Described --> translate_description

Barrier: `run()` returns only once every discovered work's whole lifecycle (both branches, and
everything the download branch fans out to) has completed — success or `WorkFailed`, never both
crashing the run. That's `asyncio.gather` all the way down, so no separate "is everyone done yet"
bookkeeping is needed: the outermost gather simply cannot return early.

TODO(step-5): the per-work enrichment gathered here (document_hash, cover_path/hash, description,
translations) isn't persisted to `data/staging/` yet — assembly will read it from wherever Step 5
decides to land it, then run it through `quality.curate.curate_works` and dedup.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

from data_foundry.config import Settings
from data_foundry.config import settings as default_settings
from data_foundry.llm.base import LLMProvider
from data_foundry.llm.factory import get_provider
from data_foundry.logging_setup import get_logger
from data_foundry.orchestrator.engine import STOP, run_worker_pool, with_retry
from data_foundry.orchestrator.events import (
    CoverExtracted,
    Described,
    DescriptionTranslated,
    EventBus,
    Hashed,
    PdfDownloaded,
    TitleTranslated,
    WorkDiscovered,
    WorkFailed,
)
from data_foundry.run import RunContext
from data_foundry.schemas import RawListingEntry, WorkDetail
from data_foundry.stages import covers as covers_stage
from data_foundry.stages import describe as describe_stage
from data_foundry.stages import download as download_stage
from data_foundry.stages import hash as hash_stage
from data_foundry.stages import scrape
from data_foundry.stages import translate as translate_stage

logger = get_logger(__name__)

ONLY_STAGES: tuple[str, ...] = (
    "scrape",
    "download",
    "hash",
    "covers",
    "describe",
    "translate",
    "translate-descriptions",
)


@dataclass
class Counters:
    """Single-threaded (cooperative asyncio -> no lock needed) count accumulator, mirrored into
    the run manifest via `RunContext.update_counts`."""

    _counts: dict[str, int] = field(default_factory=dict)

    def inc(self, key: str, by: int = 1) -> None:
        self._counts[key] = self._counts.get(key, 0) + by

    def snapshot(self) -> dict[str, int]:
        return dict(self._counts)


async def _retrying[R](settings: Settings, semaphore: asyncio.Semaphore, fn: Callable[[], Awaitable[R]]) -> R:
    """Run `fn` under `semaphore` (rate limit) with `with_retry` (retry+backoff) around it."""

    async def call() -> R:
        async with semaphore:
            return await fn()

    return await with_retry(call, max_retries=settings.max_retries, base_delay=settings.retry_base_delay_s)


async def _title_branch(
    raw: RawListingEntry,
    settings: Settings,
    provider: LLMProvider,
    bus: EventBus,
    counters: Counters,
    llm_semaphore: asyncio.Semaphore,
) -> None:
    try:
        result = await _retrying(
            settings, llm_semaphore, lambda: translate_stage.translate_title(raw.title, translate_stage.TARGET_LANGUAGES, provider)
        )
    except Exception as exc:  # noqa: BLE001 - isolate this work's failure, the run keeps going
        bus.publish(WorkFailed(work_id=raw.code, stage="translate_title", error=str(exc)))
        counters.inc("failed")
        return

    for lang, text in result.items():
        bus.publish(TitleTranslated(work_id=raw.code, lang=lang, text=text))
    counters.inc("title_translated")


async def _hash_branch(raw: RawListingEntry, pdf_path: Path, bus: EventBus, counters: Counters) -> None:
    try:
        digest = await asyncio.to_thread(hash_stage.sha256_pdf, pdf_path)
    except OSError as exc:
        bus.publish(WorkFailed(work_id=raw.code, stage="hash", error=str(exc)))
        counters.inc("failed")
        return
    bus.publish(Hashed(work_id=raw.code, sha256=digest))
    counters.inc("hashed")


async def _cover_branch(raw: RawListingEntry, pdf_path: Path, settings: Settings, bus: EventBus, counters: Counters) -> None:
    try:
        cover_path, cover_hash = await asyncio.to_thread(
            covers_stage.extract_cover, pdf_path, settings.raw_dir / "covers"
        )
    except Exception as exc:  # noqa: BLE001 - a corrupt/encrypted PDF shouldn't stop other works
        bus.publish(WorkFailed(work_id=raw.code, stage="cover", error=str(exc)))
        counters.inc("failed")
        return
    bus.publish(CoverExtracted(work_id=raw.code, cover_path=cover_path, cover_hash=cover_hash))
    counters.inc("covers")


async def _describe_branch(
    raw: RawListingEntry,
    pdf_path: Path,
    detail: WorkDetail,
    provider: LLMProvider,
    settings: Settings,
    bus: EventBus,
    counters: Counters,
    llm_semaphore: asyncio.Semaphore,
) -> None:
    try:
        description = await _retrying(
            settings, llm_semaphore, lambda: describe_stage.describe(pdf_path, raw, detail, provider)
        )
    except Exception as exc:  # noqa: BLE001 - a bad render/LLM call shouldn't stop other works
        bus.publish(WorkFailed(work_id=raw.code, stage="describe", error=str(exc)))
        counters.inc("failed")
        return

    bus.publish(Described(work_id=raw.code, description=description))
    counters.inc("described")

    try:
        translations = await _retrying(
            settings,
            llm_semaphore,
            lambda: translate_stage.translate_description(description, translate_stage.TARGET_LANGUAGES, provider),
        )
    except Exception as exc:  # noqa: BLE001 - isolate this work's failure, the run keeps going
        bus.publish(WorkFailed(work_id=raw.code, stage="translate_description", error=str(exc)))
        counters.inc("failed")
        return

    for lang, text in translations.items():
        bus.publish(DescriptionTranslated(work_id=raw.code, lang=lang, text=text))
    counters.inc("description_translated")


async def _download_branch(
    raw: RawListingEntry,
    settings: Settings,
    provider: LLMProvider,
    bus: EventBus,
    counters: Counters,
    dl_semaphore: asyncio.Semaphore,
    llm_semaphore: asyncio.Semaphore,
) -> None:
    try:
        detail = await _retrying(settings, dl_semaphore, lambda: scrape.fetch_detail(raw.code, settings))
        pdf_path = await _retrying(settings, dl_semaphore, lambda: download_stage.download_pdf(raw, detail, settings))
    except Exception as exc:  # noqa: BLE001 - download failing shouldn't stop other works
        bus.publish(WorkFailed(work_id=raw.code, stage="download", error=str(exc)))
        counters.inc("failed")
        return

    bus.publish(PdfDownloaded(work_id=raw.code, pdf_path=pdf_path))
    counters.inc("downloaded")

    await asyncio.gather(
        _hash_branch(raw, pdf_path, bus, counters),
        _cover_branch(raw, pdf_path, settings, bus, counters),
        _describe_branch(raw, pdf_path, detail, provider, settings, bus, counters, llm_semaphore),
    )


async def _process_discovered_work(
    raw: RawListingEntry,
    settings: Settings,
    provider: LLMProvider,
    bus: EventBus,
    ctx: RunContext,
    counters: Counters,
    dl_semaphore: asyncio.Semaphore,
    llm_semaphore: asyncio.Semaphore,
) -> None:
    """One work's full lifecycle. Returning implies every branch reached a terminal state."""
    bus.publish(WorkDiscovered(work_id=raw.code, raw=raw))
    counters.inc("discovered")

    await asyncio.gather(
        _title_branch(raw, settings, provider, bus, counters, llm_semaphore),
        _download_branch(raw, settings, provider, bus, counters, dl_semaphore, llm_semaphore),
    )
    ctx.update_counts(**counters.snapshot())


def _log_failure(event: WorkFailed) -> None:
    logger.warning("work failed work_id=%s stage=%s error=%s", event.work_id, event.stage, event.error)


async def run(
    settings: Settings = default_settings,
    *,
    limit: int | None = None,
    only: str | None = None,
    provider: LLMProvider | None = None,
    bus: EventBus | None = None,
) -> RunContext:
    """Run the full event-driven pipeline (or a single stage in isolation via `only`).

    `bus` is injectable so tests/callers can subscribe to per-work events (Hashed, Described, ...)
    before the run starts — there's nowhere else to observe that enrichment yet (TODO(step-5):
    once it's persisted to `data/staging/`, that becomes the durable way to inspect it).
    """
    provider = provider or get_provider(settings)

    if only is not None:
        return await _run_only_stage(only, settings)

    ctx = RunContext.create(settings)
    bus = bus or EventBus()

    async def on_failed(event: WorkFailed) -> None:
        _log_failure(event)

    bus.subscribe(WorkFailed, on_failed)

    if limit == 0:
        logger.info("limit=0: discovery-only dry run, no network calls made")
        ctx.finish("success")
        return ctx

    counters = Counters()
    dl_semaphore = asyncio.Semaphore(settings.download_concurrency)
    llm_semaphore = asyncio.Semaphore(settings.llm_concurrency)
    queue: asyncio.Queue = asyncio.Queue(maxsize=settings.queue_maxsize)

    async def handle_discovered(raw: RawListingEntry) -> None:
        await _process_discovered_work(raw, settings, provider, bus, ctx, counters, dl_semaphore, llm_semaphore)

    worker_task = asyncio.create_task(
        run_worker_pool(
            input_queue=queue,
            handler=handle_discovered,
            concurrency=settings.download_concurrency,
            sentinel=STOP,
        )
    )

    async for raw in scrape.scrape_listing(settings, limit):
        await queue.put(raw)
    await queue.put(STOP)

    await worker_task
    await bus.drain()

    # Every per-work failure is isolated (WorkFailed + counts), never raised here, so reaching
    # this point means the run itself completed — individual work outcomes are in the manifest.
    ctx.finish("success")
    logger.info("run finished status=success counts=%s manifest=%s", counters.snapshot(), ctx.manifest_path)
    return ctx


async def _run_only_stage(stage: str, settings: Settings) -> RunContext:
    """Run one stage over already-available raw data — for `make <stage>` / debugging.

    TODO(step-5): once per-work state lands in `data/staging/`, every stage (including
    describe/translate, which need catalog context) can be replayed this way.
    """
    if stage not in ONLY_STAGES:
        raise ValueError(f"unknown stage {stage!r}, expected one of {ONLY_STAGES}")

    ctx = RunContext.create(settings)
    pdf_dir = settings.raw_dir / "pdfs"
    pdfs = sorted(pdf_dir.glob("*.pdf")) if pdf_dir.exists() else []

    if stage == "hash":
        for pdf in pdfs:
            digest = await asyncio.to_thread(hash_stage.sha256_pdf, pdf)
            logger.info("hashed code=%s sha256=%s", pdf.stem, digest)
        ctx.update_counts(hashed=len(pdfs))
    elif stage == "covers":
        for pdf in pdfs:
            cover_path, _cover_hash = await asyncio.to_thread(
                covers_stage.extract_cover, pdf, settings.raw_dir / "covers"
            )
            logger.info("cover extracted code=%s path=%s", pdf.stem, cover_path)
        ctx.update_counts(covers=len(pdfs))
    else:
        logger.warning("--only %s needs per-work state from data/staging/ (TODO step-5); nothing to do", stage)

    ctx.finish("success")
    return ctx
