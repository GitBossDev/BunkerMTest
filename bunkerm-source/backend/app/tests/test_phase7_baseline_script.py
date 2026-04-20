from __future__ import annotations

import importlib.util
import pathlib
import sys


def _load_phase7_baseline_module():
    script_path = pathlib.Path(__file__).parents[4] / "scripts" / "dev-tools" / "phase7_baseline.py"
    spec = importlib.util.spec_from_file_location("phase7_baseline", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


phase7_baseline = _load_phase7_baseline_module()


def test_normalize_base_url_removes_trailing_slash():
    assert phase7_baseline.normalize_base_url("http://localhost:22000/") == "http://localhost:22000"


def test_percentile_interpolates_expected_value():
    value = phase7_baseline.percentile([10.0, 20.0, 30.0, 40.0], 0.95)
    assert round(value, 2) == 38.5


def test_summarize_durations_reports_mean_and_p95():
    summary = phase7_baseline.summarize_durations_ms([10.0, 20.0, 30.0, 40.0, 50.0])

    assert summary == {
        "minMs": 10.0,
        "maxMs": 50.0,
        "meanMs": 30.0,
        "medianMs": 30.0,
        "p95Ms": 48.0,
    }


def test_build_default_probes_includes_optional_reporting_and_security():
    probes = phase7_baseline.build_default_probes(
        reporting_path="/api/proxy/reports/broker/daily?days=7",
        security_path="/api/v1/security/ip-whitelist/status",
        reporting_auth="session",
        security_auth="api-key",
    )

    probe_names = [probe.name for probe in probes]
    assert probe_names == ["webUi", "authMe", "monitorHealth", "dynsecRoles", "reporting", "security"]
    assert probes[-2].auth_mode == "session"
    assert probes[-1].auth_mode == "api-key"
    assert probes[-1].allowed_statuses == (200,)


def test_load_api_key_reads_env_file(tmp_path):
    env_file = tmp_path / ".env.dev"
    env_file.write_text("FOO=bar\nAPI_KEY=test-key\n", encoding="utf-8")

    assert phase7_baseline.load_api_key(None, env_file) == "test-key"


def test_load_login_credentials_reads_env_file(tmp_path):
    env_file = tmp_path / ".env.dev"
    env_file.write_text("ADMIN_INITIAL_EMAIL=admin@bhm.local\nADMIN_INITIAL_PASSWORD=secret\n", encoding="utf-8")

    assert phase7_baseline.load_login_credentials(None, None, env_file) == ("admin@bhm.local", "secret")