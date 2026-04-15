from __future__ import annotations

import os
import socket
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

from core.database_url import get_async_database_url


REAL_POSTGRES_ENV = "BHM_REAL_POSTGRES_TESTS"
DEFAULT_POSTGRES_URL_ENV = "BHM_REAL_CONTROL_PLANE_DATABASE_URL"


def repo_root() -> Path:
    return Path(__file__).parents[4]


def load_env_file() -> dict[str, str]:
    env_path = repo_root() / ".env.dev"
    values: dict[str, str] = {}
    if not env_path.exists():
        return values
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def real_postgres_async_url(env_name: str = DEFAULT_POSTGRES_URL_ENV) -> str:
    explicit = os.getenv(env_name)
    if explicit:
        return get_async_database_url(explicit)

    env_values = load_env_file()
    user = env_values.get("POSTGRES_USER")
    password = env_values.get("POSTGRES_PASSWORD")
    database = env_values.get("POSTGRES_DB")
    port = env_values.get("POSTGRES_PORT", "5432")
    if not user or not password or not database:
        pytest.skip("PostgreSQL credentials are not available in .env.dev")
    return f"postgresql+asyncpg://{user}:{password}@localhost:{port}/{database}"


def require_real_postgres(env_name: str = DEFAULT_POSTGRES_URL_ENV) -> str:
    if os.getenv(REAL_POSTGRES_ENV) != "1":
        pytest.skip(f"Set {REAL_POSTGRES_ENV}=1 to run live PostgreSQL integration tests")
    database_url = real_postgres_async_url(env_name)
    parsed = make_url(database_url)
    host = parsed.host or "localhost"
    port = int(parsed.port or 5432)
    try:
        with socket.create_connection((host, port), timeout=2.0):
            pass
    except OSError:
        pytest.skip(f"PostgreSQL endpoint {host}:{port} is not reachable")
    return database_url