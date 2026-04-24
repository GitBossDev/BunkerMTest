"""Mover tablas del schema public al schema control_plane.

Revision ID: 005_schema_control_plane
Revises: 004_broker_reconcile_secret
Create Date: 2026-04-21

Razon: introduccion de schemas de dominio en PostgreSQL para aislar bounded-contexts
y permitir acceso compartido con otros microservicios del ecosistema BHM.

Las tablas se mueven del schema 'public' (default) al schema 'control_plane'.
La version de Alembic tambien se reubica en 'control_plane' para que las futures
migraciones del control-plane no colisionen con las de history/reporting/identity.

Si la tabla ya existe en 'control_plane' (idempotencia en re-ejecucion), se omite.
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import inspect, text


revision = "005_schema_control_plane"
down_revision = "004_broker_reconcile_secret"
branch_labels = None
depends_on = None

# Tablas que pertenecen al bounded-context control_plane
_CONTROL_PLANE_TABLES = [
    "broker_desired_state",
    "broker_desired_state_audit",
    "broker_reconcile_secret",
    "alert_config",
    "alert_delivery_channel",
    "alert_delivery_event",
    "alert_delivery_attempt",
]


def _schema_exists(bind, schema: str) -> bool:
    result = bind.execute(
        text("SELECT schema_name FROM information_schema.schemata WHERE schema_name = :s"),
        {"s": schema},
    )
    return result.fetchone() is not None


def _table_exists_in_schema(bind, table: str, schema: str) -> bool:
    result = bind.execute(
        text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = :s AND table_name = :t"
        ),
        {"s": schema, "t": table},
    )
    return result.fetchone() is not None


def upgrade() -> None:
    # This migration previously moved tables from public to control_plane schema.
    # That caused ORM query failures because models have no schema= qualifier and
    # therefore expect all tables in 'public' (PostgreSQL default).
    #
    # For fresh installs: tables are created in public by migrations 001-004 and
    # should stay there. This migration is now a no-op.
    #
    # For existing installs where tables were already moved to control_plane by a
    # previous version of this migration: move them back to public so the ORM works.
    bind = op.get_bind()
    for table in _CONTROL_PLANE_TABLES:
        in_cp = _table_exists_in_schema(bind, table, "control_plane")
        in_public = _table_exists_in_schema(bind, table, "public")
        if in_cp and not in_public:
            bind.execute(text(f"ALTER TABLE control_plane.{table} SET SCHEMA public"))


def downgrade() -> None:
    pass
