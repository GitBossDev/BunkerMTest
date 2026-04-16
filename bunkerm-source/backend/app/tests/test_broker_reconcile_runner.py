from types import SimpleNamespace

import pytest

from services import broker_desired_state_service as desired_state_svc
from services import broker_reconcile_runner


@pytest.mark.asyncio
async def test_reconcile_scope_dispatches_to_passwd_handler(monkeypatch):
    async def fake_reconcile(session):
        return SimpleNamespace(
            scope=desired_state_svc.MOSQUITTO_PASSWD_SCOPE,
            version=3,
            reconcile_status="applied",
            drift_detected=False,
            last_error=None,
        )

    monkeypatch.setattr(desired_state_svc, "reconcile_mosquitto_passwd", fake_reconcile)

    result = await broker_reconcile_runner.reconcile_scope(object(), desired_state_svc.MOSQUITTO_PASSWD_SCOPE)

    assert result == {
        "scope": desired_state_svc.MOSQUITTO_PASSWD_SCOPE,
        "version": 3,
        "status": "applied",
        "driftDetected": False,
        "lastError": None,
    }


@pytest.mark.asyncio
async def test_reconcile_scope_dispatches_to_broker_reload_handler(monkeypatch):
    async def fake_reconcile(session):
        return SimpleNamespace(
            scope=desired_state_svc.BROKER_RELOAD_SCOPE,
            version=2,
            reconcile_status="applied",
            drift_detected=False,
            last_error=None,
        )

    monkeypatch.setattr(desired_state_svc, "reconcile_broker_reload_signal", fake_reconcile)

    result = await broker_reconcile_runner.reconcile_scope(object(), desired_state_svc.BROKER_RELOAD_SCOPE)

    assert result == {
        "scope": desired_state_svc.BROKER_RELOAD_SCOPE,
        "version": 2,
        "status": "applied",
        "driftDetected": False,
        "lastError": None,
    }


@pytest.mark.asyncio
async def test_reconcile_scope_dispatches_dynamic_client_scope(monkeypatch):
    async def fake_reconcile(session, username, creation_password=None):
        assert username == "sensor-77"
        assert creation_password is None
        return SimpleNamespace(
            scope=f"{desired_state_svc.CLIENT_SCOPE_PREFIX}{username}",
            version=5,
            reconcile_status="drift",
            drift_detected=True,
            last_error=None,
        )

    monkeypatch.setattr(desired_state_svc, "reconcile_client", fake_reconcile)

    result = await broker_reconcile_runner.reconcile_scope(object(), f"{desired_state_svc.CLIENT_SCOPE_PREFIX}sensor-77")

    assert result == {
        "scope": f"{desired_state_svc.CLIENT_SCOPE_PREFIX}sensor-77",
        "version": 5,
        "status": "drift",
        "driftDetected": True,
        "lastError": None,
    }


@pytest.mark.asyncio
async def test_reconcile_client_consumes_staged_creation_secret_without_db_password(monkeypatch):
    state = SimpleNamespace(
        scope=f"{desired_state_svc.CLIENT_SCOPE_PREFIX}sensor-77",
        version=6,
        desired_payload_json="{}",
        applied_payload_json=None,
        observed_payload_json=None,
        reconcile_status="pending",
        drift_detected=False,
        last_error=None,
        desired_updated_at=None,
        reconciled_at=None,
        applied_at=None,
    )
    apply_calls: list[str | None] = []
    cleared_refs: list[tuple[str, int]] = []

    class FakeSession:
        async def commit(self):
            return None

        async def refresh(self, instance):
            return None

    async def fake_get_client_state(session, username):
        assert username == "sensor-77"
        return state

    monkeypatch.setattr(desired_state_svc, "get_client_state", fake_get_client_state)
    monkeypatch.setattr(
        desired_state_svc,
        "_load_json",
        lambda payload_json: {
            "username": "sensor-77",
            "textname": "",
            "groups": [],
            "roles": [],
            "disabled": False,
            "deleted": False,
        },
    )
    monkeypatch.setattr(desired_state_svc, "normalize_client_payload", lambda payload: payload)
    async def fake_get_staged_client_creation_secret(session, username, version):
        return "staged-pass-123"

    async def fake_clear_staged_client_creation_secret(session, username, version):
        cleared_refs.append((username, version))

    monkeypatch.setattr(
        desired_state_svc,
        "get_staged_client_creation_secret",
        fake_get_staged_client_creation_secret,
    )
    monkeypatch.setattr(
        desired_state_svc,
        "clear_staged_client_creation_secret",
        fake_clear_staged_client_creation_secret,
    )
    monkeypatch.setattr(
        desired_state_svc,
        "get_observed_client",
        lambda username: {
            "username": username,
            "textname": "",
            "groups": [],
            "roles": [],
            "disabled": False,
            "deleted": False,
        },
    )
    monkeypatch.setattr(
        desired_state_svc,
        "get_broker_reconciler",
        lambda: SimpleNamespace(
            apply_client_projection=lambda username, desired, creation_password=None: apply_calls.append(creation_password) or []
        ),
    )

    result = await desired_state_svc.reconcile_client(FakeSession(), "sensor-77")

    assert result.reconcile_status == "applied"
    assert apply_calls == ["staged-pass-123"]
    assert cleared_refs == [("sensor-77", 6)]


@pytest.mark.asyncio
async def test_reconcile_scope_rejects_unknown_scope():
    with pytest.raises(ValueError, match="Unsupported scope"):
        await broker_reconcile_runner.reconcile_scope(object(), "broker.unknown")