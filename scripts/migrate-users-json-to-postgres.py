#!/usr/bin/env python3
"""migrate-users-json-to-postgres.py

Migrates BHM panel users from the legacy data/users.json file to the
identity.bhm_users PostgreSQL table (created by Alembic migration 006).

Usage:
  python scripts/migrate-users-json-to-postgres.py \
      --json-file /path/to/data/users.json \
      --database-url "postgresql://bhm:password@postgres:5432/bhm_db?options=-csearch_path%3Didentity"

The script is idempotent: users that already exist (same email) are skipped.
It does NOT delete the JSON file afterwards — rename or remove it manually after
verifying the migration result.

Requirements (install in the backend venv):
  pip install sqlalchemy psycopg2-binary bcrypt
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


def _load_json_users(json_path: Path) -> list[dict]:
    if not json_path.exists():
        print(f"[ERROR] File not found: {json_path}", file=sys.stderr)
        sys.exit(1)
    with json_path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        print("[ERROR] Expected a JSON array at the top level", file=sys.stderr)
        sys.exit(1)
    return data


def _get_sync_url(url: str) -> str:
    """Convert postgresql+asyncpg or bare postgresql to psycopg2 sync URL."""
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


def migrate(json_path: Path, database_url: str, dry_run: bool) -> None:
    try:
        import sqlalchemy as sa
    except ImportError:
        print("[ERROR] sqlalchemy is not installed. Run: pip install sqlalchemy", file=sys.stderr)
        sys.exit(1)

    users_json = _load_json_users(json_path)
    print(f"[INFO] Loaded {len(users_json)} user(s) from {json_path}")

    sync_url = _get_sync_url(database_url)
    engine = sa.create_engine(sync_url)

    # Ensure schema + table exist (idempotent)
    with engine.connect() as conn:
        conn.execute(sa.text("CREATE SCHEMA IF NOT EXISTS identity"))
        conn.execute(sa.text("""
            CREATE TABLE IF NOT EXISTS identity.bhm_users (
                id           VARCHAR(36)  PRIMARY KEY,
                email        VARCHAR(255) NOT NULL UNIQUE,
                password_hash VARCHAR(255) NOT NULL,
                first_name   VARCHAR(128) NOT NULL,
                last_name    VARCHAR(128) NOT NULL,
                role         VARCHAR(32)  NOT NULL DEFAULT 'user',
                created_at   TIMESTAMP    NOT NULL,
                updated_at   TIMESTAMP    NOT NULL
            )
        """))
        conn.commit()

    inserted = 0
    skipped = 0

    with engine.connect() as conn:
        for raw in users_json:
            email = (raw.get("email") or "").strip().lower()
            if not email:
                print(f"[WARN] Skipping user with missing email: {raw}", file=sys.stderr)
                skipped += 1
                continue

            # Check if already migrated
            existing = conn.execute(
                sa.text("SELECT id FROM identity.bhm_users WHERE email = :email"),
                {"email": email},
            ).fetchone()
            if existing:
                print(f"[SKIP] Already exists: {email}")
                skipped += 1
                continue

            user_id = raw.get("id") or str(__import__("uuid").uuid4())
            password_hash = raw.get("passwordHash") or raw.get("password_hash") or ""
            if not password_hash:
                print(f"[WARN] No password hash for {email} — skipping", file=sys.stderr)
                skipped += 1
                continue

            first_name = raw.get("firstName") or raw.get("first_name") or "Migrated"
            last_name = raw.get("lastName") or raw.get("last_name") or "User"
            role = raw.get("role") or "admin"
            if role not in {"admin", "user"}:
                role = "user"
            created_at_raw = raw.get("createdAt") or raw.get("created_at")
            try:
                created_at = datetime.fromisoformat(created_at_raw) if created_at_raw else datetime.utcnow()
            except ValueError:
                created_at = datetime.utcnow()

            now = datetime.utcnow()

            if dry_run:
                print(f"[DRY-RUN] Would insert: {email} (role={role})")
                inserted += 1
                continue

            conn.execute(
                sa.text("""
                    INSERT INTO identity.bhm_users
                        (id, email, password_hash, first_name, last_name, role, created_at, updated_at)
                    VALUES
                        (:id, :email, :password_hash, :first_name, :last_name, :role, :created_at, :updated_at)
                """),
                {
                    "id": user_id,
                    "email": email,
                    "password_hash": password_hash,
                    "first_name": first_name,
                    "last_name": last_name,
                    "role": role,
                    "created_at": created_at,
                    "updated_at": now,
                },
            )
            print(f"[OK] Inserted: {email} (role={role})")
            inserted += 1

        if not dry_run:
            conn.commit()

    print(f"\n[DONE] Inserted={inserted} Skipped={skipped}")
    if not dry_run:
        print("[NOTE] Verify the migration, then remove or rename the original JSON file.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate users.json to identity.bhm_users")
    parser.add_argument(
        "--json-file",
        default="data/users.json",
        help="Path to the legacy users.json file (default: data/users.json)",
    )
    parser.add_argument(
        "--database-url",
        help="PostgreSQL connection URL (defaults to IDENTITY_DATABASE_URL env var)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be inserted without writing to the database",
    )
    args = parser.parse_args()

    database_url = args.database_url
    if not database_url:
        import os
        database_url = os.environ.get("IDENTITY_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not database_url:
        print("[ERROR] --database-url or IDENTITY_DATABASE_URL must be set", file=sys.stderr)
        sys.exit(1)

    migrate(Path(args.json_file), database_url, args.dry_run)


if __name__ == "__main__":
    main()
