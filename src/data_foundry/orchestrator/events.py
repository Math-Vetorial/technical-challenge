"""Typed events describing a work's progress, plus a minimal async pub/sub bus.

The bus is for fan-out notification (logging, count bookkeeping) — the actual backpressure
boundary between scrape and download is a bounded `asyncio.Queue` (see `pipeline.py`), per the
spec's "events on an async bus and/or bounded queues" — we use both, for what each is good at.
"""

from __future__ import annotations

import asyncio
import functools
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from data_foundry.logging_setup import get_logger
from data_foundry.schemas import RawListingEntry, WorkDetail

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class WorkDiscovered:
    work_id: str
    raw: RawListingEntry


@dataclass(frozen=True, slots=True)
class PdfDownloaded:
    work_id: str
    pdf_path: Path
    detail: WorkDetail


@dataclass(frozen=True, slots=True)
class Hashed:
    work_id: str
    sha256: str


@dataclass(frozen=True, slots=True)
class CoverExtracted:
    work_id: str
    cover_path: Path
    cover_hash: str


@dataclass(frozen=True, slots=True)
class Described:
    work_id: str
    description: str | None


@dataclass(frozen=True, slots=True)
class TitleTranslated:
    work_id: str
    lang: str
    text: str | None


@dataclass(frozen=True, slots=True)
class DescriptionTranslated:
    work_id: str
    lang: str
    text: str | None


@dataclass(frozen=True, slots=True)
class WorkFailed:
    work_id: str
    stage: str
    error: str


Event = (
    WorkDiscovered
    | PdfDownloaded
    | Hashed
    | CoverExtracted
    | Described
    | TitleTranslated
    | DescriptionTranslated
    | WorkFailed
)

Handler = Callable[[Any], Awaitable[None]]


class EventBus:
    """`subscribe(event_type, handler)` + `publish(event)`.

    Handlers run as background tasks — `publish` never blocks on them, since they exist for
    observability/counting, not for controlling how data flows between stages.
    """

    def __init__(self) -> None:
        self._handlers: dict[type, list[Handler]] = defaultdict(list)
        self._tasks: set[asyncio.Task[None]] = set()

    def subscribe(self, event_type: type, handler: Handler) -> None:
        self._handlers[event_type].append(handler)

    def publish(self, event: Event) -> None:
        for handler in self._handlers[type(event)]:
            task = asyncio.create_task(handler(event))
            self._tasks.add(task)
            task.add_done_callback(functools.partial(self._on_task_done, event=event, handler=handler))

    def _on_task_done(self, task: asyncio.Task[None], *, event: Event, handler: Handler) -> None:
        self._tasks.discard(task)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            handler_name = getattr(handler, "__name__", repr(handler))
            logger.error(
                "event handler failed event=%s handler=%s error=%s",
                type(event).__name__,
                handler_name,
                exc,
                exc_info=exc,
            )

    async def drain(self) -> None:
        """Wait for every handler task scheduled so far to finish.

        Failures are already logged by `_on_task_done` as each task completes — `drain` itself
        must not re-raise them, since handlers are fire-and-forget observability/silver-building,
        not a control-flow gate the rest of the pipeline should crash on.
        """
        pending = list(self._tasks)
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
