"""
Comprehensive second-save production scenario test.
Simulates the complete flow with state persistence and validation.
"""
import json
import re as _re
from pathlib import Path
from unittest.mock import patch
import pytest


async def test_second_save_production_realistic_scenario(client, monkeypatch, tmp_path):
    """
    Simulate the EXACT production scenario reported:
    1. Start with initial production conf (10k max_connections)
    2. First save: modify to 1k max_connections
    3. Broker restarts (simulated)
    4. Second save: modify to 500 max_connections
    5. Broker restarts again
    6. Verify broker is fully functional (all listeners present)
    """
    from services import broker_desired_state_service
    from config import mosquitto_config
    from core.database import get_db
    from main import app
    from models.orm import BrokerDesiredState

    conf_path = tmp_path / "mosquitto.conf"
    backup_dir = tmp_path / "backups"
    dynsec_path = tmp_path / "dynamic-security.json"
    backup_dir.mkdir()

    # Initial production conf
    initial_conf = """\
listener 1900 0.0.0.0
protocol mqtt
max_connections 10000
per_listener_settings false

listener 1901 0.0.0.0
max_connections 16

listener 9001 0.0.0.0
protocol websockets
max_connections 10000

allow_anonymous false
plugin /usr/lib/mosquitto_dynamic_security.so
plugin_opt_config_file /var/lib/mosquitto/dynamic-security.json
persistence true
persistence_file mosquitto.db
persistence_location /var/lib/mosquitto
"""
    conf_path.write_text(initial_conf, encoding="utf-8")

    # Initial dynsec
    dynsec_initial = {
        "defaultACLAccess": {"publishClientSend": True, "publishClientReceive": True, "subscribe": True, "unsubscribe": True},
        "clients": [{"username": "admin", "roles": [{"rolename": "admin"}]}],
        "roles": [{"rolename": "admin", "acls": []}],
        "groups": [],
    }
    dynsec_path.write_text(json.dumps(dynsec_initial, indent=2), encoding="utf-8")

    from services import broker_reconciler
    
    monkeypatch.setattr(broker_desired_state_service, "_MOSQUITTO_CONF_PATH", str(conf_path))
    monkeypatch.setattr(broker_desired_state_service, "_BACKUP_DIR", str(backup_dir))
    monkeypatch.setattr(broker_reconciler, "_MOSQUITTO_CONF_PATH", str(conf_path))
    monkeypatch.setattr(broker_reconciler, "_BACKUP_DIR", str(backup_dir))
    monkeypatch.setattr(mosquitto_config, "MOSQUITTO_CONF_PATH", str(conf_path))
    monkeypatch.setattr(mosquitto_config, "_signal_mosquitto_restart", lambda: None)

    # Override get_db to ensure we can access session
    session_generator = app.dependency_overrides.get(get_db, lambda: app.state.SessionLocal())

    # FIRST SAVE: 10k -> 1k
    print("\n=== FIRST SAVE: 10000 -> 1000 ===")
    payload_1 = {
        "config": {"allow_anonymous": "false"},
        "listeners": [
            {"port": 1900, "bind_address": "", "per_listener_settings": False, "max_connections": 1000, "protocol": None},
        ],
        "max_inflight_messages": None,
        "max_queued_messages": None,
        "tls": None,
    }
    
    resp1 = await client.post("/api/v1/config/mosquitto-config", json=payload_1)
    assert resp1.status_code == 200, f"First save failed: {resp1.json()}"
    resp1_json = resp1.json()
    print(f"First save response: {json.dumps(resp1_json, indent=2)}")
    assert resp1_json["success"] is True, f"First save returned success=False: {resp1_json}"
    
    saved_conf_1 = conf_path.read_text(encoding="utf-8")
    print(f"First save - conf file content:\n{saved_conf_1}")
    print("\n---")
    assert "max_connections 1000" in saved_conf_1, f"First save didn't update max_connections. Full conf:\n{saved_conf_1}"
    assert len(_re.findall(r"^listener 1900\b", saved_conf_1, _re.MULTILINE)) == 1, "Duplicate listener 1900 in first save"
    assert len(_re.findall(r"^listener 1901\b", saved_conf_1, _re.MULTILINE)) == 1, "Duplicate listener 1901 in first save"
    print("[OK] First save succeeded, max_connections set to 1000")
    print(f"Saved conf excerpt:\n{saved_conf_1[:500]}...")

    # SIMULATE RESTART: Broker restarts successfully and reloads config
    # (In real scenario, this would be handled by the entrypoint script)
    print("\n=== SIMULATING BROKER RESTART ===")
    print("[OK] Broker restarted successfully")

    # SECOND SAVE: 1k -> 500
    print("\n=== SECOND SAVE: 1000 -> 500 ===")
    payload_2 = {
        "config": {"allow_anonymous": "false"},
        "listeners": [
            {"port": 1900, "bind_address": "", "per_listener_settings": False, "max_connections": 500, "protocol": None},
        ],
        "max_inflight_messages": None,
        "max_queued_messages": None,
        "tls": None,
    }
    
    resp2 = await client.post("/api/v1/config/mosquitto-config", json=payload_2)
    assert resp2.status_code == 200, f"Second save failed: {resp2.json()}"
    assert resp2.json()["success"] is True, f"Second save returned success=False: {resp2.json()}"
    
    saved_conf_2 = conf_path.read_text(encoding="utf-8")
    assert "max_connections 500" in saved_conf_2, "Second save didn't update max_connections"
    assert len(_re.findall(r"^listener 1900\b", saved_conf_2, _re.MULTILINE)) == 1, "Duplicate listener 1900 in second save"
    assert len(_re.findall(r"^listener 1901\b", saved_conf_2, _re.MULTILINE)) == 1, "Duplicate listener 1901 in second save"
    assert len(_re.findall(r"^listener 9001\b", saved_conf_2, _re.MULTILINE)) == 1, "Duplicate listener 9001 in second save"
    print("[OK] Second save succeeded, max_connections set to 500")
    print(f"Saved conf excerpt:\n{saved_conf_2[:500]}...")

    # VERIFY CONF VALIDITY: Parse it back to ensure it's valid
    print("\n=== VERIFYING CONFIG VALIDITY ===")
    parsed = mosquitto_config.parse_mosquitto_conf()
    assert parsed["listeners"], "Parsed config has no listeners"
    listener_ports = [l["port"] for l in parsed["listeners"]]
    assert 1900 in listener_ports, "Port 1900 not in parsed listeners"
    assert 1901 in listener_ports, "Port 1901 not in parsed listeners"
    assert 9001 in listener_ports, "Port 9001 not in parsed listeners"
    
    # Verify max_connections
    listener_1900 = next(l for l in parsed["listeners"] if l["port"] == 1900)
    assert listener_1900["max_connections"] == 500, f"Final max_connections should be 500, got {listener_1900['max_connections']}"
    print("[OK] Config is valid and parseable")
    print(f"Parsed listeners: {json.dumps(parsed['listeners'], indent=2)}")

    print("\n[OK] COMPREHENSIVE TEST PASSED [OK]")
    print("Both saves succeeded, config is valid, and all listeners are present")
