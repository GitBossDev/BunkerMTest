"""Helpers para clasificar URLs de base de datos y aplicar configuración por backend."""
from __future__ import annotations

import os
import socket

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


def get_backend_name(database_url: str) -> str:
    try:
        return make_url(database_url).get_backend_name()
    except ArgumentError as exc:
        raise ValueError(f"Invalid database URL: {database_url}") from exc


def is_sqlite_url(database_url: str) -> bool:
    return get_backend_name(database_url) == "sqlite"


def ensure_postgres_url(database_url: str, setting_name: str) -> None:
    if get_backend_name(database_url) != "postgresql":
        raise ValueError(
            f"{setting_name} must use a PostgreSQL URL in the active BHM baseline: {database_url}"
        )


def get_async_engine_connect_args(database_url: str) -> dict[str, object]:
    if is_sqlite_url(database_url):
        return {"check_same_thread": False}
    if get_backend_name(database_url) == "postgresql":
        return {"timeout": 5, "command_timeout": 30}
    return {}


def get_async_database_url(database_url: str) -> str:
    try:
        url = make_url(database_url)
    except ArgumentError as exc:
        raise ValueError(f"Invalid database URL: {database_url}") from exc

    if url.drivername in {"sqlite", "sqlite+pysqlite"}:
        return url.set(drivername="sqlite+aiosqlite").render_as_string(hide_password=False)
    if url.drivername in {"postgresql", "postgresql+psycopg2", "postgresql+psycopg"}:
        return url.set(drivername="postgresql+asyncpg").render_as_string(hide_password=False)
    return url.render_as_string(hide_password=False)


def get_sync_database_url(database_url: str) -> str:
    try:
        url = make_url(database_url)
    except ArgumentError as exc:
        raise ValueError(f"Invalid database URL: {database_url}") from exc

    if url.drivername == "sqlite+aiosqlite":
        return url.set(drivername="sqlite+pysqlite").render_as_string(hide_password=False)
    if url.drivername in {"postgresql", "postgresql+asyncpg", "postgresql+psycopg2"}:
        return url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)
    return url.render_as_string(hide_password=False)


def get_sync_engine_connect_args(database_url: str) -> dict[str, object]:
    if is_sqlite_url(database_url):
        return {"check_same_thread": False}
    if get_backend_name(database_url) == "postgresql":
        return {"connect_timeout": 5}
    return {}


def get_host_accessible_database_url(database_url: str, fallback_host: str = "localhost") -> str:
    try:
        url = make_url(database_url)
    except ArgumentError as exc:
        raise ValueError(f"Invalid database URL: {database_url}") from exc

    if url.get_backend_name() != "postgresql" or not url.host:
        return url.render_as_string(hide_password=False)

    override_host = os.getenv("BHM_POSTGRES_HOST_OVERRIDE")
    if override_host:
        return url.set(host=override_host).render_as_string(hide_password=False)

    if url.host.lower() != "postgres":
        return url.render_as_string(hide_password=False)

    try:
        socket.getaddrinfo(url.host, int(url.port or 5432))
        return url.render_as_string(hide_password=False)
    except OSError:
        return url.set(host=fallback_host).render_as_string(hide_password=False)


def ensure_sqlite_url(database_url: str, setting_name: str) -> None:
    if not is_sqlite_url(database_url):
        raise ValueError(
            f"{setting_name} currently supports only SQLite URLs during this migration cut: {database_url}"
        )