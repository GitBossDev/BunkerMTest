from __future__ import annotations

from types import SimpleNamespace

import pytest

import core.database as database_module


class _DummyBeginContext:
    def __init__(self):
        self.calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def run_sync(self, fn):
        self.calls += 1
        fn(None)


class _DummyEngine:
    def __init__(self):
        self.context = _DummyBeginContext()

    def begin(self):
        return self.context


@pytest.mark.asyncio
async def test_init_db_rejects_sqlite_runtime(monkeypatch):
    monkeypatch.setattr(
        database_module,
        "settings",
        SimpleNamespace(
            resolved_control_plane_database_url="sqlite+aiosqlite:////tmp/test.db",
            resolved_history_database_url="postgresql://bhm:secret@localhost:5432/bhm_history",
            resolved_reporting_database_url="postgresql://bhm:secret@localhost:5432/bhm_reporting",
        ),
    )

    with pytest.raises(ValueError):
        await database_module.init_db()


@pytest.mark.asyncio
async def test_init_db_uses_alembic_for_non_sqlite(monkeypatch):
    migration_calls: list[str] = []
    history_migration_calls: list[tuple[str, ...]] = []

    async def _fake_upgrade(database_url: str) -> None:
        migration_calls.append(database_url)

    async def _fake_history_upgrade(database_urls: list[str]) -> None:
        history_migration_calls.append(tuple(database_urls))

    monkeypatch.setattr(
        database_module,
        "settings",
        SimpleNamespace(
            resolved_control_plane_database_url="postgresql://bhm:secret@localhost:5432/bhm_control",
            resolved_history_database_url="postgresql://bhm:secret@localhost:5432/bhm_history",
            resolved_reporting_database_url="postgresql://bhm:secret@localhost:5432/bhm_reporting",
        ),
    )
    monkeypatch.setattr(
        "core.database_migrations.upgrade_control_plane_database",
        _fake_upgrade,
    )
    monkeypatch.setattr(
        "core.history_reporting_database_migrations.upgrade_history_reporting_databases",
        _fake_history_upgrade,
    )

    await database_module.init_db()

    assert migration_calls == ["postgresql://bhm:secret@localhost:5432/bhm_control"]
    assert history_migration_calls == [
        (
            "postgresql://bhm:secret@localhost:5432/bhm_history",
            "postgresql://bhm:secret@localhost:5432/bhm_reporting",
        )
    ]