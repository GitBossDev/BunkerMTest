"""Stub de compatibilidad segura para el runtime legacy de DynSec.

La superficie activa vive en routers/dynsec.py y services/dynsec_service.py.
Este archivo se conserva solo para evitar que una ejecucion accidental del antiguo
microservicio vuelva a introducir escrituras directas sobre el broker.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

app = FastAPI(
    title="DynSec Legacy Compatibility API",
    version="0.0.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
)


def _legacy_dynsec_response(request: Request) -> JSONResponse:
    logger.warning(
        "Legacy DynSec runtime request rejected: %s %s debe migrarse al backend unificado",
        request.method,
        request.url,
    )
    return JSONResponse(
        status_code=status.HTTP_410_GONE,
        content={
            "status": "deprecated",
            "message": (
                "El microservicio legacy de DynSec fue retirado. "
                "Use la superficie unificada /api/v1/dynsec y el control-plane actual."
            ),
            "controlPlane": {
                "status": "legacy-disabled",
                "scope": "dynsec.legacy_runtime",
                "reason": "use-unified-dynsec-router",
            },
        },
    )


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def legacy_dynsec_surface(path: str, request: Request) -> JSONResponse:
    del path
    return _legacy_dynsec_response(request)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("dynsec.main:app", host="0.0.0.0", port=1000)