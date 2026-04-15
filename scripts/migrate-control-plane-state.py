#!/usr/bin/env python3
"""Migra el estado durable del control-plane desde SQLite al datastore configurado para el control-plane."""
from __future__ import annotations

import argparse
import asyncio
import importlib
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _app_root() -> Path:
    return _repo_root() / "bunkerm-source" / "backend" / "app"


def _load_env() -> None:
    env_file = _repo_root() / ".env.dev"
    if not env_file.exists():
        return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key, value)


def _resolve_sqlite_path(database_url: str) -> str:
    prefixes = ("sqlite+aiosqlite:///", "sqlite:///")
    for prefix in prefixes:
        if database_url.startswith(prefix):
            return database_url[len(prefix):]
    raise ValueError(f"SQLite source URL expected, got: {database_url}")


def _parse_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def _read_sqlite_rows(database_url: str) -> list[dict[str, object]]:
    db_path = _resolve_sqlite_path(database_url)
    if not os.path.exists(db_path):
        return []
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        if "broker_desired_state" not in tables:
            return []
        rows = conn.execute("SELECT * FROM broker_desired_state").fetchall()
    return [dict(row) for row in rows]


async def _migrate() -> int:
    _load_env()
    sys.path.insert(0, str(_app_root()))

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    Settings = importlib.import_module("core.config").Settings
    database_url_module = importlib.import_module("core.database_url")
    ensure_sqlite_url = database_url_module.ensure_sqlite_url
    get_async_engine_connect_args = database_url_module.get_async_engine_connect_args
    BrokerDesiredState = importlib.import_module("models.orm").BrokerDesiredState

    settings = Settings()
    source_url = settings.database_url
    target_url = settings.resolved_control_plane_database_url

    ensure_sqlite_url(source_url, "DATABASE_URL")
    rows = _read_sqlite_rows(source_url)
    if not rows:
        print("No broker_desired_state rows found in the SQLite source database.")
        return 0

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--dry-run", action="store_true")
    args, _ = parser.parse_known_args()

    if args.dry_run:
        print(f"Dry-run: {len(rows)} broker_desired_state rows ready to migrate.")
        print(f"Source: {source_url}")
        print(f"Target: {target_url}")
        return len(rows)

    engine = create_async_engine(
        target_url,
        echo=False,
        pool_pre_ping=True,
        connect_args=get_async_engine_connect_args(target_url),
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with engine.begin() as conn:
            await conn.run_sync(BrokerDesiredState.__table__.create, checkfirst=True)

        async with session_factory() as session:
            for row in rows:
                await session.merge(
                    BrokerDesiredState(
                        scope=row["scope"],
                        version=row["version"],
                        desired_payload_json=row["desired_payload_json"],
                        applied_payload_json=row.get("applied_payload_json"),
                        observed_payload_json=row.get("observed_payload_json"),
                        reconcile_status=row["reconcile_status"],
                        drift_detected=bool(row["drift_detected"]),
                        last_error=row.get("last_error"),
                        desired_updated_at=_parse_dt(row.get("desired_updated_at")) or datetime.utcnow(),
                        reconciled_at=_parse_dt(row.get("reconciled_at")),
                        applied_at=_parse_dt(row.get("applied_at")),
                    )
                )
            await session.commit()
    finally:
        await engine.dispose()

    print(f"Migrated {len(rows)} broker_desired_state rows into the control-plane datastore.")
    return len(rows)


def main() -> None:
    migrated = asyncio.run(_migrate())
    print(f"Done. Rows migrated: {migrated}")


if __name__ == "__main__":
    main()