"""The scalability core: bounded queues, semaphores, retry+backoff, per-item isolation.

Plain `asyncio` only — no external orchestrator dependency. That's the point: a lightweight,
self-contained event-driven engine (see the README for the trade-off vs. Airflow/Temporal/Prefect).

- **Bounded queues = backpressure.** `run_worker_pool` only removes an item from its input queue
  once a concurrency slot is free (the semaphore is acquired *before* `queue.get()`). So when the
  queue's `maxsize` is reached, a fast upstream producer blocks on `put()` instead of buffering an
  unbounded backlog in memory while a slow stage (the LLM) catches up.
- **Semaphores = rate limiting.** The `concurrency` parameter bounds how many `handler` calls run
  at once — one budget per resource (network, LLM), never exceeded regardless of queue size.
- **Retry with backoff + jitter** (`with_retry`) retries only transient errors, with exponential
  backoff and full jitter (randomized delay, not a fixed one) to avoid a thundering herd of
  simultaneous retries. Non-transient errors and retry-exhaustion both propagate immediately.
- **Per-item isolation:** a failure that survives retries fails only that one item — `on_failure`
  is called and the pool keeps processing everything else, so one bad work never stops the run.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from data_foundry.logging_setup import get_logger

logger = get_logger(__name__)


class TransientError(Exception):
    """A stage's own signal that a failure is worth retrying (timeout, connection reset, a bad
    or short response, ...). Stages translate whatever their HTTP/LLM client raises into this
    at the boundary (e.g. `stages.download`, `stages.scrape`), so the engine's retry logic never
    needs to know which library — or which of its own exception types — is behind the failure.
    """


# TransientError is the stage-level contract above; OSError stays retryable too since it covers
# local I/O hiccups (disk, filesystem) that stages don't (and shouldn't need to) translate.
TRANSIENT_ERRORS: tuple[type[BaseException], ...] = (TransientError, OSError)

STOP = object()
"""Sentinel enqueued to signal a worker pool that no more items are coming."""


async def with_retry[R](
    fn: Callable[[], Awaitable[R]],
    *,
    max_retries: int,
    base_delay: float,
    retryable: tuple[type[BaseException], ...] = TRANSIENT_ERRORS,
) -> R:
    """Call `fn()`, retrying `retryable` errors with exponential backoff + full jitter.

    Non-retryable errors propagate on the first attempt. Once `max_retries` is exhausted the
    final error propagates too, so the caller can isolate the failure per item.
    """
    attempt = 0
    while True:
        try:
            return await fn()
        except retryable as exc:
            attempt += 1
            if attempt > max_retries:
                raise
            delay = random.uniform(0, base_delay * (2 ** (attempt - 1)))
            logger.warning("retrying attempt=%s/%s delay=%.3fs error=%s", attempt, max_retries, delay, exc)
            await asyncio.sleep(delay)


@dataclass
class StageStats:
    succeeded: int = 0
    failed: int = 0


@dataclass
class _Handlers[T, R]:
    on_success: Callable[[T, R], Awaitable[None]] | None = None
    on_failure: Callable[[T, BaseException], Awaitable[None]] | None = None


async def run_worker_pool[T, R](
    *,
    input_queue: asyncio.Queue,
    handler: Callable[[T], Awaitable[R]],
    concurrency: int,
    max_retries: int = 0,
    base_delay: float = 0.5,
    retryable: tuple[type[BaseException], ...] = TRANSIENT_ERRORS,
    on_success: Callable[[T, R], Awaitable[None]] | None = None,
    on_failure: Callable[[T, BaseException], Awaitable[None]] | None = None,
    sentinel: object = STOP,
) -> StageStats:
    """Consume `input_queue` until `sentinel`, running at most `concurrency` handlers at once.

    Each item is retried (via `with_retry`) and isolated: a failure that survives retries is
    reported through `on_failure` and counted, without affecting any other item in flight.
    """
    semaphore = asyncio.Semaphore(concurrency)
    stats = StageStats()
    handlers = _Handlers(on_success=on_success, on_failure=on_failure)
    in_flight: set[asyncio.Task[None]] = set()

    async def process(item: T) -> None:
        try:
            try:
                result = await with_retry(
                    lambda: handler(item),
                    max_retries=max_retries,
                    base_delay=base_delay,
                    retryable=retryable,
                )
            except Exception as exc:  # noqa: BLE001 - isolate any failure, not just transient ones
                stats.failed += 1
                if handlers.on_failure:
                    await handlers.on_failure(item, exc)
                return
            stats.succeeded += 1
            if handlers.on_success:
                await handlers.on_success(item, result)
        finally:
            semaphore.release()

    while True:
        await semaphore.acquire()
        item = await input_queue.get()
        input_queue.task_done()
        if item is sentinel:
            semaphore.release()
            break
        task = asyncio.create_task(process(item))
        in_flight.add(task)
        task.add_done_callback(in_flight.discard)

    if in_flight:
        await asyncio.gather(*in_flight)
    return stats


__all__ = ["STOP", "TRANSIENT_ERRORS", "StageStats", "TransientError", "run_worker_pool", "with_retry"]
