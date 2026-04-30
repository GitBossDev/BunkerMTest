"""Consolidate client events: drop legacy split tables, ensure client_mqtt_events exists.

- Drops client_session_events (legacy)
- Drops client_topic_events (legacy)
- Creates client_mqtt_events as the single canonical event store (if not present)

For fresh installs, 001_history_reporting_initial already creates client_mqtt_events
directly, so the CREATE is a no-op (checkfirst=True).

For existing installs, the legacy tables are dropped and client_mqtt_events is
created.  Existing data in the legacy tables is abandoned; the control-plane
client_mqtt_events table is also removed by control-plane migration 008.

Revision ID: 002_consolidate_client_events
Revises: 001_history_reporting_initial
Create Date: 2026-04-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "002_consolidate_client_events"
down_revision = "001_history_reporting_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())

    # Drop legacy tables (no-op if already absent)
    for table_name in ("client_session_events", "client_topic_events"):
        if table_name in existing:
            op.drop_table(table_name)

    # Create the canonical event store (no-op if 001 already created it)
    if "client_mqtt_events" not in existing:
        op.create_table(
            "client_mqtt_events",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("event_id", sa.String(length=36), nullable=False),
            sa.Column("event_ts", sa.DateTime(), nullable=False),
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
        op.create_index("ix_client_mqtt_events_event_ts", "client_mqtt_events", ["event_ts"], unique=False)
        op.create_index("ix_client_mqtt_events_event_type", "client_mqtt_events", ["event_type"], unique=False)
        op.create_index("ix_client_mqtt_events_client_id", "client_mqtt_events", ["client_id"], unique=False)
        op.create_index("ix_client_mqtt_events_username", "client_mqtt_events", ["username"], unique=False)
        op.create_index("ix_client_mqtt_events_topic", "client_mqtt_events", ["topic"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())

    if "client_mqtt_events" in existing:
        for idx in ("ix_client_mqtt_events_topic", "ix_client_mqtt_events_username",
                    "ix_client_mqtt_events_client_id", "ix_client_mqtt_events_event_type",
                    "ix_client_mqtt_events_event_ts", "ix_client_mqtt_events_event_id"):
            try:
                op.drop_index(idx, table_name="client_mqtt_events")
            except Exception:
                pass
        op.drop_table("client_mqtt_events")

    # Recreate legacy tables
    if "client_session_events" not in existing:
        op.create_table(
            "client_session_events",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("username", sa.String(length=128), nullable=True),
            sa.Column("client_id", sa.String(length=256), nullable=False),
            sa.Column("event_ts", sa.DateTime(), nullable=False),
            sa.Column("event_type", sa.String(length=64), nullable=False),
            sa.Column("disconnect_kind", sa.String(length=64), nullable=True),
            sa.Column("reason_code", sa.String(length=128), nullable=True),
            sa.Column("ip_address", sa.String(length=64), nullable=True),
            sa.Column("port", sa.Integer(), nullable=True),
            sa.Column("protocol_level", sa.String(length=32), nullable=True),
            sa.Column("clean_session", sa.Boolean(), nullable=True),
            sa.Column("keep_alive", sa.Integer(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_client_session_events_event_ts", "client_session_events", ["event_ts"], unique=False)
        op.create_index("ix_client_session_events_username", "client_session_events", ["username"], unique=False)

    if "client_topic_events" not in existing:
        op.create_table(
            "client_topic_events",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("username", sa.String(length=128), nullable=True),
            sa.Column("client_id", sa.String(length=256), nullable=False),
            sa.Column("event_ts", sa.DateTime(), nullable=False),
            sa.Column("event_type", sa.String(length=64), nullable=False),
            sa.Column("topic", sa.String(length=512), nullable=False),
            sa.Column("qos", sa.Integer(), nullable=True),
            sa.Column("payload_bytes", sa.Integer(), nullable=True),
            sa.Column("retained", sa.Boolean(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_client_topic_events_event_ts", "client_topic_events", ["event_ts"], unique=False)
        op.create_index("ix_client_topic_events_username", "client_topic_events", ["username"], unique=False)
