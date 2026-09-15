"""CLI entrypoint: `python -m data_foundry run [--only STAGE] [--limit N]`."""

from __future__ import annotations

import argparse
import asyncio

from data_foundry.config import settings
from data_foundry.logging_setup import get_logger
from data_foundry.pipeline import ONLY_STAGES
from data_foundry.pipeline import run as run_pipeline

logger = get_logger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="data_foundry")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="run the pipeline")
    run_parser.add_argument(
        "--only", choices=ONLY_STAGES, default=None, help="run a single stage over already-available data"
    )
    run_parser.add_argument(
        "--limit", type=int, default=None, help="cap the number of works discovered (0 = discovery-only dry run)"
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)

    if args.command == "run":
        ctx = asyncio.run(run_pipeline(settings, limit=args.limit, only=args.only))
        logger.info("run finished status=%s manifest=%s", ctx.manifest.status, ctx.manifest_path)


if __name__ == "__main__":
    main()
