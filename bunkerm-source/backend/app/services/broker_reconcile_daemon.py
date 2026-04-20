"""Daemon transicional para reconciliar scopes broker-facing fuera del proceso web."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging

from core.database import init_db
from services import broker_reconcile_runner

logger = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the transitional broker reconcile daemon")
    parser.add_argument(
        "--scope",
        action="append",
        dest="scopes",
        default=[],
        help="Control-plane scope to reconcile. Repeatable. Defaults to 'all'.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=5.0,
        help="Seconds between reconciliation polling cycles.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single reconciliation cycle and exit.",
    )
    return parser


async def run_daemon(scopes: list[str], interval_seconds: float, once: bool = False) -> int:
    await init_db()

    while True:
        try:
            results = await broker_reconcile_runner.reconcile_requested_scopes(scopes)
            if results:
                logger.info("Broker reconcile cycle applied: %s", json.dumps(results, ensure_ascii=True))
        except Exception:
            logger.exception("Broker reconcile cycle failed")
            if once:
                return 1

        if once:
            return 0

        await asyncio.sleep(interval_seconds)


async def _async_main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    scopes = args.scopes or ["all"]
    return await run_daemon(scopes, args.interval, once=args.once)


def main() -> int:
    return asyncio.run(_async_main())


if __name__ == "__main__":
    raise SystemExit(main())