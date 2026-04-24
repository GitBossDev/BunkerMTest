"""Create identity.bhm_users table for panel user management.

Revision ID: 006_identity_bhm_users
Revises: 005_schema_control_plane
Create Date: 2026-04-21

Creates the 'bhm_users' table inside the 'identity' schema.
The identity schema is created here if it does not already exist (idempotent).
This migration is intentionally data-free: initial user seeding is handled
by the application startup (init_identity_data).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "006_identity_bhm_users"
down_revision = "005_schema_control_plane"
branch_labels = None
depends_on = None


def _table_exists_in_schema(bind, table: str, schema: str) -> bool:
    inspector = sa.inspect(bind)
    return table in inspector.get_table_names(schema=schema)


def _schema_exists(bind, schema: str) -> bool:
    inspector = sa.inspect(bind)
    return schema in inspector.get_schema_names()


def upgrade() -> None:
    bind = op.get_bind()

    if not _schema_exists(bind, "identity"):
        bind.execute(sa.text("CREATE SCHEMA IF NOT EXISTS identity"))

    if not _table_exists_in_schema(bind, "bhm_users", "identity"):
        op.create_table(
            "bhm_users",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("email", sa.String(255), nullable=False),
            sa.Column("password_hash", sa.String(255), nullable=False),
            sa.Column("first_name", sa.String(128), nullable=False),
            sa.Column("last_name", sa.String(128), nullable=False),
            sa.Column("role", sa.String(32), nullable=False, server_default="user"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            schema="identity",
        )
        op.create_index(
            "ix_identity_bhm_users_email",
            "bhm_users",
            ["email"],
            unique=True,
            schema="identity",
        )
        op.create_index(
            "ix_identity_bhm_users_role",
            "bhm_users",
            ["role"],
            unique=False,
            schema="identity",
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists_in_schema(bind, "bhm_users", "identity"):
        op.drop_index("ix_identity_bhm_users_role", table_name="bhm_users", schema="identity")
        op.drop_index("ix_identity_bhm_users_email", table_name="bhm_users", schema="identity")
        op.drop_table("bhm_users", schema="identity")
