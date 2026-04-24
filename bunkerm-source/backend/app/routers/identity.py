"""Identity router — BHM panel user management and credential verification.

Endpoints:
  POST /api/v1/identity/verify                       — verify credentials (used by Next.js BFF for login)
  GET  /api/v1/identity/users                        — list all panel users           (X-API-Key)
  POST /api/v1/identity/users                        — create new panel user          (X-API-Key)
  GET  /api/v1/identity/users/{user_id}              — get panel user by ID           (X-API-Key)
  DELETE /api/v1/identity/users/{user_id}            — delete panel user              (X-API-Key)
  PATCH /api/v1/identity/users/{user_id}/password    — reset user password            (X-API-Key)
  POST /api/v1/identity/users/{user_id}/change-password — change own password        (X-API-Key)
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Annotated, Optional
from uuid import uuid4

import bcrypt
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.identity_database import get_identity_db
from models.orm import BhmUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/identity", tags=["identity"])

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_VALID_ROLES = {"admin", "user"}


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class UserOut(BaseModel):
    id: str
    email: str
    first_name: str
    last_name: str
    role: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class VerifyRequest(BaseModel):
    email: str
    password: str = Field(max_length=128)


class CreateUserRequest(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=128)
    first_name: str = Field(min_length=1, max_length=128)
    last_name: str = Field(min_length=1, max_length=128)
    role: str = Field(default="user")


class ResetPasswordRequest(BaseModel):
    password: str = Field(min_length=8, max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------

async def _require_api_key(
    x_api_key: Annotated[str, Header(alias="X-API-Key")] = "",
) -> None:
    if x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/verify",
    response_model=UserOut,
    summary="Verify user credentials (used by bhm-frontend BFF for login)",
)
async def verify_credentials(
    body: VerifyRequest,
    db: AsyncSession = Depends(get_identity_db),
) -> UserOut:
    """Accepts email + password, returns the user record on success or 401 on failure.

    Intentionally uses the same error message for both 'user not found' and
    'wrong password' to prevent email enumeration attacks.
    """
    result = await db.execute(
        select(BhmUser).where(BhmUser.email == body.email.strip().lower())
    )
    user = result.scalars().first()

    if not user or not bcrypt.checkpw(body.password.encode(), user.password_hash.encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    return UserOut.model_validate(user)


@router.get(
    "/users",
    response_model=dict,
    summary="List all panel users",
    dependencies=[Depends(_require_api_key)],
)
async def list_users(db: AsyncSession = Depends(get_identity_db)) -> dict:
    result = await db.execute(select(BhmUser).order_by(BhmUser.created_at))
    users = result.scalars().all()
    return {"users": [UserOut.model_validate(u) for u in users]}


@router.post(
    "/users",
    response_model=dict,
    status_code=201,
    summary="Create a new panel user",
    dependencies=[Depends(_require_api_key)],
)
async def create_user(
    body: CreateUserRequest,
    db: AsyncSession = Depends(get_identity_db),
) -> dict:
    if not _EMAIL_RE.match(body.email):
        raise HTTPException(status_code=400, detail="Invalid email address")
    if body.role not in _VALID_ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")
    if re.search(r"[\x00-\x1F\x7F]", body.first_name) or re.search(r"[\x00-\x1F\x7F]", body.last_name):
        raise HTTPException(status_code=400, detail="Name contains invalid characters")

    existing = await db.execute(
        select(BhmUser).where(BhmUser.email == body.email.strip().lower())
    )
    if existing.scalars().first():
        raise HTTPException(status_code=409, detail="Email already registered")

    now = datetime.utcnow()
    user = BhmUser(
        id=str(uuid4()),
        email=body.email.strip().lower(),
        password_hash=bcrypt.hashpw(body.password.encode(), bcrypt.gensalt(10)).decode(),
        first_name=body.first_name,
        last_name=body.last_name,
        role=body.role,
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return {"user": UserOut.model_validate(user)}


@router.get(
    "/users/{user_id}",
    response_model=dict,
    summary="Get a specific panel user",
    dependencies=[Depends(_require_api_key)],
)
async def get_user(user_id: str, db: AsyncSession = Depends(get_identity_db)) -> dict:
    result = await db.execute(select(BhmUser).where(BhmUser.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"user": UserOut.model_validate(user)}


@router.delete(
    "/users/{user_id}",
    response_model=dict,
    summary="Delete a panel user",
    dependencies=[Depends(_require_api_key)],
)
async def delete_user(user_id: str, db: AsyncSession = Depends(get_identity_db)) -> dict:
    result = await db.execute(select(BhmUser).where(BhmUser.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.role == "admin":
        count_result = await db.execute(
            select(func.count()).select_from(BhmUser).where(BhmUser.role == "admin")
        )
        if count_result.scalar_one() <= 1:
            raise HTTPException(
                status_code=400, detail="Cannot delete the last admin account"
            )

    await db.delete(user)
    await db.commit()
    return {"message": "User deleted"}


@router.patch(
    "/users/{user_id}/password",
    response_model=dict,
    summary="Reset a user password (admin action)",
    dependencies=[Depends(_require_api_key)],
)
async def reset_user_password(
    user_id: str,
    body: ResetPasswordRequest,
    db: AsyncSession = Depends(get_identity_db),
) -> dict:
    result = await db.execute(select(BhmUser).where(BhmUser.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.password_hash = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt(10)).decode()
    user.updated_at = datetime.utcnow()
    await db.commit()
    return {"user": UserOut.model_validate(user)}


@router.post(
    "/users/{user_id}/change-password",
    response_model=dict,
    summary="Change own password (requires current password)",
    dependencies=[Depends(_require_api_key)],
)
async def change_password(
    user_id: str,
    body: ChangePasswordRequest,
    db: AsyncSession = Depends(get_identity_db),
) -> dict:
    result = await db.execute(select(BhmUser).where(BhmUser.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not bcrypt.checkpw(body.current_password.encode(), user.password_hash.encode()):
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    user.password_hash = bcrypt.hashpw(body.new_password.encode(), bcrypt.gensalt(10)).decode()
    user.updated_at = datetime.utcnow()
    await db.commit()
    return {"message": "Password changed successfully"}
