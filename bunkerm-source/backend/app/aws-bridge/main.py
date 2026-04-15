"""Stub de compatibilidad segura para el microservicio legacy AWS Bridge."""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

app = FastAPI(
    title="AWS Bridge Legacy Compatibility API",
    version="0.0.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
)


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def legacy_aws_bridge_surface(path: str, request: Request) -> JSONResponse:
    del path
    logger.warning(
        "Legacy AWS Bridge microservice request rejected: %s %s debe migrarse al control-plane",
        request.method,
        request.url,
    )
    return JSONResponse(
        status_code=status.HTTP_410_GONE,
        content={
            "status": "deprecated",
            "message": (
                "El microservicio legacy AWS Bridge fue retirado. "
                "Reintroduzca esta capacidad solo mediante desired state + reconciler."
            ),
            "controlPlane": {
                "status": "legacy-disabled",
                "scope": "bridge.aws",
                "reason": "reactivate-via-control-plane",
            },
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=1003)