"""Broker reconcile secret staging.

Revision ID: 004_broker_reconcile_secret
Revises: 003_alert_delivery_outbox
Create Date: 2026-04-16
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "004_broker_reconcile_secret"
down_revision = "003_alert_delivery_outbox"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "broker_reconcile_secret" in set(inspector.get_table_names()):
        return

    op.create_table(
        "broker_reconcile_secret",
        sa.Column("secret_key", sa.String(length=64), nullable=False),
        sa.Column("scope", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("encrypted_payload", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("secret_key"),
    )
    op.create_index("ix_broker_reconcile_secret_scope", "broker_reconcile_secret", ["scope"], unique=False)
    op.create_index("ix_broker_reconcile_secret_version", "broker_reconcile_secret", ["version"], unique=False)
    op.create_index("ix_broker_reconcile_secret_expires_at", "broker_reconcile_secret", ["expires_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_broker_reconcile_secret_expires_at", table_name="broker_reconcile_secret")
    op.drop_index("ix_broker_reconcile_secret_version", table_name="broker_reconcile_secret")
    op.drop_index("ix_broker_reconcile_secret_scope", table_name="broker_reconcile_secret")
    op.drop_table("broker_reconcile_secret")