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
async def test_init_db_uses_create_all_for_sqlite(monkeypatch):
    dummy_engine = _DummyEngine()
    create_all_calls: list[str] = []

    monkeypatch.setattr(database_module, "settings", SimpleNamespace(resolved_control_plane_database_url="sqlite+aiosqlite:////tmp/test.db"))
    monkeypatch.setattr(database_module, "engine", dummy_engine)
    monkeypatch.setattr(database_module.Base.metadata, "create_all", lambda *_args, **_kwargs: create_all_calls.append("create_all"))

    await database_module.init_db()

    assert create_all_calls == ["create_all"]
    assert dummy_engine.context.calls == 1


@pytest.mark.asyncio
async def test_init_db_uses_alembic_for_non_sqlite(monkeypatch):
    migration_calls: list[str] = []

    async def _fake_upgrade(database_url: str) -> None:
        migration_calls.append(database_url)

    monkeypatch.setattr(database_module, "settings", SimpleNamespace(resolved_control_plane_database_url="postgresql://bhm:secret@localhost:5432/bhm"))
    monkeypatch.setattr(
        "core.database_migrations.upgrade_control_plane_database",
        _fake_upgrade,
    )

    await database_module.init_db()

    assert migration_calls == ["postgresql://bhm:secret@localhost:5432/bhm"]