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
        help="Override target control-plane database URL. If omitted, uses resolved_control_plane_database_url from settings.",
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
    upgrade_control_plane_database_sync = importlib.import_module(
        "core.database_migrations"
    ).upgrade_control_plane_database_sync

    settings = Settings()
    database_url = get_host_accessible_database_url(args.database_url or settings.resolved_control_plane_database_url)
    upgrade_control_plane_database_sync(database_url, revision=args.revision)
    print(f"Control-plane schema upgraded to {args.revision} on {database_url}")


if __name__ == "__main__":
    main()