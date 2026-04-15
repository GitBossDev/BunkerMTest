from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _app_root() -> Path:
    return _repo_root() / "bunkerm-source" / "backend" / "app"


def _load_env() -> None:
    env_path = _repo_root() / ".env.dev"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--truncate-target", action="store_true")
    parser.add_argument("--source-url", help="Override legacy SQLite source URL.")
    parser.add_argument("--history-target-url", help="Override history target URL.")
    parser.add_argument("--reporting-target-url", help="Override reporting target URL.")
    return parser.parse_args()


def main() -> None:
    _load_env()
    sys.path.insert(0, str(_app_root()))

    args = _parse_args()
    migration_module = importlib.import_module("core.history_reporting_migrations")
    resolve_plan = migration_module.resolve_history_reporting_plan
    migrate_sync = migration_module.migrate_history_reporting_sqlite_sync

    plan = resolve_plan(
        source_url=args.source_url,
        history_target_url=args.history_target_url,
        reporting_target_url=args.reporting_target_url,
    )
    result = migrate_sync(
        source_url=plan.source_url,
        history_target_url=plan.history_target_url,
        reporting_target_url=plan.reporting_target_url,
        truncate_target=args.truncate_target,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()