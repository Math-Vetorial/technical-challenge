"""EventBus: fan-out dispatch, and that a handler's exception is surfaced rather than lost.

Async test bodies run via `asyncio.run(...)` from plain sync `test_*` functions, matching
`test_engine.py` — no pytest-asyncio plugin needed.
"""

from __future__ import annotations

import asyncio
import logging

from data_foundry.orchestrator.events import EventBus, Hashed


def test_publish_dispatches_to_all_subscribed_handlers():
    bus = EventBus()
    seen: list[str] = []

    async def handler_a(event: Hashed) -> None:
        seen.append(f"a:{event.work_id}")

    async def handler_b(event: Hashed) -> None:
        seen.append(f"b:{event.work_id}")

    bus.subscribe(Hashed, handler_a)
    bus.subscribe(Hashed, handler_b)

    async def scenario() -> None:
        bus.publish(Hashed(work_id="fixture-001", sha256="deadbeef"))
        await bus.drain()

    asyncio.run(scenario())

    assert sorted(seen) == ["a:fixture-001", "b:fixture-001"]


def test_handler_exception_is_logged_and_does_not_crash_drain(caplog):
    bus = EventBus()

    async def bad_handler(event: Hashed) -> None:
        raise ValueError(f"boom for {event.work_id}")

    bus.subscribe(Hashed, bad_handler)

    async def scenario() -> None:
        bus.publish(Hashed(work_id="fixture-001", sha256="deadbeef"))
        await bus.drain()  # must not raise, even though the handler blew up

    with caplog.at_level(logging.ERROR, logger="data_foundry.orchestrator.events"):
        asyncio.run(scenario())

    matching = [r for r in caplog.records if "event handler failed" in r.message]
    assert len(matching) == 1
    record = matching[0]
    assert "Hashed" in record.message
    assert "bad_handler" in record.message
    assert record.exc_info is not None
    assert isinstance(record.exc_info[1], ValueError)


def test_one_failing_handler_does_not_stop_sibling_handlers(caplog):
    """A raising handler must not prevent other handlers subscribed to the same event from
    running — the bus fans out independently per handler."""
    bus = EventBus()
    seen: list[str] = []

    async def bad_handler(event: Hashed) -> None:
        raise RuntimeError("boom")

    async def good_handler(event: Hashed) -> None:
        seen.append(event.work_id)

    bus.subscribe(Hashed, bad_handler)
    bus.subscribe(Hashed, good_handler)

    async def scenario() -> None:
        bus.publish(Hashed(work_id="fixture-001", sha256="deadbeef"))
        await bus.drain()

    with caplog.at_level(logging.ERROR, logger="data_foundry.orchestrator.events"):
        asyncio.run(scenario())

    assert seen == ["fixture-001"]
    assert any("event handler failed" in r.message for r in caplog.records)
