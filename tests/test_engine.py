"""Engine tests with FAKE stages only — no network, no LLM, no real stage modules.

Async test bodies run via `asyncio.run(...)` from plain sync `test_*` functions, so no pytest
plugin is needed.
"""

from __future__ import annotations

import asyncio
import time

from data_foundry.orchestrator.engine import STOP, run_worker_pool, with_retry


def test_concurrency_never_exceeds_semaphore_limit():
    async def scenario() -> int:
        current = 0
        max_seen = 0
        lock = asyncio.Lock()

        async def handler(item: int) -> int:
            nonlocal current, max_seen
            async with lock:
                current += 1
                max_seen = max(max_seen, current)
            await asyncio.sleep(0.02)
            async with lock:
                current -= 1
            return item

        queue: asyncio.Queue = asyncio.Queue()
        for i in range(10):
            await queue.put(i)
        await queue.put(STOP)

        stats = await run_worker_pool(input_queue=queue, handler=handler, concurrency=3)
        assert stats.succeeded == 10
        assert stats.failed == 0
        return max_seen

    max_seen = asyncio.run(scenario())
    assert max_seen <= 3
    assert max_seen > 1  # actually exercised concurrency, not accidentally serial


def test_retry_then_succeeds():
    async def scenario() -> None:
        attempts = 0

        async def flaky(_: str) -> str:
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise TimeoutError("transient")
            return "ok"

        results: list[tuple[str, str]] = []

        async def record(item: str, result: str) -> None:
            results.append((item, result))

        queue: asyncio.Queue = asyncio.Queue()
        await queue.put("work-1")
        await queue.put(STOP)

        stats = await run_worker_pool(
            input_queue=queue, handler=flaky, concurrency=1, max_retries=5, base_delay=0.001, on_success=record
        )

        assert attempts == 3
        assert stats.succeeded == 1
        assert stats.failed == 0
        assert results == [("work-1", "ok")]

    asyncio.run(scenario())


def test_always_fails_becomes_isolated_failure_without_crashing():
    async def scenario() -> None:
        async def always_fails(_: str) -> str:
            raise TimeoutError("nope")

        failures: list[tuple[str, str]] = []

        async def record_failure(item: str, exc: BaseException) -> None:
            failures.append((item, str(exc)))

        queue: asyncio.Queue = asyncio.Queue()
        await queue.put("bad")
        await queue.put(STOP)

        stats = await run_worker_pool(
            input_queue=queue,
            handler=always_fails,
            concurrency=1,
            max_retries=2,
            base_delay=0.001,
            on_failure=record_failure,
        )

        assert stats.succeeded == 0
        assert stats.failed == 1
        assert failures == [("bad", "nope")]

    asyncio.run(scenario())


def test_per_item_isolation_one_bad_work_does_not_stop_the_others():
    async def scenario() -> None:
        async def handler(item: str) -> str:
            if item == "bad":
                raise ValueError("boom")
            return item.upper()

        successes: list[str] = []
        failures: list[str] = []

        async def on_success(_: str, result: str) -> None:
            successes.append(result)

        async def on_failure(item: str, _: BaseException) -> None:
            failures.append(item)

        queue: asyncio.Queue = asyncio.Queue()
        for item in ("a", "bad", "b", "c"):
            await queue.put(item)
        await queue.put(STOP)

        stats = await run_worker_pool(
            input_queue=queue,
            handler=handler,
            concurrency=2,
            on_success=on_success,
            on_failure=on_failure,
        )

        assert stats.succeeded == 3
        assert stats.failed == 1
        assert set(successes) == {"A", "B", "C"}
        assert failures == ["bad"]

    asyncio.run(scenario())


def test_backpressure_blocks_fast_producer_behind_a_slow_consumer():
    async def scenario() -> float:
        queue: asyncio.Queue = asyncio.Queue(maxsize=2)
        processed: list[int] = []

        async def slow_handler(item: int) -> int:
            await asyncio.sleep(0.05)
            processed.append(item)
            return item

        worker_task = asyncio.create_task(
            run_worker_pool(input_queue=queue, handler=slow_handler, concurrency=1)
        )

        start = time.monotonic()
        for i in range(6):
            await queue.put(i)
            assert queue.qsize() <= queue.maxsize
        await queue.put(STOP)
        await worker_task
        elapsed = time.monotonic() - start

        assert processed == list(range(6))
        return elapsed

    elapsed = asyncio.run(scenario())
    # 6 items x 0.05s at concurrency=1 -> ~0.3s. A producer that wasn't blocked by the bounded
    # queue (i.e. buffering unboundedly instead of honoring backpressure) would return near-instantly.
    assert elapsed >= 0.25


def test_with_retry_raises_immediately_on_non_retryable_error():
    async def scenario() -> None:
        calls = 0

        async def fn() -> None:
            nonlocal calls
            calls += 1
            raise ValueError("not transient")

        try:
            await with_retry(fn, max_retries=5, base_delay=0.001)
        except ValueError:
            pass
        else:
            raise AssertionError("expected ValueError to propagate")

        assert calls == 1  # no retries attempted for a non-retryable error

    asyncio.run(scenario())


def test_with_retry_raises_after_exhausting_retries():
    async def scenario() -> None:
        calls = 0

        async def fn() -> None:
            nonlocal calls
            calls += 1
            raise TimeoutError("always transient")

        try:
            await with_retry(fn, max_retries=2, base_delay=0.001)
        except TimeoutError:
            pass
        else:
            raise AssertionError("expected TimeoutError to propagate after exhausting retries")

        assert calls == 3  # 1 initial attempt + 2 retries

    asyncio.run(scenario())
