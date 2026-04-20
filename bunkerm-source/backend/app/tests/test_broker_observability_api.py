from __future__ import annotations

import json

from fastapi.testclient import TestClient

import services.broker_observability_api as observability_api
import services.broker_observability_service as observability_service


def test_internal_broker_logs_endpoint_supports_incremental_offsets(monkeypatch, tmp_path):
    log_path = tmp_path / "mosquitto.log"
    log_path.write_text("line-1\nline-2\nline-3\n", encoding="utf-8")

    monkeypatch.setattr(observability_service.settings, "broker_log_path", str(log_path))
    monkeypatch.setattr(observability_service.settings, "broker_log_read_enabled", True)

    client = TestClient(observability_api.app)

    initial = client.get("/internal/broker/logs", params={"limit": 2})
    assert initial.status_code == 200
    initial_body = initial.json()
    assert initial_body["logs"] == ["line-2", "line-3"]
    assert initial_body["rewound"] is False

    with log_path.open("a", encoding="utf-8") as handle:
        handle.write("line-4\nline-5\n")

    incremental = client.get(
        "/internal/broker/logs",
        params={"limit": 10, "offset": initial_body["next_offset"]},
    )
    assert incremental.status_code == 200
    incremental_body = incremental.json()
    assert incremental_body["logs"] == ["line-4", "line-5"]
    assert incremental_body["offset"] == initial_body["next_offset"]
    assert incremental_body["rewound"] is False


def test_internal_broker_logs_source_status_reports_disabled_config(monkeypatch, tmp_path):
    log_path = tmp_path / "missing.log"
    monkeypatch.setattr(observability_service.settings, "broker_log_path", str(log_path))
    monkeypatch.setattr(observability_service.settings, "broker_log_read_enabled", False)

    client = TestClient(observability_api.app)

    resp = client.get("/internal/broker/logs/source-status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"]["enabled"] is False
    assert body["source"]["available"] is False
    assert body["source"]["lastError"] == "disabled_by_config"


def test_internal_broker_resource_stats_endpoint_returns_broker_owned_payload(monkeypatch, tmp_path):
    stats_path = tmp_path / "broker-resource-stats.json"
    stats_path.write_text(
        json.dumps(
            {
                "cpu_pct": 12.5,
                "memory_bytes": 10485760,
                "memory_limit_bytes": 20971520,
                "memory_pct": 50.0,
                "cpu_limit_cores": 1.5,
                "timestamp": "2026-04-20T10:30:00Z",
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(observability_service.settings, "broker_resource_stats_path", str(stats_path))
    monkeypatch.setattr(observability_service.settings, "broker_resource_stats_file_enabled", True)

    client = TestClient(observability_api.app)

    resp = client.get("/internal/broker/resource-stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["stats"]["cpu_pct"] == 12.5
    assert body["stats"]["memory_pct"] == 50.0
    assert body["source"]["available"] is True
    assert body["source"]["mode"] == "shared-file"