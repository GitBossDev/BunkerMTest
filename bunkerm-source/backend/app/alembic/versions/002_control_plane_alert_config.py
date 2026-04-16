"""Control-plane alert configuration.

Revision ID: 002_control_plane_alert_config
Revises: 001_control_plane_initial
Create Date: 2026-04-16
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "002_control_plane_alert_config"
down_revision = "001_control_plane_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "alert_config" in set(inspector.get_table_names()):
        return

    op.create_table(
        "alert_config",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("alert_config")