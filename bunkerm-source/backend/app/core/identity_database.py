"""Async SQLAlchemy session dedicated to the 'identity' PostgreSQL schema.

Provides get_identity_db() FastAPI dependency used by the identity router (5B-1)
and the standalone bhm-identity service (5B-2).
"""
from __future__ import annotations

import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.config import settings
from core.database_url import get_async_database_url, get_async_engine_connect_args

logger = logging.getLogger(__name__)

# Module-level lazy singleton — created on first call to avoid import-time side effects.
_IdentitySessionLocal: async_sessionmaker[AsyncSession] | None = None


def _make_identity_session_maker() -> async_sessionmaker[AsyncSession]:
    url = get_async_database_url(settings.resolved_identity_database_url)
    connect_args = get_async_engine_connect_args(url)
    engine_kwargs: dict = {"echo": False}
    if connect_args:
        engine_kwargs["connect_args"] = connect_args
    _engine = create_async_engine(url, **engine_kwargs)
    logger.debug("Identity DB engine created: %s", url.split("@")[-1])
    return async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


def _get_identity_session_maker() -> async_sessionmaker[AsyncSession]:
    global _IdentitySessionLocal
    if _IdentitySessionLocal is None:
        _IdentitySessionLocal = _make_identity_session_maker()
    return _IdentitySessionLocal


async def get_identity_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: async SQLAlchemy session for the identity schema."""
    async with _get_identity_session_maker()() as session:
        yield session
