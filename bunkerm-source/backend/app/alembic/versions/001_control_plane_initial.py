"""Initial control-plane schema.

Revision ID: 001_control_plane_initial
Revises:
Create Date: 2026-04-15
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "001_control_plane_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "broker_desired_state",
        sa.Column("scope", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("desired_payload_json", sa.Text(), nullable=False),
        sa.Column("applied_payload_json", sa.Text(), nullable=True),
        sa.Column("observed_payload_json", sa.Text(), nullable=True),
        sa.Column("reconcile_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("drift_detected", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("desired_updated_at", sa.DateTime(), nullable=False),
        sa.Column("reconciled_at", sa.DateTime(), nullable=True),
        sa.Column("applied_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("scope"),
    )
    op.create_table(
        "broker_desired_state_audit",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scope", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("event_kind", sa.String(length=32), nullable=False),
        sa.Column("desired_payload_json", sa.Text(), nullable=True),
        sa.Column("applied_payload_json", sa.Text(), nullable=True),
        sa.Column("observed_payload_json", sa.Text(), nullable=True),
        sa.Column("reconcile_status", sa.String(length=32), nullable=False),
        sa.Column("drift_detected", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_broker_desired_state_audit_scope", "broker_desired_state_audit", ["scope"], unique=False)
    op.create_index("ix_broker_desired_state_audit_version", "broker_desired_state_audit", ["version"], unique=False)
    op.create_index("ix_broker_desired_state_audit_recorded_at", "broker_desired_state_audit", ["recorded_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_broker_desired_state_audit_recorded_at", table_name="broker_desired_state_audit")
    op.drop_index("ix_broker_desired_state_audit_version", table_name="broker_desired_state_audit")
    op.drop_index("ix_broker_desired_state_audit_scope", table_name="broker_desired_state_audit")
    op.drop_table("broker_desired_state_audit")
    op.drop_table("broker_desired_state")