"""
Tests de regresion para los routers AWS Bridge y Azure Bridge.

Ambos routers solo exponen POST (creacion de configuracion de bridge con
certificados). Los tests verifican que:
1. Los routers estan montados y accesibles (no retornan 404)
2. Los endpoints requieren autenticacion (401/403 sin API key)
3. El esquema de request es validado (422 cuando faltan campos requeridos)

No se testea la logica de escritura de certificados porque requiere
acceso al filesystem de Mosquitto (/etc/mosquitto/certs).
"""
import pytest


# ---------------------------------------------------------------------------
# AWS Bridge — POST /api/v1/aws-bridge
# ---------------------------------------------------------------------------

async def test_aws_bridge_requires_auth(raw_client):
    """Sin autenticacion el endpoint retorna 401 o 403 (no 404)."""
    resp = await raw_client.post("/api/v1/aws-bridge")
    assert resp.status_code in (401, 403)


async def test_aws_bridge_missing_fields_returns_422(client):
    """
    Body vacio (sin aws_endpoint, client_id, topics, certificados):
    retorna 422 por validacion de schema antes de ejecutar logica de negocio.
    """
    resp = await client.post("/api/v1/aws-bridge", json={})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Azure Bridge — POST /api/v1/azure-bridge
# ---------------------------------------------------------------------------

async def test_azure_bridge_requires_auth(raw_client):
    """Sin autenticacion el endpoint retorna 401 o 403 (no 404)."""
    resp = await raw_client.post("/api/v1/azure-bridge")
    assert resp.status_code in (401, 403)


async def test_azure_bridge_missing_fields_returns_422(client):
    """
    Body vacio: retorna 422 por validacion de schema.
    """
    resp = await client.post("/api/v1/azure-bridge", json={})
    assert resp.status_code == 422
