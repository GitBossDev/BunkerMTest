import pathlib

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import routers.aws_bridge as aws_bridge_router
import routers.azure_bridge as azure_bridge_router
from core.auth import get_api_key


@pytest.mark.asyncio
async def test_legacy_aws_bridge_router_returns_410_when_mounted():
    app = FastAPI()
    app.include_router(aws_bridge_router.router)
    app.dependency_overrides[get_api_key] = lambda: "test-api-key"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/aws-bridge")

    assert response.status_code == 410
    payload = response.json()
    assert payload["controlPlane"]["scope"] == "bridge.aws"
    assert payload["controlPlane"]["status"] == "legacy-disabled"


@pytest.mark.asyncio
async def test_legacy_azure_bridge_router_returns_410_when_mounted():
    app = FastAPI()
    app.include_router(azure_bridge_router.router)
    app.dependency_overrides[get_api_key] = lambda: "test-api-key"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/azure-bridge")

    assert response.status_code == 410
    payload = response.json()
    assert payload["controlPlane"]["scope"] == "bridge.azure"
    assert payload["controlPlane"]["status"] == "legacy-disabled"


@pytest.mark.asyncio
async def test_legacy_dynsec_runtime_returns_410_for_any_request():
    from dynsec.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/clients")

    assert response.status_code == 410
    payload = response.json()
    assert payload["controlPlane"]["scope"] == "dynsec.legacy_runtime"
    assert payload["controlPlane"]["status"] == "legacy-disabled"


def test_legacy_bridge_standalone_files_no_longer_embed_broker_writes():
    project_root = pathlib.Path(__file__).parents[1]
    files = [
        project_root / "aws-bridge" / "main.py",
        project_root / "azure-bridge" / "main.py",
    ]
    forbidden_markers = (
        "mosquitto_ctrl",
        "/var/lib/mosquitto/.reload",
        "dynamic-security.json",
        "MOSQUITTO_CONF_PATH",
        "MOSQUITTO_CERT_PATH",
    )

    for file_path in files:
        text = file_path.read_text(encoding="utf-8")
        assert all(marker not in text for marker in forbidden_markers), file_path