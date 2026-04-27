"""
Diagnostic test for production second-save issue.
Captures the exact flow and generated conf to identify why broker becomes unreachable.
"""
import json
import re as _re
from pathlib import Path
from unittest.mock import patch
import pytest
from config.mosquitto_config import generate_mosquitto_conf, validate_listeners, parse_mosquitto_conf
from services.broker_desired_state_service import (
    merge_mosquitto_config_payload,
    normalize_mosquitto_config_payload,
    _normalize_listener_entries,
)


PRODUCTION_INITIAL_CONF = """\
# Mosquitto Broker Configuration
allow_anonymous false
plugin /usr/lib/mosquitto_dynamic_security.so
plugin_opt_config_file /var/lib/mosquitto/dynamic-security.json
persistence true
persistence_file mosquitto.db
persistence_location /var/lib/mosquitto/

listener 1900 0.0.0.0
protocol mqtt
max_connections 10000
per_listener_settings false

listener 1901 0.0.0.0
max_connections 16
per_listener_settings false

listener 9001 0.0.0.0
protocol websockets
max_connections 10000
per_listener_settings false
"""


def test_second_save_diagnostic_captures_config_generation(tmp_path, monkeypatch):
    """
    Simulate exact scenario:
    1. Parse production conf (with 0.0.0.0 binds)
    2. Merge with frontend request (with bind_address:"")
    3. Generate new conf
    4. Parse the generated conf back
    5. Merge again and generate (second iteration)
    6. Verify each listener appears exactly once in final conf
    """
    from config import mosquitto_config

    # ITERATION 1: Initial save
    # Write the production conf to a temp file and parse it
    conf_file = tmp_path / "mosquitto.conf"
    conf_file.write_text(PRODUCTION_INITIAL_CONF, encoding="utf-8")
    
    print("\n=== ITERATION 1 ===")
    print("1a. Parsing initial production conf...")
    monkeypatch.setattr(mosquitto_config, "MOSQUITTO_CONF_PATH", str(conf_file))
    observed_conf_1 = parse_mosquitto_conf()
    print(f"Observed listeners from initial conf: {json.dumps(observed_conf_1['listeners'], indent=2)}")

    # Frontend sends partial update (only 1900, frontend does NOT send 1901)
    requested_payload_1 = {
        "config": {
            "allow_anonymous": "false",
        },
        "listeners": [
            {"port": 1900, "bind_address": "", "per_listener_settings": False, "max_connections": 10000, "protocol": None},
        ],
        "max_inflight_messages": None,
        "max_queued_messages": None,
        "tls": None,
    }
    print(f"\n1b. Frontend requested payload: {json.dumps(requested_payload_1, indent=2)}")

    # Merge current (from disk) with requested (from frontend)
    print("\n1c. Merging current + requested...")
    merged_1 = merge_mosquitto_config_payload(observed_conf_1, requested_payload_1)
    print(f"Merged listeners: {json.dumps(merged_1['listeners'], indent=2)}")

    # Normalize the merged payload
    print("\n1d. Normalizing merged payload...")
    normalized_1 = normalize_mosquitto_config_payload(merged_1)
    print(f"Normalized listeners: {json.dumps(normalized_1['listeners'], indent=2)}")

    # Validate
    print("\n1e. Validating listeners...")
    is_valid, err_msg = validate_listeners(observed_conf_1.get("listeners", []), normalized_1["listeners"])
    assert is_valid, f"Validation failed in iteration 1: {err_msg}"
    print(f"Validation passed: is_valid={is_valid}, err_msg='{err_msg}'")

    # Generate conf (this is what gets written to disk)
    print("\n1f. Generating conf to write...")
    generated_conf_1 = generate_mosquitto_conf(
        normalized_1["config"],
        normalized_1["listeners"],
        normalized_1.get("max_inflight_messages"),
        normalized_1.get("max_queued_messages"),
    )
    print("Generated conf (first iteration):")
    print("---")
    print(generated_conf_1)
    print("---")

    # Verify no duplicates in generated conf
    listener_1900_count_1 = len(_re.findall(r"^listener 1900\b", generated_conf_1, _re.MULTILINE))
    listener_1901_count_1 = len(_re.findall(r"^listener 1901\b", generated_conf_1, _re.MULTILINE))
    listener_9001_count_1 = len(_re.findall(r"^listener 9001\b", generated_conf_1, _re.MULTILINE))
    print(f"\nListener counts in generated conf (iteration 1):")
    print(f"  1900: {listener_1900_count_1}")
    print(f"  1901: {listener_1901_count_1}")
    print(f"  9001: {listener_9001_count_1}")
    assert listener_1900_count_1 == 1, f"listener 1900 count: {listener_1900_count_1}"
    assert listener_1901_count_1 == 1, f"listener 1901 count: {listener_1901_count_1}"
    assert listener_9001_count_1 == 1, f"listener 9001 count: {listener_9001_count_1}"

    # ITERATION 2: Second save with different max_connections
    print("\n\n=== ITERATION 2 ===")
    print("2a. Parsing conf written by first iteration...")
    # Write the generated conf from iteration 1 back to the file
    conf_file.write_text(generated_conf_1, encoding="utf-8")
    # This is the critical step: the conf written by BHM in iteration 1
    # has normalized binds (empty string ""), so when parsed back, it should
    # produce listener identity keys that match the frontend request
    observed_conf_2 = parse_mosquitto_conf()
    print(f"Observed listeners from generated conf: {json.dumps(observed_conf_2['listeners'], indent=2)}")

    # Frontend sends another update with different max_connections
    requested_payload_2 = {
        "config": {
            "allow_anonymous": "false",
        },
        "listeners": [
            {"port": 1900, "bind_address": "", "per_listener_settings": False, "max_connections": 500, "protocol": None},
        ],
        "max_inflight_messages": None,
        "max_queued_messages": None,
        "tls": None,
    }
    print(f"\n2b. Frontend requested payload (iteration 2): {json.dumps(requested_payload_2, indent=2)}")

    # Merge current (from iteration 1's generated conf) with requested (from frontend)
    print("\n2c. Merging current + requested...")
    merged_2 = merge_mosquitto_config_payload(observed_conf_2, requested_payload_2)
    print(f"Merged listeners (iteration 2): {json.dumps(merged_2['listeners'], indent=2)}")

    # Normalize
    print("\n2d. Normalizing merged payload...")
    normalized_2 = normalize_mosquitto_config_payload(merged_2)
    print(f"Normalized listeners (iteration 2): {json.dumps(normalized_2['listeners'], indent=2)}")

    # Validate
    print("\n2e. Validating listeners (iteration 2)...")
    is_valid_2, err_msg_2 = validate_listeners(observed_conf_2.get("listeners", []), normalized_2["listeners"])
    assert is_valid_2, f"Validation failed in iteration 2: {err_msg_2}"
    print(f"Validation passed: is_valid={is_valid_2}, err_msg='{err_msg_2}'")

    # Generate conf for second iteration
    print("\n2f. Generating conf for second iteration...")
    generated_conf_2 = generate_mosquitto_conf(
        normalized_2["config"],
        normalized_2["listeners"],
        normalized_2.get("max_inflight_messages"),
        normalized_2.get("max_queued_messages"),
    )
    print("Generated conf (second iteration):")
    print("---")
    print(generated_conf_2)
    print("---")

    # Verify no duplicates in second generated conf
    listener_1900_count_2 = len(_re.findall(r"^listener 1900\b", generated_conf_2, _re.MULTILINE))
    listener_1901_count_2 = len(_re.findall(r"^listener 1901\b", generated_conf_2, _re.MULTILINE))
    listener_9001_count_2 = len(_re.findall(r"^listener 9001\b", generated_conf_2, _re.MULTILINE))
    print(f"\nListener counts in generated conf (iteration 2):")
    print(f"  1900: {listener_1900_count_2}")
    print(f"  1901: {listener_1901_count_2}")
    print(f"  9001: {listener_9001_count_2}")
    assert listener_1900_count_2 == 1, f"listener 1900 count: {listener_1900_count_2}"
    assert listener_1901_count_2 == 1, f"listener 1901 count: {listener_1901_count_2}"
    assert listener_9001_count_2 == 1, f"listener 9001 count: {listener_9001_count_2}"

    # Verify max_connections was updated
    assert "max_connections 500" in generated_conf_2, "Second iteration should have max_connections 500"
    print("\nSecond iteration successfully updated max_connections")

    print("\n✓ DIAGNOSTIC TEST PASSED")
    print("Both iterations produced valid configs with no duplicate listeners")
