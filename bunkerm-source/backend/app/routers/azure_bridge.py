"""Compatibilidad segura para la superficie legacy de Azure Bridge.

La funcionalidad cloud bridge quedó fuera de la superficie activa del producto.
Si se reactiva en el futuro, deberá reaparecer detrás del control-plane del broker
y no como escritura directa del proceso HTTP sobre el filesystem del broker.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Request, Security, status
from fastapi.responses import JSONResponse

from core.auth import get_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/azure-bridge", tags=["azure-bridge"])


def _legacy_bridge_response(request: Request) -> JSONResponse:
    logger.warning(
        "Legacy Azure Bridge request rejected: %s %s no pertenece a la superficie activa",
        request.method,
        request.url,
    )
    return JSONResponse(
        status_code=status.HTTP_410_GONE,
        content={
            "status": "deprecated",
            "message": (
                "Azure Bridge quedó retirado de la superficie funcional activa. "
                "Cualquier reactivación deberá implementarse vía desired state + reconciler."
            ),
            "controlPlane": {
                "status": "legacy-disabled",
                "scope": "bridge.azure",
                "reason": "reactivate-via-control-plane",
            },
        },
    )


@router.post("")
async def create_azure_bridge(
    request: Request,
    api_key: str = Security(get_api_key),
):
    del api_key
    return _legacy_bridge_response(request)