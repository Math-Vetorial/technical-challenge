"""Minimal entrypoint: builds a run, logs, writes a manifest. No stages wired yet."""

from __future__ import annotations

from data_foundry.config import settings
from data_foundry.logging_setup import get_logger
from data_foundry.run import RunContext

logger = get_logger(__name__)


def main() -> None:
    logger.info("run started")
    ctx = RunContext.create(settings)
    logger.info("run created run_id=%s dir=%s", ctx.run_id, ctx.run_dir)

    # TODO(step-3): wire the event-driven orchestrator here (scrape -> download ->
    # hash/describe/cover (fan-out) -> assemble (barrier)). Stages are not wired yet.
    logger.info("stages not wired yet; this is a foundations-only run")

    ctx.finish("success")
    logger.info("run finished status=success manifest=%s", ctx.manifest_path)


if __name__ == "__main__":
    main()
