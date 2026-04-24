"""BHM Identity Service — standalone FastAPI process.

This is the entry point for the bhm-identity container (5B-2).
It serves only the identity router on port 8080 using IDENTITY_DATABASE_URL.

Start with:
    uvicorn identity_main:app --host 0.0.0.0 --port 8080
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime
from uuid import uuid4

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy import func, select, text

from core.config import settings
from core.identity_database import _get_identity_session_maker
from models.orm import BhmUser

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Database bootstrap helpers (lightweight — no full Alembic run)
# ---------------------------------------------------------------------------

async def _ensure_identity_schema() -> None:
    """Create the identity schema and bhm_users table if they do not exist.

    This is a safety net for cold starts before bhm-api has run migration 006.
    The authoritative schema creation is via Alembic migration 006_identity_bhm_users.
    """
    import sqlalchemy as sa

    session_maker = _get_identity_session_maker()
    async with session_maker() as db:
        await db.execute(text("CREATE SCHEMA IF NOT EXISTS identity"))
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS identity.bhm_users (
                id            VARCHAR(36)  PRIMARY KEY,
                email         VARCHAR(255) NOT NULL UNIQUE,
                password_hash VARCHAR(255) NOT NULL,
                first_name    VARCHAR(128) NOT NULL,
                last_name     VARCHAR(128) NOT NULL,
                role          VARCHAR(32)  NOT NULL DEFAULT 'user',
                created_at    TIMESTAMP    NOT NULL,
                updated_at    TIMESTAMP    NOT NULL
            )
        """))
        await db.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_identity_bhm_users_email
                ON identity.bhm_users (email)
        """))
        await db.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_identity_bhm_users_role
                ON identity.bhm_users (role)
        """))
        await db.commit()
        logger.info("identity.bhm_users schema verified")


async def _seed_admin() -> None:
    """Seed the initial admin user if identity.bhm_users is empty."""
    import bcrypt as _bcrypt

    session_maker = _get_identity_session_maker()
    async with session_maker() as db:
        count = (await db.execute(select(func.count()).select_from(BhmUser))).scalar_one()
        if count > 0:
            return

        admin_email = os.environ.get("ADMIN_INITIAL_EMAIL", "admin@bhm.local")
        raw_password = os.environ.get("ADMIN_INITIAL_PASSWORD")
        if not raw_password:
            raw_password = str(uuid4())
            logger.warning(
                "ADMIN_INITIAL_PASSWORD not set — generated initial admin password: %s",
                raw_password,
            )

        now = datetime.utcnow()
        admin = BhmUser(
            id=str(uuid4()),
            email=admin_email.strip().lower(),
            password_hash=_bcrypt.hashpw(raw_password.encode(), _bcrypt.gensalt(10)).decode(),
            first_name="Admin",
            last_name="User",
            role="admin",
            created_at=now,
            updated_at=now,
        )
        db.add(admin)
        await db.commit()
        logger.info("Seeded initial admin user: %s", admin_email)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("bhm-identity service starting…")

    # Retry loop: wait for PostgreSQL to be ready before running schema setup.
    # Mirrors the retry pattern in core/database.py (init_db).
    # We catch both sqlalchemy.exc.OperationalError (wrapped asyncpg errors) and
    # OSError / ConnectionRefusedError for raw socket errors that asyncpg may not
    # wrap before SQLAlchemy intercepts them.
    from sqlalchemy.exc import OperationalError, SQLAlchemyError

    startup_timeout = 120.0
    retry_delay = 3.0
    deadline = time.monotonic() + startup_timeout
    last_exc: Exception | None = None

    while True:
        try:
            await _ensure_identity_schema()
            await _seed_admin()
            break
        except (OperationalError, OSError, ConnectionRefusedError) as exc:
            last_exc = exc
            if time.monotonic() >= deadline:
                logger.error(
                    "bhm-identity: PostgreSQL no disponible tras %.0f s — abortando: %s",
                    startup_timeout,
                    exc,
                )
                raise
            logger.warning(
                "bhm-identity: PostgreSQL aun no listo (%s: %s). Reintentando en %.1f s...",
                type(exc).__name__,
                exc,
                retry_delay,
            )
            await asyncio.sleep(retry_delay)

    logger.info("bhm-identity service ready on port 8080")
    yield
    logger.info("bhm-identity service stopping")


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="BHM Identity Service",
    version="1.0.0",
    description="Panel user management and credential verification for Broker Health Manager.",
    docs_url="/docs",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.allowed_hosts.split(","),
)

# Mount the identity router
from routers.identity import router as identity_router  # noqa: E402

app.include_router(identity_router, prefix="/api/v1")


@app.get("/health", tags=["health"])
async def health() -> dict:
    """Liveness probe for bhm-identity."""
    return {"status": "ok", "service": "bhm-identity"}
