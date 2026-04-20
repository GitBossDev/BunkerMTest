import services.ip_whitelist_service as whitelist_svc


async def test_ip_whitelist_endpoints_require_auth(raw_client):
    get_resp = await raw_client.get("/api/v1/security/ip-whitelist")
    status_resp = await raw_client.get("/api/v1/security/ip-whitelist/status")

    assert get_resp.status_code in (401, 403)
    assert status_resp.status_code in (401, 403)


async def test_ip_whitelist_roundtrip_and_status(client):
    whitelist_svc.clear_ip_whitelist_runtime_state()

    resp = await client.put(
        "/api/v1/security/ip-whitelist",
        json={
            "mode": "enforce",
            "trustedProxies": ["10.0.0.0/24"],
            "defaultAction": {"api_admin": "deny", "mqtt_clients": "allow"},
            "entries": [
                {
                    "id": "local-admin",
                    "cidr": "127.0.0.1/32",
                    "scope": "api_admin",
                    "description": "Acceso local",
                    "enabled": True,
                },
                {
                    "id": "plant-gateway",
                    "cidr": "198.51.100.10/32",
                    "scope": "mqtt_clients",
                    "description": "Gateway MQTT",
                    "enabled": True,
                },
            ],
            "lastUpdatedBy": {"type": "human", "id": "admin@bhm.local"},
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["policy"]["mode"] == "enforce"
    assert body["policy"]["version"] == 1
    assert body["policy"]["defaultAction"]["api_admin"] == "deny"
    assert body["policy"]["lastUpdatedBy"]["id"] == "admin@bhm.local"
    assert body["status"]["apiAdmin"]["configuredEntries"] == 1
    assert body["status"]["mqttClients"]["configuredEntries"] == 1
    assert body["status"]["mqttClients"]["desiredVersion"] == 1

    status_resp = await client.get("/api/v1/security/ip-whitelist/status")
    assert status_resp.status_code == 200
    status_body = status_resp.json()
    assert status_body["apiAdmin"]["mode"] == "enforce"
    assert status_body["mqttClients"]["observedVersion"] == 1


async def test_ip_whitelist_enforce_blocks_disallowed_admin_requests(client):
    whitelist_svc.prime_ip_whitelist_cache(
        {
            "mode": "enforce",
            "trustedProxies": [],
            "defaultAction": {"api_admin": "deny", "mqtt_clients": "allow"},
            "entries": [
                {
                    "id": "remote-office",
                    "cidr": "198.51.100.0/24",
                    "scope": "api_admin",
                    "description": "Oficina remota",
                    "enabled": True,
                }
            ],
            "lastUpdatedBy": {"type": "human", "id": "admin@bhm.local"},
            "version": 5,
            "lastUpdatedAt": "2026-04-20T18:00:00Z",
        }
    )

    resp = await client.get("/api/v1/reports/broker/daily", params={"days": 7})

    assert resp.status_code == 403
    assert resp.json()["detail"] == "IP not allowed by whitelist policy"


async def test_ip_whitelist_does_not_block_public_health(raw_client):
    whitelist_svc.prime_ip_whitelist_cache(
        {
            "mode": "enforce",
            "trustedProxies": [],
            "defaultAction": {"api_admin": "deny", "mqtt_clients": "deny"},
            "entries": [],
            "lastUpdatedBy": {"type": "human", "id": "admin@bhm.local"},
            "version": 2,
            "lastUpdatedAt": "2026-04-20T18:05:00Z",
        }
    )

    resp = await raw_client.get("/api/v1/monitor/health")

    assert resp.status_code == 200