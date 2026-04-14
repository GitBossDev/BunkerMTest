"""Integración real contra el stack Compose-first activo para validar aplicación al broker."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
import uuid
from typing import Any

import pytest
import requests


REAL_BROKER_ENV = "BHM_REAL_BROKER_TESTS"
BASE_URL_ENV = "BHM_REAL_STACK_BASE_URL"
API_KEY_ENV = "BHM_REAL_STACK_API_KEY"
ADMIN_EMAIL_ENV = "BHM_REAL_ADMIN_EMAIL"
ADMIN_PASSWORD_ENV = "BHM_REAL_ADMIN_PASSWORD"
PLATFORM_CONTAINER_ENV = "BHM_REAL_PLATFORM_CONTAINER"
BROKER_CONTAINER_ENV = "BHM_REAL_BROKER_CONTAINER"


def _require_real_broker_tests_enabled() -> None:
    if os.getenv(REAL_BROKER_ENV) != "1":
        pytest.skip(f"Set {REAL_BROKER_ENV}=1 to run live broker integration tests")


def _container_name(env_name: str, default: str) -> str:
    return os.getenv(env_name, default)


def _podman(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["podman", *args],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def _require_container_running(name: str) -> None:
    result = _podman("inspect", "-f", "{{.State.Running}}", name)
    if result.returncode != 0 or result.stdout.strip().lower() != "true":
        pytest.skip(f"Required container {name} is not running")


def _stack_api_key() -> str:
    api_key = os.getenv(API_KEY_ENV)
    if api_key:
        return api_key

    platform_container = _container_name(PLATFORM_CONTAINER_ENV, "bunkerm-platform")
    result = _podman("exec", platform_container, "printenv", "API_KEY")
    if result.returncode != 0:
        pytest.skip("Unable to read API_KEY from the running platform container")
    api_key = result.stdout.strip()
    if not api_key:
        pytest.skip("Running platform container does not expose API_KEY")
    return api_key


def _platform_env_var(name: str, default: str) -> str:
    platform_container = _container_name(PLATFORM_CONTAINER_ENV, "bunkerm-platform")
    result = _podman("exec", platform_container, "printenv", name)
    if result.returncode != 0:
        return default
    value = result.stdout.strip()
    return value or default


def _stack_admin_credentials() -> tuple[str, str]:
    email = os.getenv(ADMIN_EMAIL_ENV)
    password = os.getenv(ADMIN_PASSWORD_ENV)
    if email and password:
        return email, password

    platform_container = _container_name(PLATFORM_CONTAINER_ENV, "bunkerm-platform")
    email_result = _podman("exec", platform_container, "printenv", "ADMIN_INITIAL_EMAIL")
    password_result = _podman("exec", platform_container, "printenv", "ADMIN_INITIAL_PASSWORD")
    if email_result.returncode != 0 or password_result.returncode != 0:
        pytest.skip("Unable to read admin credentials from the running platform container")

    email = email_result.stdout.strip()
    password = password_result.stdout.strip()
    if not email or not password:
        pytest.skip("Running platform container does not expose admin credentials")
    return email, password


def _broker_dynsec_document() -> dict[str, Any]:
    broker_container = _container_name(BROKER_CONTAINER_ENV, "bunkerm-mosquitto")
    result = _podman("exec", broker_container, "cat", "/var/lib/mosquitto/dynamic-security.json")
    if result.returncode != 0:
        pytest.skip("Unable to read dynamic-security.json from the running broker container")
    return json.loads(result.stdout)


def _platform_file_content(path: str, allow_missing: bool = False) -> str | None:
    platform_container = _container_name(PLATFORM_CONTAINER_ENV, "bunkerm-platform")
    result = _podman("exec", platform_container, "cat", path)
    if result.returncode != 0:
        if allow_missing:
            return None
        pytest.skip(f"Unable to read {path} from the running platform container")
    return result.stdout


def _copy_content_to_platform_file(path: str, content: str) -> None:
    platform_container = _container_name(PLATFORM_CONTAINER_ENV, "bunkerm-platform")
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
        handle.write(content)
        temp_path = handle.name

    try:
        copy_result = _podman("cp", temp_path, f"{platform_container}:{path}")
        assert copy_result.returncode == 0, copy_result.stderr
        chmod_result = _podman("exec", platform_container, "chmod", "644", path)
        assert chmod_result.returncode == 0, chmod_result.stderr
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass


def _signal_platform_dynsec_reload(dynsec_path: str) -> None:
    platform_container = _container_name(PLATFORM_CONTAINER_ENV, "bunkerm-platform")
    marker_path = f"{os.path.dirname(dynsec_path)}/.dynsec-reload"
    result = _podman("exec", platform_container, "touch", marker_path)
    assert result.returncode == 0, result.stderr


def _remove_platform_file(path: str) -> None:
    platform_container = _container_name(PLATFORM_CONTAINER_ENV, "bunkerm-platform")
    result = _podman("exec", platform_container, "rm", "-f", path)
    assert result.returncode == 0, result.stderr


def _wait_until(assertion, timeout_seconds: float = 15.0, interval_seconds: float = 0.5) -> None:
    deadline = time.time() + timeout_seconds
    last_error: AssertionError | None = None
    while time.time() < deadline:
        try:
            assertion()
            return
        except AssertionError as exc:
            last_error = exc
            time.sleep(interval_seconds)
    if last_error is not None:
        raise last_error


def _proxy_url(base_url: str, path: str) -> str:
    return f"{base_url}/api/proxy/{path.lstrip('/')}"


def _login_session(base_url: str) -> requests.Session:
    admin_email, admin_password = _stack_admin_credentials()
    session = requests.Session()
    login_response = session.post(
        f"{base_url}/api/auth/login",
        json={"email": admin_email, "password": admin_password},
        timeout=10,
    )
    assert login_response.status_code == 200, login_response.text
    return session


def _restore_dynsec_document(session: requests.Session, base_url: str, original_doc: dict[str, Any]) -> None:
    dynsec_path = _platform_env_var("DYNSEC_PATH", "/var/lib/mosquitto/dynamic-security.json")
    _copy_content_to_platform_file(dynsec_path, json.dumps(original_doc, indent=2))
    _signal_platform_dynsec_reload(dynsec_path)
    _wait_until(lambda: _assert_dynsec_document_matches(original_doc), timeout_seconds=20.0)


def _assert_dynsec_document_matches(expected_doc: dict[str, Any]) -> None:
    assert _broker_dynsec_document() == expected_doc


@pytest.mark.integration
def test_real_stack_applies_client_lifecycle_to_broker():
    _require_real_broker_tests_enabled()

    platform_container = _container_name(PLATFORM_CONTAINER_ENV, "bunkerm-platform")
    broker_container = _container_name(BROKER_CONTAINER_ENV, "bunkerm-mosquitto")
    _require_container_running(platform_container)
    _require_container_running(broker_container)

    base_url = os.getenv(BASE_URL_ENV, "http://localhost:2000")
    username = f"phase3-it-{uuid.uuid4().hex[:8]}"
    session = _login_session(base_url)

    def _status_response() -> requests.Response:
        return session.get(
            _proxy_url(base_url, f"dynsec/clients/{username}/status"),
            timeout=10,
        )

    def assert_client_present(expected_disabled: bool) -> None:
        status_response = _status_response()
        assert status_response.status_code == 200
        status_body = status_response.json()
        assert status_body["status"] in {"applied", "drift"}
        assert status_body["desired"]["username"] == username
        assert status_body["observed"]["username"] == username
        assert status_body["observed"]["disabled"] is expected_disabled

        dynsec_doc = _broker_dynsec_document()
        client_entry = next((entry for entry in dynsec_doc.get("clients", []) if entry.get("username") == username), None)
        assert client_entry is not None
        assert bool(client_entry.get("disabled", False)) is expected_disabled

    def assert_client_absent() -> None:
        status_response = _status_response()
        assert status_response.status_code == 200
        status_body = status_response.json()
        assert status_body["desired"]["deleted"] is True
        assert status_body["observed"] is None

        dynsec_doc = _broker_dynsec_document()
        assert all(entry.get("username") != username for entry in dynsec_doc.get("clients", []))

    create_response = session.post(
        _proxy_url(base_url, "dynsec/clients"),
        json={"username": username, "password": "SecurePass123!"},
        timeout=10,
    )
    assert create_response.status_code == 201, create_response.text
    assert username in create_response.text

    try:
        _wait_until(lambda: assert_client_present(expected_disabled=False))

        disable_response = session.put(
            _proxy_url(base_url, f"dynsec/clients/{username}/disable"),
            timeout=10,
        )
        assert disable_response.status_code == 200, disable_response.text
        assert username in disable_response.text
        _wait_until(lambda: assert_client_present(expected_disabled=True))
    finally:
        delete_response = session.delete(
            _proxy_url(base_url, f"dynsec/clients/{username}"),
            timeout=10,
        )
        assert delete_response.status_code == 200, delete_response.text
        assert username in delete_response.text
        _wait_until(assert_client_absent)


@pytest.mark.integration
def test_real_stack_applies_dynsec_import_and_reset_to_broker():
    _require_real_broker_tests_enabled()

    platform_container = _container_name(PLATFORM_CONTAINER_ENV, "bunkerm-platform")
    broker_container = _container_name(BROKER_CONTAINER_ENV, "bunkerm-mosquitto")
    _require_container_running(platform_container)
    _require_container_running(broker_container)

    base_url = os.getenv(BASE_URL_ENV, "http://localhost:2000")
    session = _login_session(base_url)
    original_doc = _broker_dynsec_document()
    username = f"phase3-import-{uuid.uuid4().hex[:8]}"

    def assert_import_applied() -> None:
        status_response = session.get(
            _proxy_url(base_url, "config/dynsec-json/status"),
            timeout=10,
        )
        assert status_response.status_code == 200
        status_body = status_response.json()
        assert status_body["status"] in {"applied", "drift"}
        assert any(entry.get("username") == username for entry in status_body["desired"]["clients"])
        assert any(entry.get("username") == username for entry in status_body["observed"]["clients"])

        dynsec_doc = _broker_dynsec_document()
        assert any(entry.get("username") == username for entry in dynsec_doc.get("clients", []))

    def assert_reset_applied() -> None:
        status_response = session.get(
            _proxy_url(base_url, "config/dynsec-json/status"),
            timeout=10,
        )
        assert status_response.status_code == 200
        status_body = status_response.json()
        assert status_body["status"] in {"applied", "drift"}
        assert all(entry.get("username") != username for entry in status_body["observed"]["clients"])

        dynsec_doc = _broker_dynsec_document()
        assert all(entry.get("username") != username for entry in dynsec_doc.get("clients", []))

    import_payload = {
        "defaultACLAccess": {
            "publishClientSend": False,
            "publishClientReceive": True,
            "subscribe": False,
            "unsubscribe": True,
        },
        "clients": [{"username": username, "roles": [], "groups": []}],
        "groups": [],
        "roles": [],
    }

    try:
        import_response = session.post(
            _proxy_url(base_url, "config/import-dynsec-json"),
            files={"file": ("phase3-dynsec.json", json.dumps(import_payload), "application/json")},
            timeout=15,
        )
        assert import_response.status_code == 200, import_response.text
        assert import_response.json()["controlPlane"]["scope"] == "broker.dynsec_config"
        _wait_until(assert_import_applied, timeout_seconds=20.0)

        reset_response = session.post(
            _proxy_url(base_url, "config/reset-dynsec-json"),
            timeout=15,
        )
        assert reset_response.status_code == 200, reset_response.text
        assert reset_response.json()["controlPlane"]["scope"] == "broker.dynsec_config"
        _wait_until(assert_reset_applied, timeout_seconds=20.0)
    finally:
        _restore_dynsec_document(session, base_url, original_doc)


@pytest.mark.integration
def test_real_stack_syncs_passwd_users_to_dynsec():
    _require_real_broker_tests_enabled()

    platform_container = _container_name(PLATFORM_CONTAINER_ENV, "bunkerm-platform")
    broker_container = _container_name(BROKER_CONTAINER_ENV, "bunkerm-mosquitto")
    _require_container_running(platform_container)
    _require_container_running(broker_container)

    base_url = os.getenv(BASE_URL_ENV, "http://localhost:2000")
    session = _login_session(base_url)
    original_doc = _broker_dynsec_document()
    passwd_path = _platform_env_var("MOSQUITTO_PASSWD_PATH", "/etc/mosquitto/mosquitto_passwd")
    original_passwd = _platform_file_content(passwd_path, allow_missing=True)
    username = f"phase3-sync-{uuid.uuid4().hex[:8]}"

    existing_usernames = [entry.get("username") for entry in original_doc.get("clients", []) if entry.get("username")]
    passwd_lines = [f"{name}:$7$phase3hash{index}" for index, name in enumerate(existing_usernames + [username], start=1)]
    desired_passwd = "\n".join(passwd_lines) + "\n"

    def assert_sync_applied() -> None:
        status_response = session.get(
            _proxy_url(base_url, "config/dynsec-json/status"),
            timeout=10,
        )
        assert status_response.status_code == 200
        status_body = status_response.json()
        assert status_body["status"] in {"applied", "drift"}
        assert any(entry.get("username") == username for entry in status_body["desired"]["clients"])
        assert any(entry.get("username") == username for entry in status_body["observed"]["clients"])

        dynsec_doc = _broker_dynsec_document()
        assert any(entry.get("username") == username for entry in dynsec_doc.get("clients", []))

    try:
        _copy_content_to_platform_file(passwd_path, desired_passwd)

        sync_response = session.post(
            _proxy_url(base_url, "dynsec/sync-passwd-to-dynsec"),
            timeout=15,
        )
        assert sync_response.status_code == 200, sync_response.text
        sync_body = sync_response.json()
        assert sync_body["controlPlane"]["scope"] == "broker.dynsec_config"
        assert sync_body["count"] >= 1
        _wait_until(assert_sync_applied, timeout_seconds=20.0)
    finally:
        if original_passwd is None:
            _remove_platform_file(passwd_path)
        else:
            _copy_content_to_platform_file(passwd_path, original_passwd)
        _restore_dynsec_document(session, base_url, original_doc)