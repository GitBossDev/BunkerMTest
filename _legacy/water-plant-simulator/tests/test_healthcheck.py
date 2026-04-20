import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import healthcheck


def test_readiness_requires_mqtt_connection_and_fresh_heartbeat(tmp_path, monkeypatch):
    status_file = tmp_path / "status.json"
    heartbeat_file = tmp_path / "heartbeat.txt"
    status_file.write_text(
        json.dumps({"initialized": True, "running": True, "mqttConnected": False}),
        encoding="utf-8",
    )
    heartbeat_file.write_text(str(time.time()), encoding="utf-8")

    monkeypatch.setenv("SIMULATOR_STATUS_FILE", str(status_file))
    monkeypatch.setenv("SIMULATOR_HEARTBEAT_FILE", str(heartbeat_file))

    assert healthcheck.readiness(30.0) is False

    status_file.write_text(
        json.dumps({"initialized": True, "running": True, "mqttConnected": True}),
        encoding="utf-8",
    )

    assert healthcheck.readiness(30.0) is True


def test_liveness_requires_recent_heartbeat(tmp_path, monkeypatch):
    status_file = tmp_path / "status.json"
    heartbeat_file = tmp_path / "heartbeat.txt"
    status_file.write_text(json.dumps({"running": True}), encoding="utf-8")
    heartbeat_file.write_text(str(time.time() - 120), encoding="utf-8")

    monkeypatch.setenv("SIMULATOR_STATUS_FILE", str(status_file))
    monkeypatch.setenv("SIMULATOR_HEARTBEAT_FILE", str(heartbeat_file))

    assert healthcheck.liveness(30.0) is False

    heartbeat_file.write_text(str(time.time()), encoding="utf-8")

    assert healthcheck.liveness(30.0) is True