from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy import inspect

from core.database_migrations import upgrade_control_plane_database_sync
from core.sync_database import create_sync_engine_for_url
from models.orm import BrokerDesiredState, BrokerDesiredStateAudit
from core.database import Base


def test_control_plane_alembic_upgrade_creates_expected_tables(tmp_path):
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'control-plane-migrations.db').as_posix()}"

    upgrade_control_plane_database_sync(database_url)

    engine = create_sync_engine_for_url(database_url)
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    assert "alembic_version" in table_names
    assert "broker_desired_state" in table_names
    assert "broker_desired_state_audit" in table_names

    audit_indexes = {index["name"] for index in inspector.get_indexes("broker_desired_state_audit")}
    assert "ix_broker_desired_state_audit_scope" in audit_indexes
    assert "ix_broker_desired_state_audit_version" in audit_indexes
    assert "ix_broker_desired_state_audit_recorded_at" in audit_indexes


def test_control_plane_alembic_upgrade_stamps_existing_bootstrapped_schema(tmp_path):
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'control-plane-bootstrap.db').as_posix()}"
    engine = create_sync_engine_for_url(database_url)

    Base.metadata.create_all(bind=engine, tables=[BrokerDesiredState.__table__, BrokerDesiredStateAudit.__table__])

    upgrade_control_plane_database_sync(database_url)

    with engine.begin() as connection:
        stamped_revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()

    assert stamped_revision == "001_control_plane_initial"