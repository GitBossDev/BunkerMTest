from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_PATH = REPO_ROOT / ".env.dev"
DEFAULT_CONTAINER_NAME = "bunkerm-postgres"
DEFAULT_BACKUP_DIR = REPO_ROOT / "data" / "backups"


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()

    return values


def detect_container_engine() -> str:
    for candidate in ("podman", "docker"):
        if shutil.which(candidate):
            return candidate
    raise RuntimeError("Neither podman nor docker is available in PATH")


def build_output_path(explicit_output: str | None, database_name: str) -> Path:
    if explicit_output:
        return Path(explicit_output).expanduser().resolve()

    DEFAULT_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return (DEFAULT_BACKUP_DIR / f"postgres-{database_name}-{timestamp}.dump").resolve()


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a PostgreSQL backup from the running Compose container.")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_PATH), help="Path to the env file with PostgreSQL credentials.")
    parser.add_argument("--container", default=DEFAULT_CONTAINER_NAME, help="Name of the running PostgreSQL container.")
    parser.add_argument("--database", help="Database name to backup. Defaults to POSTGRES_DB from the env file.")
    parser.add_argument("--user", help="Database user. Defaults to POSTGRES_USER from the env file.")
    parser.add_argument("--password", help="Database password. Defaults to POSTGRES_PASSWORD from the env file.")
    parser.add_argument("--output", help="Output dump file path. Defaults to data/backups/postgres-<db>-<timestamp>.dump")
    args = parser.parse_args()

    env_values = load_env_file(Path(args.env_file))
    database_name = args.database or env_values.get("POSTGRES_DB")
    database_user = args.user or env_values.get("POSTGRES_USER")
    database_password = args.password or env_values.get("POSTGRES_PASSWORD")

    if not database_name or not database_user or not database_password:
        print("Missing PostgreSQL credentials. Provide --database/--user/--password or use a valid .env.dev.", file=sys.stderr)
        return 1

    output_path = build_output_path(args.output, database_name)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    engine = detect_container_engine()
    command = [
        engine,
        "exec",
        "-e",
        f"PGPASSWORD={database_password}",
        args.container,
        "pg_dump",
        "-U",
        database_user,
        "-d",
        database_name,
        "-Fc",
        "--no-owner",
        "--no-privileges",
    ]

    with output_path.open("wb") as output_file:
        completed = subprocess.run(command, stdout=output_file)

    if completed.returncode != 0:
        if output_path.exists():
            output_path.unlink()
        return completed.returncode

    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())