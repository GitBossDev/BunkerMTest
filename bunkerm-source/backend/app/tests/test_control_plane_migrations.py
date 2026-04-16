from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy import inspect

from core.database_migrations import upgrade_control_plane_database_sync
from core.sync_database import create_sync_engine_for_url
from models.orm import (
    AlertConfigEntry,
    AlertDeliveryAttempt,
    AlertDeliveryChannel,
    AlertDeliveryEvent,
    BrokerDesiredState,
    BrokerDesiredStateAudit,
    BrokerReconcileSecret,
)
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
    assert "broker_reconcile_secret" in table_names
    assert "alert_config" in table_names
    assert "alert_delivery_channel" in table_names
    assert "alert_delivery_event" in table_names
    assert "alert_delivery_attempt" in table_names

    audit_indexes = {index["name"] for index in inspector.get_indexes("broker_desired_state_audit")}
    assert "ix_broker_desired_state_audit_scope" in audit_indexes
    assert "ix_broker_desired_state_audit_version" in audit_indexes
    assert "ix_broker_desired_state_audit_recorded_at" in audit_indexes

    event_indexes = {index["name"] for index in inspector.get_indexes("alert_delivery_event")}
    assert "ix_alert_delivery_event_alert_id" in event_indexes
    assert "ix_alert_delivery_event_dedupe_key" in event_indexes
    assert "ix_alert_delivery_event_delivery_state" in event_indexes
    assert "ix_alert_delivery_event_next_attempt_at" in event_indexes

    attempt_indexes = {index["name"] for index in inspector.get_indexes("alert_delivery_attempt")}
    assert "ix_alert_delivery_attempt_event_id" in attempt_indexes
    assert "ix_alert_delivery_attempt_channel_id" in attempt_indexes
    assert "ix_alert_delivery_attempt_attempt_state" in attempt_indexes
    assert "ix_alert_delivery_attempt_scheduled_at" in attempt_indexes

    secret_indexes = {index["name"] for index in inspector.get_indexes("broker_reconcile_secret")}
    assert "ix_broker_reconcile_secret_scope" in secret_indexes
    assert "ix_broker_reconcile_secret_version" in secret_indexes
    assert "ix_broker_reconcile_secret_expires_at" in secret_indexes


def test_control_plane_alembic_upgrade_stamps_existing_bootstrapped_schema(tmp_path):
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'control-plane-bootstrap.db').as_posix()}"
    engine = create_sync_engine_for_url(database_url)

    Base.metadata.create_all(bind=engine, tables=[BrokerDesiredState.__table__, BrokerDesiredStateAudit.__table__])

    upgrade_control_plane_database_sync(database_url)

    with engine.begin() as connection:
        stamped_revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()

    inspector = inspect(engine)
    assert "alert_config" in set(inspector.get_table_names())
    assert "broker_reconcile_secret" in set(inspector.get_table_names())
    assert stamped_revision == "004_broker_reconcile_secret"


def test_control_plane_alembic_upgrade_stamps_existing_alert_config_schema(tmp_path):
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'control-plane-alert-config-bootstrap.db').as_posix()}"
    engine = create_sync_engine_for_url(database_url)

    Base.metadata.create_all(bind=engine, tables=[
        BrokerDesiredState.__table__,
        BrokerDesiredStateAudit.__table__,
        AlertConfigEntry.__table__,
    ])

    upgrade_control_plane_database_sync(database_url)

    with engine.begin() as connection:
        stamped_revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()

        assert stamped_revision == "004_broker_reconcile_secret"


def test_control_plane_alembic_upgrade_accepts_preexisting_alert_config_on_revision_001(tmp_path):
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'control-plane-alert-config-revision-001.db').as_posix()}"
    engine = create_sync_engine_for_url(database_url)

    upgrade_control_plane_database_sync(database_url, revision="001_control_plane_initial")
    Base.metadata.create_all(bind=engine, tables=[AlertConfigEntry.__table__])

    upgrade_control_plane_database_sync(database_url)

    with engine.begin() as connection:
        stamped_revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()

        assert stamped_revision == "004_broker_reconcile_secret"


def test_control_plane_alembic_upgrade_stamps_existing_alert_delivery_schema(tmp_path):
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'control-plane-alert-delivery-bootstrap.db').as_posix()}"
    engine = create_sync_engine_for_url(database_url)

    Base.metadata.create_all(bind=engine, tables=[
        BrokerDesiredState.__table__,
        BrokerDesiredStateAudit.__table__,
        AlertConfigEntry.__table__,
        AlertDeliveryChannel.__table__,
        AlertDeliveryEvent.__table__,
        AlertDeliveryAttempt.__table__,
        BrokerReconcileSecret.__table__,
    ])

    upgrade_control_plane_database_sync(database_url)

    with engine.begin() as connection:
        stamped_revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()

        assert stamped_revision == "004_broker_reconcile_secret"