"""Typed events describing a work's progress, plus a minimal async pub/sub bus.

The bus is for fan-out notification (logging, count bookkeeping) — the actual backpressure
boundary between scrape and download is a bounded `asyncio.Queue` (see `pipeline.py`), per the
spec's "events on an async bus and/or bounded queues" — we use both, for what each is good at.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from data_foundry.schemas import RawListingEntry


@dataclass(frozen=True, slots=True)
class WorkDiscovered:
    work_id: str
    raw: RawListingEntry


@dataclass(frozen=True, slots=True)
class PdfDownloaded:
    work_id: str
    pdf_path: Path


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
            task.add_done_callback(self._tasks.discard)

    async def drain(self) -> None:
        """Wait for every handler task scheduled so far to finish."""
        pending = list(self._tasks)
        if pending:
            await asyncio.gather(*pending)
