from __future__ import annotations

import argparse
import logging
import time

from services.alert_delivery_worker import process_pending_alert_delivery_events

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="Consume alert delivery outbox events")
    parser.add_argument("--interval", type=float, default=5.0, help="Polling interval in seconds")
    parser.add_argument("--limit", type=int, default=20, help="Maximum events per loop")
    parser.add_argument("--once", action="store_true", help="Process once and exit")
    args = parser.parse_args()

    while True:
        result = process_pending_alert_delivery_events(limit=args.limit)
        if result["processed"] > 0:
            logger.info(
                "Alert delivery loop processed=%s delivered=%s failed=%s",
                result["processed"],
                result["delivered"],
                result["failed"],
            )
        if args.once:
            return 0
        time.sleep(max(args.interval, 1.0))


if __name__ == "__main__":
    raise SystemExit(main())