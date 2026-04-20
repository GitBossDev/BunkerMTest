"""Healthchecks for the water plant simulator runtime."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any


def _status_file_path() -> Path:
    return Path(os.getenv("SIMULATOR_STATUS_FILE", "/app/status/simulator-status.json"))


def _heartbeat_file_path() -> Path:
    return Path(os.getenv("SIMULATOR_HEARTBEAT_FILE", "/app/status/heartbeat.txt"))


def load_status() -> dict[str, Any]:
    path = _status_file_path()
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def heartbeat_is_fresh(max_age_seconds: float) -> bool:
    path = _heartbeat_file_path()
    if not path.exists():
        return False
    last_heartbeat = float(path.read_text(encoding="utf-8").strip())
    return (time.time() - last_heartbeat) <= max_age_seconds


def readiness(max_heartbeat_age_seconds: float) -> bool:
    status = load_status()
    return bool(
        status.get("initialized")
        and status.get("running")
        and status.get("mqttConnected")
        and heartbeat_is_fresh(max_heartbeat_age_seconds)
    )


def liveness(max_heartbeat_age_seconds: float) -> bool:
    status = load_status()
    return bool(status.get("running") and heartbeat_is_fresh(max_heartbeat_age_seconds))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Water plant simulator healthcheck")
    parser.add_argument("--mode", choices=("readiness", "liveness"), required=True)
    parser.add_argument("--max-heartbeat-age", type=float, default=30.0)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    ok = readiness(args.max_heartbeat_age) if args.mode == "readiness" else liveness(args.max_heartbeat_age)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())