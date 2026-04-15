"""Tests de regresion para verificar que los bridges cloud no se publiquen."""


# ---------------------------------------------------------------------------
# AWS Bridge — POST /api/v1/aws-bridge
# ---------------------------------------------------------------------------

async def test_aws_bridge_requires_auth(raw_client):
    """AWS bridge queda fuera de la superficie activa del backend."""
    resp = await raw_client.post("/api/v1/aws-bridge")
    assert resp.status_code == 404


async def test_aws_bridge_missing_fields_returns_422(client):
    """Incluso autenticado, AWS bridge no debe exponerse como funcionalidad disponible."""
    resp = await client.post("/api/v1/aws-bridge", json={})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Azure Bridge — POST /api/v1/azure-bridge
# ---------------------------------------------------------------------------

async def test_azure_bridge_requires_auth(raw_client):
    """Azure bridge queda fuera de la superficie activa del backend."""
    resp = await raw_client.post("/api/v1/azure-bridge")
    assert resp.status_code == 404


async def test_azure_bridge_missing_fields_returns_422(client):
    """Incluso autenticado, Azure bridge no debe exponerse como funcionalidad disponible."""
    resp = await client.post("/api/v1/azure-bridge", json={})
    assert resp.status_code == 404
