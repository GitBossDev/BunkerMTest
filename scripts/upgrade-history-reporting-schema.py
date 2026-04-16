from __future__ import annotations

import argparse
import importlib
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
    parser.add_argument(
        "--database-url",
        action="append",
        dest="database_urls",
        help="Override one or more target history/reporting database URLs. If omitted, uses resolved_history_database_url and resolved_reporting_database_url.",
    )
    parser.add_argument(
        "--revision",
        default="head",
        help="Alembic revision target. Defaults to head.",
    )
    return parser.parse_args()


def main() -> None:
    _load_env()
    sys.path.insert(0, str(_app_root()))

    args = _parse_args()
    Settings = importlib.import_module("core.config").Settings
    get_host_accessible_database_url = importlib.import_module("core.database_url").get_host_accessible_database_url
    upgrade_history_reporting_database_sync = importlib.import_module(
        "core.history_reporting_database_migrations"
    ).upgrade_history_reporting_database_sync

    settings = Settings()
    raw_database_urls = args.database_urls or [
        settings.resolved_history_database_url,
        settings.resolved_reporting_database_url,
    ]

    upgraded: list[str] = []
    seen: set[str] = set()
    for raw_database_url in raw_database_urls:
        database_url = get_host_accessible_database_url(raw_database_url)
        if database_url in seen:
            continue
        seen.add(database_url)
        upgrade_history_reporting_database_sync(database_url, revision=args.revision)
        upgraded.append(database_url)

    print(f"History/reporting schema upgraded to {args.revision} on {', '.join(upgraded)}")


if __name__ == "__main__":
    main()