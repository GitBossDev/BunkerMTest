"""Remove client_mqtt_events from control-plane DB.

The table moves to the history/reporting database as the canonical event
store.  Data in the control-plane copy is abandoned (acceptable: the table
was written only by the backend process and the history DB already contains
the authoritative event log after migration 002_consolidate_client_events).

Revision ID: 008_rm_client_mqtt_events
Revises: 007_client_mqtt_events
Create Date: 2026-04-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "008_rm_client_mqtt_events"
down_revision = "007_client_mqtt_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "client_mqtt_events" not in set(inspector.get_table_names()):
        return
    # Drop indexes before table (some backends require this)
    for idx in ("ix_client_mqtt_events_topic", "ix_client_mqtt_events_username",
                "ix_client_mqtt_events_client_id", "ix_client_mqtt_events_event_type",
                "ix_client_mqtt_events_timestamp", "ix_client_mqtt_events_event_id"):
        try:
            op.drop_index(idx, table_name="client_mqtt_events")
        except Exception:
            pass
    op.drop_table("client_mqtt_events")


def downgrade() -> None:
    """Recreate the table in control-plane DB (empty, without migrated data)."""
    op.create_table(
        "client_mqtt_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("client_id", sa.String(length=256), nullable=False),
        sa.Column("username", sa.String(length=128), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("port", sa.Integer(), nullable=True),
        sa.Column("protocol_level", sa.String(length=32), nullable=True),
        sa.Column("clean_session", sa.Boolean(), nullable=True),
        sa.Column("keep_alive", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("details", sa.Text(), nullable=False),
        sa.Column("topic", sa.String(length=512), nullable=True),
        sa.Column("qos", sa.Integer(), nullable=True),
        sa.Column("payload_bytes", sa.Integer(), nullable=True),
        sa.Column("retained", sa.Boolean(), nullable=True),
        sa.Column("disconnect_kind", sa.String(length=64), nullable=True),
        sa.Column("reason_code", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", name="uq_client_mqtt_events_event_id"),
    )
    op.create_index("ix_client_mqtt_events_event_id", "client_mqtt_events", ["event_id"], unique=True)
    op.create_index("ix_client_mqtt_events_timestamp", "client_mqtt_events", ["timestamp"], unique=False)
    op.create_index("ix_client_mqtt_events_event_type", "client_mqtt_events", ["event_type"], unique=False)
    op.create_index("ix_client_mqtt_events_client_id", "client_mqtt_events", ["client_id"], unique=False)
    op.create_index("ix_client_mqtt_events_username", "client_mqtt_events", ["username"], unique=False)
    op.create_index("ix_client_mqtt_events_topic", "client_mqtt_events", ["topic"], unique=False)
