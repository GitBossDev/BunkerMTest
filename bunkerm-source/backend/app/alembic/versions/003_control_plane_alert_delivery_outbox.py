"""Alert delivery outbox schema.

Revision ID: 003_alert_delivery_outbox
Revises: 002_control_plane_alert_config
Create Date: 2026-04-16
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "003_alert_delivery_outbox"
down_revision = "002_control_plane_alert_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alert_delivery_channel",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("channel_key", sa.String(length=64), nullable=False),
        sa.Column("channel_type", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("config_json", sa.Text(), nullable=False),
        sa.Column("secret_ref", sa.String(length=256), nullable=True),
        sa.Column("last_delivery_status", sa.String(length=32), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_alert_delivery_channel_channel_key",
        "alert_delivery_channel",
        ["channel_key"],
        unique=True,
    )
    op.create_index(
        "ix_alert_delivery_channel_channel_type",
        "alert_delivery_channel",
        ["channel_type"],
        unique=False,
    )

    op.create_table(
        "alert_delivery_event",
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("alert_id", sa.String(length=128), nullable=False),
        sa.Column("dedupe_key", sa.String(length=256), nullable=False),
        sa.Column("transition", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("delivery_state", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("channel_policy_id", sa.String(length=64), nullable=True),
        sa.Column("channel_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index("ix_alert_delivery_event_alert_id", "alert_delivery_event", ["alert_id"], unique=False)
    op.create_index("ix_alert_delivery_event_created_at", "alert_delivery_event", ["created_at"], unique=False)
    op.create_index(
        "ix_alert_delivery_event_dedupe_key",
        "alert_delivery_event",
        ["dedupe_key"],
        unique=True,
    )
    op.create_index(
        "ix_alert_delivery_event_delivery_state",
        "alert_delivery_event",
        ["delivery_state"],
        unique=False,
    )
    op.create_index(
        "ix_alert_delivery_event_next_attempt_at",
        "alert_delivery_event",
        ["next_attempt_at"],
        unique=False,
    )

    op.create_table(
        "alert_delivery_attempt",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("channel_id", sa.Integer(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("attempt_state", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("scheduled_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("provider_status_code", sa.Integer(), nullable=True),
        sa.Column("provider_message_id", sa.String(length=256), nullable=True),
        sa.Column("error_class", sa.String(length=128), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("response_payload_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["channel_id"], ["alert_delivery_channel.id"]),
        sa.ForeignKeyConstraint(["event_id"], ["alert_delivery_event.event_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "event_id",
            "channel_id",
            "attempt_number",
            name="uq_alert_delivery_attempt_event_channel_attempt",
        ),
    )
    op.create_index("ix_alert_delivery_attempt_attempt_state", "alert_delivery_attempt", ["attempt_state"], unique=False)
    op.create_index("ix_alert_delivery_attempt_channel_id", "alert_delivery_attempt", ["channel_id"], unique=False)
    op.create_index("ix_alert_delivery_attempt_event_id", "alert_delivery_attempt", ["event_id"], unique=False)
    op.create_index("ix_alert_delivery_attempt_scheduled_at", "alert_delivery_attempt", ["scheduled_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_alert_delivery_attempt_scheduled_at", table_name="alert_delivery_attempt")
    op.drop_index("ix_alert_delivery_attempt_event_id", table_name="alert_delivery_attempt")
    op.drop_index("ix_alert_delivery_attempt_channel_id", table_name="alert_delivery_attempt")
    op.drop_index("ix_alert_delivery_attempt_attempt_state", table_name="alert_delivery_attempt")
    op.drop_table("alert_delivery_attempt")

    op.drop_index("ix_alert_delivery_event_next_attempt_at", table_name="alert_delivery_event")
    op.drop_index("ix_alert_delivery_event_delivery_state", table_name="alert_delivery_event")
    op.drop_index("ix_alert_delivery_event_dedupe_key", table_name="alert_delivery_event")
    op.drop_index("ix_alert_delivery_event_created_at", table_name="alert_delivery_event")
    op.drop_index("ix_alert_delivery_event_alert_id", table_name="alert_delivery_event")
    op.drop_table("alert_delivery_event")

    op.drop_index("ix_alert_delivery_channel_channel_type", table_name="alert_delivery_channel")
    op.drop_index("ix_alert_delivery_channel_channel_key", table_name="alert_delivery_channel")
    op.drop_table("alert_delivery_channel")
