"""Add client_publish_state table.

Stores one record per (username, topic) for publish events — mirroring
client_subscription_state but for publish permissions.  Publish events are
no longer appended to client_mqtt_events; only this state table is updated.

Revision ID: 003_add_client_publish_state
Revises: 002_consolidate_client_events
Create Date: 2026-05-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "003_add_client_publish_state"
down_revision = "002_consolidate_client_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())

    if "client_publish_state" not in existing:
        op.create_table(
            "client_publish_state",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("username", sa.String(length=128), nullable=False),
            sa.Column("topic", sa.String(length=512), nullable=False),
            sa.Column("first_seen_at", sa.DateTime(), nullable=False),
            sa.Column("last_seen_at", sa.DateTime(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("source", sa.String(length=64), nullable=False, server_default="clientlogs"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("username", "topic", name="uq_client_publish_state"),
        )
        op.create_index("ix_client_publish_state_username", "client_publish_state", ["username"], unique=False)
        op.create_index("ix_client_publish_state_topic", "client_publish_state", ["topic"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())

    if "client_publish_state" in existing:
        op.drop_index("ix_client_publish_state_topic", table_name="client_publish_state")
        op.drop_index("ix_client_publish_state_username", table_name="client_publish_state")
        op.drop_table("client_publish_state")
