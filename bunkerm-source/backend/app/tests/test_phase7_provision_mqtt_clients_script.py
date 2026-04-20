from __future__ import annotations

import importlib.util
import pathlib
import sys
from datetime import datetime, timezone


def _load_phase7_provision_module():
    script_path = pathlib.Path(__file__).parents[4] / "scripts" / "dev-tools" / "phase7_provision_mqtt_clients.py"
    spec = importlib.util.spec_from_file_location("phase7_provision_mqtt_clients", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


phase7_provision = _load_phase7_provision_module()


def test_parse_iso_timestamp_assumes_utc_for_naive_values():
    parsed = phase7_provision.parse_iso_timestamp("2026-04-20T09:00:46.514975")

    assert parsed == datetime(2026, 4, 20, 9, 0, 46, 514975, tzinfo=timezone.utc)


def test_summarize_returns_expected_values():
    summary = phase7_provision.summarize([10.0, 20.0, 30.0])

    assert summary == {
        "minMs": 10.0,
        "maxMs": 30.0,
        "meanMs": 20.0,
        "medianMs": 20.0,
    }


def test_urls_follow_host_published_dynsec_paths():
    base_url = "http://localhost:22000"

    assert phase7_provision.create_url(base_url) == "http://localhost:22000/api/dynsec/clients"
    assert phase7_provision.role_url(base_url, "1") == "http://localhost:22000/api/dynsec/clients/1/roles"
    assert phase7_provision.status_url(base_url, "1") == "http://localhost:22000/api/dynsec/clients/1/status"