"""Daemon transicional para reconciliar scopes broker-facing fuera del proceso web."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import pathlib
import time

from core.database import init_db
from services import broker_reconcile_runner

logger = logging.getLogger(__name__)

# Archivo de heartbeat leido por las probes de Kubernetes para verificar actividad real del daemon
_HEARTBEAT_FILE = pathlib.Path("/tmp/reconciler.alive")


def _write_heartbeat() -> None:
    """Escribe el timestamp actual al archivo de heartbeat de forma atomica."""
    try:
        _HEARTBEAT_FILE.write_text(str(time.time()))
    except OSError:
        logger.warning("No se pudo escribir el heartbeat en %s", _HEARTBEAT_FILE)


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

    # Escribe el heartbeat inicial para que las probes no fallen durante el arranque
    _write_heartbeat()

    while True:
        try:
            results = await broker_reconcile_runner.reconcile_requested_scopes(scopes)
            if results:
                logger.info("Broker reconcile cycle applied: %s", json.dumps(results, ensure_ascii=True))
        except Exception:
            logger.exception("Broker reconcile cycle failed")
            if once:
                return 1

        # Actualiza el heartbeat tras cada ciclo (exitoso o fallido) para reflejar actividad real
        _write_heartbeat()

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