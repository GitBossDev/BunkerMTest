from __future__ import annotations

import argparse
import logging
import pathlib
import time

from sqlalchemy.exc import ProgrammingError, OperationalError

from services.alert_delivery_worker import process_pending_alert_delivery_events

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# Archivo de heartbeat leido por las probes de Kubernetes para verificar actividad real del daemon
_HEARTBEAT_FILE = pathlib.Path("/tmp/alert_delivery.alive")


def _write_heartbeat() -> None:
    """Escribe el timestamp actual al archivo de heartbeat de forma atomica."""
    try:
        _HEARTBEAT_FILE.write_text(str(time.time()))
    except OSError:
        logger.warning("No se pudo escribir el heartbeat en %s", _HEARTBEAT_FILE)


def main() -> int:
    parser = argparse.ArgumentParser(description="Consume alert delivery outbox events")
    parser.add_argument("--interval", type=float, default=5.0, help="Polling interval in seconds")
    parser.add_argument("--limit", type=int, default=20, help="Maximum events per loop")
    parser.add_argument("--once", action="store_true", help="Process once and exit")
    args = parser.parse_args()

    # Escribe el heartbeat inicial para que las probes no fallen durante el arranque
    _write_heartbeat()

    # Esperar a que bhm-api termine las migraciones Alembic antes de la primera query.
    # En un despliegue limpio ambos pods arrancan simultaneamente; el daemon puede llegar
    # aqui antes de que las tablas existan. Reintentamos hasta 5 minutos.
    _STARTUP_TIMEOUT = 300.0
    _STARTUP_RETRY = 5.0
    _startup_deadline = time.monotonic() + _STARTUP_TIMEOUT
    while True:
        try:
            process_pending_alert_delivery_events(limit=1)
            break
        except (ProgrammingError, OperationalError) as exc:
            if time.monotonic() >= _startup_deadline:
                logger.error(
                    "La base de datos no esta lista tras %.0f s de espera: %s", _STARTUP_TIMEOUT, exc
                )
                raise
            logger.warning(
                "Base de datos no lista aun (%s). Reintentando en %.0f s...",
                type(exc).__name__,
                _STARTUP_RETRY,
            )
            _write_heartbeat()
            time.sleep(_STARTUP_RETRY)

    while True:
        result = process_pending_alert_delivery_events(limit=args.limit)
        if result["processed"] > 0:
            logger.info(
                "Alert delivery loop processed=%s delivered=%s failed=%s",
                result["processed"],
                result["delivered"],
                result["failed"],
            )
        # Actualiza el heartbeat tras cada ciclo para reflejar actividad real
        _write_heartbeat()
        if args.once:
            return 0
        time.sleep(max(args.interval, 1.0))


if __name__ == "__main__":
    raise SystemExit(main())