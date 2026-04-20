import logging


async def test_invalid_api_key_is_denied_and_logged_for_admin_endpoints(raw_client, caplog):
    caplog.set_level(logging.WARNING, logger="core.auth")

    responses = [
        await raw_client.get("/api/v1/dynsec/clients", headers={"X-API-Key": "wrong-key"}),
        await raw_client.get("/api/v1/config/mosquitto-config", headers={"X-API-Key": "wrong-key"}),
        await raw_client.get("/api/v1/notifications/channels", headers={"X-API-Key": "wrong-key"}),
        await raw_client.get("/api/v1/reports/broker/daily", headers={"X-API-Key": "wrong-key"}),
    ]

    for response in responses:
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid API Key"

    warning_messages = [record.getMessage() for record in caplog.records if record.name == "core.auth"]
    assert any("clave API inválida" in message for message in warning_messages)