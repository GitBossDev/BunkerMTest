"""Add client MQTT events table for persistent event logging.

Revision ID: 005_client_mqtt_events
Revises: 004_broker_reconcile_secret
Create Date: 2026-04-22
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "005_client_mqtt_events"
down_revision = "004_broker_reconcile_secret"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "client_mqtt_events" in set(inspector.get_table_names()):
        return

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


def downgrade() -> None:
    op.drop_index("ix_client_mqtt_events_topic", table_name="client_mqtt_events")
    op.drop_index("ix_client_mqtt_events_username", table_name="client_mqtt_events")
    op.drop_index("ix_client_mqtt_events_client_id", table_name="client_mqtt_events")
    op.drop_index("ix_client_mqtt_events_event_type", table_name="client_mqtt_events")
    op.drop_index("ix_client_mqtt_events_timestamp", table_name="client_mqtt_events")
    op.drop_index("ix_client_mqtt_events_event_id", table_name="client_mqtt_events")
    op.drop_table("client_mqtt_events")
