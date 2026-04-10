"""
Tests de regresion para el router Config Mosquitto (/api/v1/config).

parse_mosquitto_conf() lee el archivo de configuracion real del broker,
que no esta disponible en el entorno de test. Se mockea a nivel del modulo
del router para devolver una estructura minima valida.
"""
import pytest
import routers.config_mosquitto as config_router


# Respuesta minima valida de parse_mosquitto_conf()
SAMPLE_CONFIG = {
    "config": {"listener": "1900", "allow_anonymous": "false"},
    "listeners": [],
    "certs": [],
}


# ---------------------------------------------------------------------------
# GET /api/v1/config/mosquitto-config
# ---------------------------------------------------------------------------

async def test_get_config_returns_200(client, monkeypatch):
    """El endpoint retorna 200 con la configuracion parseada."""
    monkeypatch.setattr(config_router, "parse_mosquitto_conf", lambda: SAMPLE_CONFIG)
    resp = await client.get("/api/v1/config/mosquitto-config")
    assert resp.status_code == 200
    body = resp.json()
    # El router devuelve success=True cuando puede parsear la config
    assert body.get("success") is True


async def test_get_config_requires_auth(raw_client, monkeypatch):
    """Sin autenticacion retorna 401 o 403."""
    monkeypatch.setattr(config_router, "parse_mosquitto_conf", lambda: SAMPLE_CONFIG)
    resp = await raw_client.get("/api/v1/config/mosquitto-config")
    assert resp.status_code in (401, 403)


async def test_get_config_parse_failure(client, monkeypatch):
    """
    Si parse_mosquitto_conf devuelve config vacia, el router retorna
    success=False (degrada con gracia, no lanza 500).
    """
    empty_config = {"config": {}, "listeners": [], "certs": []}
    monkeypatch.setattr(config_router, "parse_mosquitto_conf", lambda: empty_config)
    resp = await client.get("/api/v1/config/mosquitto-config")
    assert resp.status_code == 200
    assert resp.json().get("success") is False
