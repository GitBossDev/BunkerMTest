from __future__ import annotations

from fastapi import APIRouter, Depends, Security
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_api_key
from core.database import get_db
from models.schemas import IPWhitelistPolicyUpsert
from services import ip_whitelist_service

router = APIRouter(prefix="/api/v1/security", tags=["security"])


@router.get("/ip-whitelist")
async def get_ip_whitelist(
    db: AsyncSession = Depends(get_db),
    api_key: str = Security(get_api_key),
):
    return await ip_whitelist_service.get_ip_whitelist_document(db)


@router.put("/ip-whitelist")
async def put_ip_whitelist(
    payload: IPWhitelistPolicyUpsert,
    db: AsyncSession = Depends(get_db),
    api_key: str = Security(get_api_key),
):
    await ip_whitelist_service.set_ip_whitelist_desired(
        db,
        payload.model_dump(exclude_none=True),
    )
    return await ip_whitelist_service.get_ip_whitelist_document(db)


@router.get("/ip-whitelist/status")
async def get_ip_whitelist_status(
    db: AsyncSession = Depends(get_db),
    api_key: str = Security(get_api_key),
):
    document = await ip_whitelist_service.get_ip_whitelist_document(db)
    return document["status"]