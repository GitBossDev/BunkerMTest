"""Servicios transicionales de control-plane para broker desired state."""
from __future__ import annotations

import asyncio
import json
import os
import base64
import hashlib
import copy
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, List

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.ext.asyncio import AsyncSession

from config.mosquitto_config import (
    DEFAULT_CONFIG,
    _generate_tls_listener_block,
    generate_mosquitto_conf,
    parse_mosquitto_conf,
)
from config.dynsec_config import DEFAULT_CONFIG as DEFAULT_DYNSEC_CONFIG, validate_dynsec_json
from core.config import settings
from core.database import AsyncSessionLocal
from models.orm import BrokerDesiredState, BrokerDesiredStateAudit
from services import broker_observability_client
from services import broker_reconciler as broker_reconciler_svc
from services import dynsec_service

MOSQUITTO_CONFIG_SCOPE = "broker.mosquitto_config"
MOSQUITTO_PASSWD_SCOPE = "broker.mosquitto_passwd"
TLS_CERT_STORE_SCOPE = "broker.tls_certs"
DYNSEC_CONFIG_SCOPE = "broker.dynsec_config"
BROKER_RELOAD_SCOPE = "broker.reload_signal"
BRIDGE_BUNDLE_SCOPE = "broker.bridge_bundle"
DEFAULT_ACL_SCOPE = "dynsec.default_acl"
CLIENT_SCOPE_PREFIX = "dynsec.client."
ROLE_SCOPE_PREFIX = "dynsec.role."
GROUP_SCOPE_PREFIX = "dynsec.group."
DEFAULT_ACL_KEYS = (
    "publishClientSend",
    "publishClientReceive",
    "subscribe",
    "unsubscribe",
)
_MOSQUITTO_CONF_PATH: str = settings.mosquitto_conf_path
_BACKUP_DIR: str = settings.mosquitto_conf_backup_dir
_MOSQUITTO_PASSWD_PATH: str = settings.mosquitto_passwd_path
_CERTS_DIR: str = settings.mosquitto_certs_dir
_BROKER_RECONCILE_SECRET_DIR: str = settings.broker_reconcile_secret_dir
_ALLOWED_CERT_EXTENSIONS = {".pem", ".crt", ".cer", ".key"}
_MOSQUITTO_PASSWD_LINE_PATTERN = re.compile(r"^[^:]+:\$\d+\$[^:]+$")
_broker_reconciler = broker_reconciler_svc.BrokerReconciler()
_DESIRED_AUDIT_EVENT_KIND = "desired_change"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def normalize_default_acl(payload: Dict[str, Any] | None) -> Dict[str, bool]:
    source = payload or {}
    return {key: bool(source.get(key, True)) for key in DEFAULT_ACL_KEYS}


def normalize_broker_reload_payload(payload: Dict[str, Any] | None) -> Dict[str, Any]:
    source = payload or {}
    requested_at = source.get("requestedAt")
    reason = str(source.get("reason") or "manual")
    requested_by = str(source.get("requestedBy") or "api")
    if not isinstance(requested_at, str) or not requested_at.strip():
        requested_at = datetime.now(timezone.utc).isoformat()
    return {
        "requestedAt": requested_at,
        "reason": reason,
        "requestedBy": requested_by,
    }


def _dump_payload(payload: Dict[str, bool]) -> str:
    return json.dumps(payload, sort_keys=True)


def _load_payload(payload_json: str | None) -> Dict[str, bool] | None:
    if not payload_json:
        return None
    return normalize_default_acl(json.loads(payload_json))


def _dump_json(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True)


def _load_json(payload_json: str | None) -> Dict[str, Any] | None:
    if not payload_json:
        return None
    return json.loads(payload_json)


def normalize_dynsec_config_payload(payload: Dict[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("DynSec desired state requires a config object")
    validated = validate_dynsec_json(copy.deepcopy(payload))
    return json.loads(json.dumps(validated, sort_keys=True))


def normalize_bridge_bundle_payload(payload: Dict[str, Any] | None) -> Dict[str, Any]:
    source = payload or {}
    bridges: List[Dict[str, Any]] = []
    for entry in source.get("bridges") or []:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        bridges.append(
            {
                "name": name,
                "provider": str(entry.get("provider") or "generic").strip().lower(),
                "enabled": bool(entry.get("enabled", False)),
                "topics": [str(topic) for topic in entry.get("topics") or [] if str(topic).strip()],
                "certRefs": [str(ref) for ref in entry.get("certRefs") or [] if str(ref).strip()],
            }
        )

    return {
        "status": str(source.get("status") or "deferred"),
        "requestedBy": str(source.get("requestedBy") or "api"),
        "notes": str(source.get("notes") or "legacy bridge surface removed from active product"),
        "bridges": bridges,
    }


def get_broker_reconciler() -> broker_reconciler_svc.BrokerReconciler:
    return _broker_reconciler


async def _commit_desired_state_change(
    session: AsyncSession,
    state: BrokerDesiredState,
) -> BrokerDesiredState:
    session.add(
        BrokerDesiredStateAudit(
            scope=state.scope,
            version=state.version,
            event_kind=_DESIRED_AUDIT_EVENT_KIND,
            desired_payload_json=state.desired_payload_json,
            applied_payload_json=state.applied_payload_json,
            observed_payload_json=state.observed_payload_json,
            reconcile_status=state.reconcile_status,
            drift_detected=state.drift_detected,
            error_message=state.last_error,
            recorded_at=_utcnow(),
        )
    )
    await session.commit()
    await session.refresh(state)
    return state


def is_daemon_reconcile_mode() -> bool:
    return settings.broker_reconcile_mode.strip().lower() == "daemon"


async def wait_for_scope_settlement(
    scope: str,
    minimum_version: int,
    timeout_seconds: float | None = None,
    poll_interval_seconds: float | None = None,
) -> BrokerDesiredState | None:
    timeout = timeout_seconds if timeout_seconds is not None else settings.broker_reconcile_wait_timeout_seconds
    poll_interval = (
        poll_interval_seconds
        if poll_interval_seconds is not None
        else settings.broker_reconcile_poll_interval_seconds
    )
    deadline = time.monotonic() + max(timeout, 0.0)
    latest_state: BrokerDesiredState | None = None

    while True:
        async with AsyncSessionLocal() as wait_session:
            latest_state = await wait_session.get(BrokerDesiredState, scope)

        if (
            latest_state is not None
            and latest_state.version >= minimum_version
            and latest_state.reconcile_status != "pending"
        ):
            return latest_state

        if time.monotonic() >= deadline:
            return latest_state

        await asyncio.sleep(max(poll_interval, 0.05))


async def reconcile_or_wait(
    state: BrokerDesiredState,
    reconcile_action: Callable[..., Awaitable[BrokerDesiredState]],
    session: AsyncSession,
    *args: Any,
    force_inline: bool = False,
    **kwargs: Any,
) -> BrokerDesiredState:
    if force_inline or not is_daemon_reconcile_mode():
        return await reconcile_action(session, *args, **kwargs)

    settled_state = await wait_for_scope_settlement(state.scope, state.version)
    return settled_state or state


def _reconcile_secret_cipher() -> Fernet:
    key_material = f"{settings.auth_secret}:{settings.jwt_secret}".encode("utf-8")
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(key_material).digest()))


def _client_creation_secret_path(username: str, version: int) -> str:
    secret_key = hashlib.sha256(f"{_client_scope(username)}:{version}".encode("utf-8")).hexdigest()
    return os.path.join(_BROKER_RECONCILE_SECRET_DIR, f"{secret_key}.token")


def _safe_remove_file(path: str) -> None:
    try:
        os.remove(path)
    except FileNotFoundError:
        return


def _load_staged_client_creation_secret_payload(secret_path: str) -> Dict[str, Any] | None:
    try:
        with open(secret_path, "rb") as handle:
            encrypted_payload = handle.read()
    except FileNotFoundError:
        return None
    except OSError:
        return None

    try:
        decrypted_payload = _reconcile_secret_cipher().decrypt(encrypted_payload)
        payload = json.loads(decrypted_payload.decode("utf-8"))
    except (InvalidToken, json.JSONDecodeError, UnicodeDecodeError):
        _safe_remove_file(secret_path)
        return None

    expires_at_raw = payload.get("expiresAt")
    try:
        expires_at = datetime.fromisoformat(expires_at_raw) if isinstance(expires_at_raw, str) else None
    except ValueError:
        expires_at = None

    if expires_at is None:
        _safe_remove_file(secret_path)
        return None

    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at <= datetime.now(timezone.utc):
        _safe_remove_file(secret_path)
        return None

    return payload


def cleanup_staged_client_creation_secrets() -> None:
    if not os.path.isdir(_BROKER_RECONCILE_SECRET_DIR):
        return

    for entry_name in os.listdir(_BROKER_RECONCILE_SECRET_DIR):
        if not entry_name.endswith(".token"):
            continue
        _load_staged_client_creation_secret_payload(os.path.join(_BROKER_RECONCILE_SECRET_DIR, entry_name))


def stage_client_creation_secret(username: str, version: int, creation_password: str) -> None:
    if not creation_password:
        raise ValueError("Client creation password is required")

    os.makedirs(_BROKER_RECONCILE_SECRET_DIR, exist_ok=True)
    cleanup_staged_client_creation_secrets()

    expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=max(settings.broker_reconcile_secret_ttl_seconds, 5.0)
    )
    payload = {
        "username": username,
        "version": version,
        "password": creation_password,
        "expiresAt": expires_at.isoformat(),
    }
    encrypted_payload = _reconcile_secret_cipher().encrypt(_dump_json(payload).encode("utf-8"))
    secret_path = _client_creation_secret_path(username, version)
    temp_path = f"{secret_path}.tmp"

    with open(temp_path, "wb") as handle:
        handle.write(encrypted_payload)

    try:
        os.chmod(temp_path, 0o600)
    except OSError:
        pass

    os.replace(temp_path, secret_path)

    try:
        os.chmod(secret_path, 0o600)
    except OSError:
        pass


def get_staged_client_creation_secret(username: str, version: int) -> str | None:
    cleanup_staged_client_creation_secrets()
    payload = _load_staged_client_creation_secret_payload(_client_creation_secret_path(username, version))
    if payload is None:
        return None
    if payload.get("username") != username or int(payload.get("version", -1)) != version:
        return None
    password = payload.get("password")
    return password if isinstance(password, str) and password else None


def clear_staged_client_creation_secret(username: str, version: int) -> None:
    _safe_remove_file(_client_creation_secret_path(username, version))


def _client_scope(username: str) -> str:
    return f"{CLIENT_SCOPE_PREFIX}{username}"


def _role_scope(role_name: str) -> str:
    return f"{ROLE_SCOPE_PREFIX}{role_name}"


def _group_scope(group_name: str) -> str:
    return f"{GROUP_SCOPE_PREFIX}{group_name}"


def _normalize_listener_entries(raw_listeners: List[Any]) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for listener in raw_listeners:
        if not isinstance(listener, dict):
            continue
        port = listener.get("port")
        if port is None:
            continue
        entries.append(
            {
                "port": int(port),
                "bind_address": str(listener.get("bind_address") or ""),
                "per_listener_settings": bool(listener.get("per_listener_settings", False)),
                "max_connections": int(listener.get("max_connections", 10000)),
                "protocol": listener.get("protocol") or None,
            }
        )
    return sorted(entries, key=lambda item: (item["port"], item["bind_address"], item["protocol"] or ""))


def _normalize_tls_payload(raw_tls: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if not raw_tls or not raw_tls.get("enabled"):
        return None
    return {
        "enabled": True,
        "port": int(raw_tls.get("port", 8883)),
        "cafile": raw_tls.get("cafile") or None,
        "certfile": raw_tls.get("certfile") or None,
        "keyfile": raw_tls.get("keyfile") or None,
        "require_certificate": bool(raw_tls.get("require_certificate", False)),
        "tls_version": raw_tls.get("tls_version") or None,
    }


def _read_mosquitto_content() -> str:
    if not os.path.exists(_MOSQUITTO_CONF_PATH):
        return ""
    with open(_MOSQUITTO_CONF_PATH, "r", encoding="utf-8") as handle:
        return handle.read()


def _extract_tls_from_content(content: str) -> Dict[str, Any] | None:
    if not content:
        return None

    tls_data: Dict[str, Any] | None = None
    current_listener_port: int | None = None
    current_listener_tls: Dict[str, Any] | None = None

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("listener "):
            if current_listener_tls and (
                current_listener_tls.get("cafile")
                or current_listener_tls.get("certfile")
                or current_listener_tls.get("keyfile")
            ):
                tls_data = current_listener_tls
                break
            parts = line.split()
            current_listener_port = int(parts[1]) if len(parts) > 1 else None
            current_listener_tls = {
                "enabled": True,
                "port": current_listener_port or 8883,
                "cafile": None,
                "certfile": None,
                "keyfile": None,
                "require_certificate": False,
                "tls_version": None,
            }
            continue

        if current_listener_tls is None or " " not in line:
            continue

        key, value = line.split(" ", 1)
        if key in {"cafile", "certfile", "keyfile", "tls_version"}:
            current_listener_tls[key] = value.strip()
        elif key == "require_certificate":
            current_listener_tls["require_certificate"] = value.strip().lower() == "true"

    if tls_data is None and current_listener_tls and (
        current_listener_tls.get("cafile")
        or current_listener_tls.get("certfile")
        or current_listener_tls.get("keyfile")
    ):
        tls_data = current_listener_tls

    return _normalize_tls_payload(tls_data)


def normalize_mosquitto_config_payload(payload: Dict[str, Any] | None) -> Dict[str, Any]:
    source = payload or {}
    config_data = source.get("config")
    if not isinstance(config_data, dict):
        raise ValueError("Mosquitto desired state requires a config object")

    normalized_config = {key: config_data[key] for key in sorted(config_data.keys())}
    listeners = _normalize_listener_entries(source.get("listeners", []))
    tls = _normalize_tls_payload(source.get("tls"))
    max_inflight = source.get("max_inflight_messages")
    max_queued = source.get("max_queued_messages")

    rendered_content = generate_mosquitto_conf(
        normalized_config,
        listeners,
        max_inflight_messages=int(max_inflight) if max_inflight is not None else None,
        max_queued_messages=int(max_queued) if max_queued is not None else None,
    )
    if tls:
        rendered_content += _generate_tls_listener_block(type("TLSPayload", (), tls))

    return {
        "config": normalized_config,
        "listeners": listeners,
        "max_inflight_messages": int(max_inflight) if max_inflight is not None else None,
        "max_queued_messages": int(max_queued) if max_queued is not None else None,
        "tls": tls,
        "content": rendered_content,
    }


def _normalize_mosquitto_observed_payload(parsed: Dict[str, Any], content: str) -> Dict[str, Any]:
    return {
        "config": parsed.get("config", {}),
        "listeners": _normalize_listener_entries(parsed.get("listeners", [])),
        "max_inflight_messages": parsed.get("max_inflight_messages"),
        "max_queued_messages": parsed.get("max_queued_messages"),
        "tls": _extract_tls_from_content(content),
        "content": content,
    }


def get_observed_mosquitto_config() -> Dict[str, Any]:
    if os.path.isfile(_MOSQUITTO_CONF_PATH):
        content = _read_mosquitto_content()
        parsed = parse_mosquitto_conf() if content else {"config": {}, "listeners": []}
        return _normalize_mosquitto_observed_payload(parsed, content)

    try:
        parsed = parse_mosquitto_conf()
        if parsed.get("config"):
            return _normalize_mosquitto_observed_payload(parsed, _read_mosquitto_content())
    except Exception:
        pass

    payload = broker_observability_client.fetch_broker_mosquitto_config_sync()
    return normalize_mosquitto_config_payload(
        {
            "config": payload.get("config", {}),
            "listeners": payload.get("listeners", []),
            "max_inflight_messages": payload.get("max_inflight_messages"),
            "max_queued_messages": payload.get("max_queued_messages"),
            "tls": payload.get("tls"),
        }
    )


async def get_mosquitto_config_state(session: AsyncSession) -> BrokerDesiredState | None:
    return await session.get(BrokerDesiredState, MOSQUITTO_CONFIG_SCOPE)


async def get_broker_reload_state(session: AsyncSession) -> BrokerDesiredState | None:
    return await session.get(BrokerDesiredState, BROKER_RELOAD_SCOPE)


async def get_bridge_bundle_state(session: AsyncSession) -> BrokerDesiredState | None:
    return await session.get(BrokerDesiredState, BRIDGE_BUNDLE_SCOPE)


async def set_broker_reload_desired(
    session: AsyncSession,
    payload: Dict[str, Any] | None = None,
) -> BrokerDesiredState:
    desired = normalize_broker_reload_payload(payload)
    state = await get_broker_reload_state(session)
    now = _utcnow()

    if state is None:
        state = BrokerDesiredState(
            scope=BROKER_RELOAD_SCOPE,
            version=1,
            desired_payload_json=_dump_json(desired),
            reconcile_status="pending",
            drift_detected=False,
            desired_updated_at=now,
        )
        session.add(state)
    else:
        state.version += 1
        state.desired_payload_json = _dump_json(desired)
        state.reconcile_status = "pending"
        state.drift_detected = False
        state.last_error = None
        state.desired_updated_at = now

    return await _commit_desired_state_change(session, state)


async def reconcile_broker_reload_signal(session: AsyncSession) -> BrokerDesiredState:
    state = await get_broker_reload_state(session)
    if state is None:
        raise ValueError("No desired state found for broker reload signal")

    desired = normalize_broker_reload_payload(_load_json(state.desired_payload_json))
    errors = get_broker_reconciler().signal_mosquitto_reload()
    now = _utcnow()
    observed = None if errors else {**desired, "signaled": True}

    state.observed_payload_json = _dump_json(observed or {})
    state.reconciled_at = now

    if errors:
        state.reconcile_status = "error"
        state.drift_detected = False
        state.last_error = "; ".join(errors)
    else:
        state.applied_payload_json = _dump_json(desired)
        state.applied_at = now
        state.drift_detected = False
        state.reconcile_status = "applied"
        state.last_error = None

    return await _commit_desired_state_change(session, state)


async def get_broker_reload_status(session: AsyncSession) -> Dict[str, Any]:
    state = await get_broker_reload_state(session)
    if state is None:
        return {
            "scope": BROKER_RELOAD_SCOPE,
            "version": 0,
            "status": "unmanaged",
            "desired": None,
            "applied": None,
            "observed": None,
            "driftDetected": False,
            "lastError": None,
            "desiredUpdatedAt": None,
            "reconciledAt": None,
            "appliedAt": None,
        }

    desired = normalize_broker_reload_payload(_load_json(state.desired_payload_json))
    applied_raw = _load_json(state.applied_payload_json)
    observed_raw = _load_json(state.observed_payload_json)
    applied = normalize_broker_reload_payload(applied_raw) if applied_raw else None
    observed = observed_raw or None

    return {
        "scope": state.scope,
        "version": state.version,
        "status": state.reconcile_status,
        "desired": desired,
        "applied": applied,
        "observed": observed,
        "driftDetected": state.drift_detected,
        "lastError": state.last_error,
        "desiredUpdatedAt": state.desired_updated_at.isoformat() if state.desired_updated_at else None,
        "reconciledAt": state.reconciled_at.isoformat() if state.reconciled_at else None,
        "appliedAt": state.applied_at.isoformat() if state.applied_at else None,
    }


async def set_bridge_bundle_desired(
    session: AsyncSession,
    payload: Dict[str, Any] | None = None,
) -> BrokerDesiredState:
    desired = normalize_bridge_bundle_payload(payload)
    state = await get_bridge_bundle_state(session)
    now = _utcnow()

    if state is None:
        state = BrokerDesiredState(
            scope=BRIDGE_BUNDLE_SCOPE,
            version=1,
            desired_payload_json=_dump_json(desired),
            reconcile_status="deferred",
            drift_detected=False,
            desired_updated_at=now,
            last_error="bridge scope defined but not active in product surface",
        )
        session.add(state)
    else:
        state.version += 1
        state.desired_payload_json = _dump_json(desired)
        state.reconcile_status = "deferred"
        state.drift_detected = False
        state.last_error = "bridge scope defined but not active in product surface"
        state.desired_updated_at = now

    return await _commit_desired_state_change(session, state)


async def get_bridge_bundle_status(session: AsyncSession) -> Dict[str, Any]:
    state = await get_bridge_bundle_state(session)
    if state is None:
        return {
            "scope": BRIDGE_BUNDLE_SCOPE,
            "version": 0,
            "status": "unmanaged",
            "desired": None,
            "applied": None,
            "observed": None,
            "driftDetected": False,
            "lastError": None,
            "desiredUpdatedAt": None,
            "reconciledAt": None,
            "appliedAt": None,
            "activeInProductSurface": False,
        }

    desired = normalize_bridge_bundle_payload(_load_json(state.desired_payload_json))
    applied_raw = _load_json(state.applied_payload_json)
    observed_raw = _load_json(state.observed_payload_json)
    applied = normalize_bridge_bundle_payload(applied_raw) if applied_raw else None
    observed = normalize_bridge_bundle_payload(observed_raw) if observed_raw else None

    return {
        "scope": state.scope,
        "version": state.version,
        "status": state.reconcile_status,
        "desired": desired,
        "applied": applied,
        "observed": observed,
        "driftDetected": state.drift_detected,
        "lastError": state.last_error,
        "desiredUpdatedAt": state.desired_updated_at.isoformat() if state.desired_updated_at else None,
        "reconciledAt": state.reconciled_at.isoformat() if state.reconciled_at else None,
        "appliedAt": state.applied_at.isoformat() if state.applied_at else None,
        "activeInProductSurface": False,
    }


async def _store_mosquitto_config_desired(
    session: AsyncSession,
    desired: Dict[str, Any],
) -> BrokerDesiredState:
    state = await get_mosquitto_config_state(session)
    now = _utcnow()

    if state is None:
        state = BrokerDesiredState(
            scope=MOSQUITTO_CONFIG_SCOPE,
            version=1,
            desired_payload_json=_dump_json(desired),
            reconcile_status="pending",
            drift_detected=False,
            desired_updated_at=now,
        )
        session.add(state)
    else:
        state.version += 1
        state.desired_payload_json = _dump_json(desired)
        state.reconcile_status = "pending"
        state.drift_detected = False
        state.last_error = None
        state.desired_updated_at = now

    return await _commit_desired_state_change(session, state)


async def set_mosquitto_config_desired(session: AsyncSession, payload: Dict[str, Any]) -> BrokerDesiredState:
    desired = normalize_mosquitto_config_payload(payload)
    return await _store_mosquitto_config_desired(session, desired)


async def set_mosquitto_config_desired_from_content(session: AsyncSession, content: str) -> BrokerDesiredState:
    desired = _normalize_mosquitto_observed_payload(
        {
            "config": {},
            "listeners": [],
            "max_inflight_messages": None,
            "max_queued_messages": None,
        },
        content,
    )
    return await _store_mosquitto_config_desired(session, desired)


async def reconcile_mosquitto_config(session: AsyncSession) -> BrokerDesiredState:
    state = await get_mosquitto_config_state(session)
    if state is None:
        raise ValueError("No desired state found for mosquitto config")

    desired = _load_json(state.desired_payload_json)
    if desired is None:
        raise ValueError("Desired mosquitto config state payload is empty")

    apply_result = get_broker_reconciler().apply_mosquitto_config(desired["content"])
    errors = apply_result["errors"]
    rollback_note = apply_result.get("rollbackNote")

    observed = get_observed_mosquitto_config()
    desired_content = desired.get("content", "")
    observed_content = observed.get("content", "")
    now = _utcnow()

    state.observed_payload_json = _dump_json(observed)
    state.reconciled_at = now

    if errors:
        state.reconcile_status = "error"
        state.drift_detected = desired_content != observed_content
        state.last_error = "; ".join(errors + ([rollback_note] if rollback_note else []))
    else:
        state.applied_payload_json = _dump_json(desired)
        state.applied_at = now
        state.drift_detected = desired_content != observed_content
        state.reconcile_status = "drift" if state.drift_detected else "applied"
        state.last_error = None

    return await _commit_desired_state_change(session, state)


async def reset_mosquitto_config_desired(session: AsyncSession) -> BrokerDesiredState:
    return await set_mosquitto_config_desired_from_content(session, DEFAULT_CONFIG)


async def get_mosquitto_config_status(session: AsyncSession) -> Dict[str, Any]:
    state = await get_mosquitto_config_state(session)
    observed = get_observed_mosquitto_config()

    if state is None:
        return {
            "scope": MOSQUITTO_CONFIG_SCOPE,
            "version": 0,
            "status": "unmanaged",
            "desired": observed,
            "applied": None,
            "observed": observed,
            "driftDetected": False,
            "lastError": None,
            "desiredUpdatedAt": None,
            "reconciledAt": None,
            "appliedAt": None,
        }

    desired = _load_json(state.desired_payload_json)
    applied = _load_json(state.applied_payload_json)
    drift_detected = (desired or {}).get("content", "") != observed.get("content", "")

    if drift_detected != state.drift_detected:
        state.drift_detected = drift_detected
        if state.reconcile_status == "applied" and drift_detected:
            state.reconcile_status = "drift"
        await session.commit()
        await session.refresh(state)

    return {
        "scope": state.scope,
        "version": state.version,
        "status": state.reconcile_status,
        "desired": desired,
        "applied": applied,
        "observed": observed,
        "driftDetected": state.drift_detected,
        "lastError": state.last_error,
        "desiredUpdatedAt": state.desired_updated_at.isoformat() if state.desired_updated_at else None,
        "reconciledAt": state.reconciled_at.isoformat() if state.reconciled_at else None,
        "appliedAt": state.applied_at.isoformat() if state.applied_at else None,
    }


def _normalize_mosquitto_passwd_content(content: str) -> str:
    normalized = content.replace("\r\n", "\n")
    if normalized and not normalized.endswith("\n"):
        normalized += "\n"
    return normalized


def _parse_mosquitto_passwd_users(content: str) -> List[str]:
    usernames: List[str] = []
    for index, raw_line in enumerate(content.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        if not _MOSQUITTO_PASSWD_LINE_PATTERN.match(line):
            raise ValueError(f"Invalid mosquitto_passwd format at line {index}: {line}")
        usernames.append(line.split(":", 1)[0])
    if not usernames:
        raise ValueError("mosquitto_passwd content is empty")
    return usernames


def normalize_mosquitto_passwd_payload(payload: Dict[str, Any] | None) -> Dict[str, Any]:
    source = payload or {}
    content = source.get("content")
    if not isinstance(content, str):
        raise ValueError("Mosquitto passwd desired state requires file content")

    normalized_content = _normalize_mosquitto_passwd_content(content)
    usernames = _parse_mosquitto_passwd_users(normalized_content)
    raw_bytes = normalized_content.encode("utf-8")
    return {
        "exists": True,
        "content": normalized_content,
        "users": usernames,
        "userCount": len(usernames),
        "sizeBytes": len(raw_bytes),
        "sha256": _sha256_bytes(raw_bytes),
    }


def _public_mosquitto_passwd_payload(payload: Dict[str, Any] | None) -> Dict[str, Any]:
    source = payload or {}
    return {
        "exists": bool(source.get("exists", False)),
        "users": list(source.get("users", [])),
        "userCount": int(source.get("userCount", 0)),
        "sizeBytes": int(source.get("sizeBytes", 0)),
        "sha256": source.get("sha256"),
    }


def get_observed_mosquitto_passwd() -> Dict[str, Any]:
    if os.path.exists(_MOSQUITTO_PASSWD_PATH):
        with open(_MOSQUITTO_PASSWD_PATH, "r", encoding="utf-8") as handle:
            content = _normalize_mosquitto_passwd_content(handle.read())

        usernames = _parse_mosquitto_passwd_users(content)
        raw_bytes = content.encode("utf-8")
        return {
            "exists": True,
            "content": content,
            "users": usernames,
            "userCount": len(usernames),
            "sizeBytes": len(raw_bytes),
            "sha256": _sha256_bytes(raw_bytes),
        }

    payload = broker_observability_client.fetch_broker_passwd_sync()
    return payload.get("passwd") or {
        "exists": False,
        "content": "",
        "users": [],
        "userCount": 0,
        "sizeBytes": 0,
        "sha256": None,
    }


async def get_mosquitto_passwd_state(session: AsyncSession) -> BrokerDesiredState | None:
    return await session.get(BrokerDesiredState, MOSQUITTO_PASSWD_SCOPE)


async def _store_mosquitto_passwd_desired(
    session: AsyncSession,
    desired: Dict[str, Any],
) -> BrokerDesiredState:
    state = await get_mosquitto_passwd_state(session)
    now = _utcnow()

    if state is None:
        state = BrokerDesiredState(
            scope=MOSQUITTO_PASSWD_SCOPE,
            version=1,
            desired_payload_json=_dump_json(desired),
            reconcile_status="pending",
            drift_detected=False,
            desired_updated_at=now,
        )
        session.add(state)
    else:
        state.version += 1
        state.desired_payload_json = _dump_json(desired)
        state.reconcile_status = "pending"
        state.drift_detected = False
        state.last_error = None
        state.desired_updated_at = now

    return await _commit_desired_state_change(session, state)


async def set_mosquitto_passwd_desired(session: AsyncSession, payload: Dict[str, Any]) -> BrokerDesiredState:
    desired = normalize_mosquitto_passwd_payload(payload)
    return await _store_mosquitto_passwd_desired(session, desired)


async def set_mosquitto_passwd_desired_from_content(session: AsyncSession, content: str) -> BrokerDesiredState:
    return await set_mosquitto_passwd_desired(session, {"content": content})


async def reconcile_mosquitto_passwd(session: AsyncSession) -> BrokerDesiredState:
    state = await get_mosquitto_passwd_state(session)
    if state is None:
        raise ValueError("No desired state found for mosquitto passwd")

    desired = _load_json(state.desired_payload_json)
    if desired is None:
        raise ValueError("Desired mosquitto passwd state payload is empty")

    apply_result = get_broker_reconciler().apply_mosquitto_passwd(desired["content"])
    errors = apply_result["errors"]
    rollback_note = apply_result.get("rollbackNote")

    observed = get_observed_mosquitto_passwd()
    desired_content = desired.get("content", "")
    observed_content = observed.get("content", "")
    now = _utcnow()

    state.observed_payload_json = _dump_json(observed)
    state.reconciled_at = now

    if errors:
        state.reconcile_status = "error"
        state.drift_detected = desired_content != observed_content
        state.last_error = "; ".join(errors + ([rollback_note] if rollback_note else []))
    else:
        state.applied_payload_json = _dump_json(desired)
        state.applied_at = now
        state.drift_detected = desired_content != observed_content
        state.reconcile_status = "drift" if state.drift_detected else "applied"
        state.last_error = None

    return await _commit_desired_state_change(session, state)


async def get_mosquitto_passwd_status(session: AsyncSession) -> Dict[str, Any]:
    state = await get_mosquitto_passwd_state(session)
    observed = get_observed_mosquitto_passwd()
    observed_public = _public_mosquitto_passwd_payload(observed)

    if state is None:
        return {
            "scope": MOSQUITTO_PASSWD_SCOPE,
            "version": 0,
            "status": "unmanaged",
            "desired": observed_public,
            "applied": None,
            "observed": observed_public,
            "driftDetected": False,
            "lastError": None,
            "desiredUpdatedAt": None,
            "reconciledAt": None,
            "appliedAt": None,
        }

    desired = _load_json(state.desired_payload_json)
    applied = _load_json(state.applied_payload_json) if state.applied_payload_json else None
    desired_public = _public_mosquitto_passwd_payload(desired)
    applied_public = _public_mosquitto_passwd_payload(applied) if applied else None
    drift_detected = (desired or {}).get("content", "") != observed.get("content", "")

    if drift_detected != state.drift_detected:
        state.drift_detected = drift_detected
        if state.reconcile_status == "applied" and drift_detected:
            state.reconcile_status = "drift"
        await session.commit()
        await session.refresh(state)

    return {
        "scope": state.scope,
        "version": state.version,
        "status": state.reconcile_status,
        "desired": desired_public,
        "applied": applied_public,
        "observed": observed_public,
        "driftDetected": state.drift_detected,
        "lastError": state.last_error,
        "desiredUpdatedAt": state.desired_updated_at.isoformat() if state.desired_updated_at else None,
        "reconciledAt": state.reconciled_at.isoformat() if state.reconciled_at else None,
        "appliedAt": state.applied_at.isoformat() if state.applied_at else None,
    }


def get_observed_dynsec_config() -> Dict[str, Any]:
    if os.path.isfile(settings.dynsec_path):
        return normalize_dynsec_config_payload(dynsec_service.read_dynsec())

    try:
        return normalize_dynsec_config_payload(dynsec_service.read_dynsec())
    except Exception:
        pass

    payload = broker_observability_client.fetch_broker_dynsec_sync()
    return normalize_dynsec_config_payload(payload.get("config") or DEFAULT_DYNSEC_CONFIG)


async def get_dynsec_config_state(session: AsyncSession) -> BrokerDesiredState | None:
    return await session.get(BrokerDesiredState, DYNSEC_CONFIG_SCOPE)


async def set_dynsec_config_desired(session: AsyncSession, payload: Dict[str, Any]) -> BrokerDesiredState:
    desired = normalize_dynsec_config_payload(payload)
    state = await get_dynsec_config_state(session)
    now = _utcnow()

    if state is None:
        state = BrokerDesiredState(
            scope=DYNSEC_CONFIG_SCOPE,
            version=1,
            desired_payload_json=_dump_json(desired),
            reconcile_status="pending",
            drift_detected=False,
            desired_updated_at=now,
        )
        session.add(state)
    else:
        state.version += 1
        state.desired_payload_json = _dump_json(desired)
        state.reconcile_status = "pending"
        state.drift_detected = False
        state.last_error = None
        state.desired_updated_at = now

    return await _commit_desired_state_change(session, state)


async def reset_dynsec_config_desired(session: AsyncSession) -> BrokerDesiredState:
    return await set_dynsec_config_desired(session, DEFAULT_DYNSEC_CONFIG)


async def reconcile_dynsec_config(session: AsyncSession) -> BrokerDesiredState:
    state = await get_dynsec_config_state(session)
    if state is None:
        raise ValueError("No desired state found for dynsec config")

    desired = _load_json(state.desired_payload_json)
    if desired is None:
        raise ValueError("Desired DynSec config state payload is empty")

    apply_result = get_broker_reconciler().apply_dynsec_config(desired)
    errors = apply_result["errors"]
    rollback_note = apply_result.get("rollbackNote")
    observed = get_observed_dynsec_config()
    now = _utcnow()

    state.observed_payload_json = _dump_json(observed)
    state.reconciled_at = now

    if errors:
        state.reconcile_status = "error"
        state.drift_detected = desired != observed
        state.last_error = "; ".join(errors + ([rollback_note] if rollback_note else []))
    else:
        state.applied_payload_json = _dump_json(desired)
        state.applied_at = now
        state.drift_detected = desired != observed
        state.reconcile_status = "drift" if state.drift_detected else "applied"
        state.last_error = None

    return await _commit_desired_state_change(session, state)


async def get_dynsec_config_status(session: AsyncSession) -> Dict[str, Any]:
    state = await get_dynsec_config_state(session)
    observed = get_observed_dynsec_config()

    if state is None:
        return {
            "scope": DYNSEC_CONFIG_SCOPE,
            "version": 0,
            "status": "unmanaged",
            "desired": observed,
            "applied": None,
            "observed": observed,
            "driftDetected": False,
            "lastError": None,
            "desiredUpdatedAt": None,
            "reconciledAt": None,
            "appliedAt": None,
        }

    desired = _load_json(state.desired_payload_json)
    applied = _load_json(state.applied_payload_json)
    drift_detected = desired != observed if desired is not None else False

    if drift_detected != state.drift_detected:
        state.drift_detected = drift_detected
        if state.reconcile_status == "applied" and drift_detected:
            state.reconcile_status = "drift"
        await session.commit()
        await session.refresh(state)

    return {
        "scope": state.scope,
        "version": state.version,
        "status": state.reconcile_status,
        "desired": desired,
        "applied": applied,
        "observed": observed,
        "driftDetected": state.drift_detected,
        "lastError": state.last_error,
        "desiredUpdatedAt": state.desired_updated_at.isoformat() if state.desired_updated_at else None,
        "reconciledAt": state.reconciled_at.isoformat() if state.reconciled_at else None,
        "appliedAt": state.applied_at.isoformat() if state.applied_at else None,
    }


def _normalize_acl_entries(raw_acls: List[Any]) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for acl in raw_acls:
        if not isinstance(acl, dict):
            continue
        acl_type = acl.get("acltype") or acl.get("aclType")
        topic = acl.get("topic")
        if not isinstance(acl_type, str) or not acl_type:
            continue
        if not isinstance(topic, str) or not topic:
            continue
        allow = acl.get("allow")
        if allow is None:
            allow = str(acl.get("permission", "")).lower() == "allow"
        priority = acl.get("priority", -1)
        entries.append(
            {
                "acltype": acl_type,
                "topic": topic,
                "allow": bool(allow),
                "priority": int(priority),
            }
        )
    return sorted(entries, key=lambda item: (item["acltype"], item["topic"], item["priority"]))


def _normalize_role_entries(raw_roles: List[Any]) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for role in raw_roles:
        if isinstance(role, dict):
            name = role.get("rolename") or role.get("name")
            priority = role.get("priority")
        else:
            name = role
            priority = None
        if isinstance(name, str) and name:
            entry: Dict[str, Any] = {"rolename": name}
            if priority is not None:
                entry["priority"] = int(priority)
            entries.append(entry)
    return sorted(entries, key=lambda item: (item["rolename"], item.get("priority", 0)))


def _normalize_group_entries(raw_groups: List[Any]) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for group in raw_groups:
        if isinstance(group, dict):
            name = group.get("groupname") or group.get("name")
            priority = group.get("priority")
        else:
            name = group
            priority = None
        if isinstance(name, str) and name:
            entry: Dict[str, Any] = {"groupname": name}
            if priority is not None:
                entry["priority"] = int(priority)
            entries.append(entry)
    return sorted(entries, key=lambda item: (item["groupname"], item.get("priority", 0)))


def normalize_client_payload(payload: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if payload is None:
        return None
    username = payload.get("username")
    if not isinstance(username, str) or not username:
        raise ValueError("Client desired state requires a valid username")
    return {
        "username": username,
        "textname": str(payload.get("textname", "")),
        "disabled": bool(payload.get("disabled", False)),
        "roles": _normalize_role_entries(payload.get("roles", [])),
        "groups": _normalize_group_entries(payload.get("groups", [])),
        "deleted": bool(payload.get("deleted", False)),
    }


def normalize_role_payload(payload: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if payload is None:
        return None
    role_name = payload.get("rolename") or payload.get("name")
    if not isinstance(role_name, str) or not role_name:
        raise ValueError("Role desired state requires a valid rolename")
    return {
        "rolename": role_name,
        "acls": _normalize_acl_entries(payload.get("acls", [])),
        "deleted": bool(payload.get("deleted", False)),
    }


def normalize_group_payload(payload: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if payload is None:
        return None
    group_name = payload.get("groupname") or payload.get("name")
    if not isinstance(group_name, str) or not group_name:
        raise ValueError("Group desired state requires a valid groupname")

    normalized_clients: List[Dict[str, Any]] = []
    for client in payload.get("clients", []):
        if isinstance(client, dict):
            username = client.get("username")
            priority = client.get("priority")
        else:
            username = client
            priority = None
        if isinstance(username, str) and username:
            entry: Dict[str, Any] = {"username": username}
            if priority is not None:
                entry["priority"] = int(priority)
            normalized_clients.append(entry)

    normalized_clients.sort(key=lambda item: (item["username"], item.get("priority", 0)))
    return {
        "groupname": group_name,
        "roles": _normalize_role_entries(payload.get("roles", [])),
        "clients": normalized_clients,
        "deleted": bool(payload.get("deleted", False)),
    }


def get_observed_client(username: str) -> Dict[str, Any] | None:
    data = dynsec_service.read_dynsec()
    client = dynsec_service.find_client(data, username)
    return normalize_client_payload(client) if client else None


def get_observed_role(role_name: str) -> Dict[str, Any] | None:
    data = dynsec_service.read_dynsec()
    role = dynsec_service.find_role(data, role_name)
    return normalize_role_payload(role) if role else None


def get_observed_group(group_name: str) -> Dict[str, Any] | None:
    data = dynsec_service.read_dynsec()
    group = dynsec_service.find_group(data, group_name)
    return normalize_group_payload(group) if group else None


def get_observed_default_acl() -> Dict[str, bool]:
    data = dynsec_service.read_dynsec()
    return normalize_default_acl(data.get("defaultACLAccess", {}))


async def get_default_acl_state(session: AsyncSession) -> BrokerDesiredState | None:
    return await session.get(BrokerDesiredState, DEFAULT_ACL_SCOPE)


async def set_default_acl_desired(session: AsyncSession, payload: Dict[str, Any]) -> BrokerDesiredState:
    desired = normalize_default_acl(payload)
    state = await get_default_acl_state(session)
    now = _utcnow()

    if state is None:
        state = BrokerDesiredState(
            scope=DEFAULT_ACL_SCOPE,
            version=1,
            desired_payload_json=_dump_payload(desired),
            reconcile_status="pending",
            drift_detected=False,
            desired_updated_at=now,
        )
        session.add(state)
    else:
        state.version += 1
        state.desired_payload_json = _dump_payload(desired)
        state.reconcile_status = "pending"
        state.drift_detected = False
        state.last_error = None
        state.desired_updated_at = now

    return await _commit_desired_state_change(session, state)


async def reconcile_default_acl(session: AsyncSession) -> BrokerDesiredState:
    state = await get_default_acl_state(session)
    if state is None:
        raise ValueError("No desired state found for default ACL")

    desired = _load_payload(state.desired_payload_json)
    if desired is None:
        raise ValueError("Desired state payload is empty")

    errors = get_broker_reconciler().apply_default_acl(desired)

    observed_after = get_observed_default_acl()
    now = _utcnow()

    state.observed_payload_json = _dump_payload(observed_after)
    state.reconciled_at = now

    if errors:
        state.reconcile_status = "error"
        state.drift_detected = desired != observed_after
        state.last_error = "; ".join(errors)
    else:
        state.applied_payload_json = _dump_payload(desired)
        state.applied_at = now
        state.drift_detected = desired != observed_after
        state.reconcile_status = "drift" if state.drift_detected else "applied"
        state.last_error = None

    await session.commit()
    await session.refresh(state)
    return state


async def get_default_acl_status(session: AsyncSession) -> Dict[str, Any]:
    state = await get_default_acl_state(session)
    observed = get_observed_default_acl()

    if state is None:
        return {
            "scope": DEFAULT_ACL_SCOPE,
            "version": 0,
            "status": "unmanaged",
            "desired": observed,
            "applied": None,
            "observed": observed,
            "driftDetected": False,
            "lastError": None,
            "desiredUpdatedAt": None,
            "reconciledAt": None,
            "appliedAt": None,
        }

    desired = _load_payload(state.desired_payload_json)
    applied = _load_payload(state.applied_payload_json)
    drift_detected = desired != observed if desired is not None else False

    if drift_detected != state.drift_detected:
        state.drift_detected = drift_detected
        if state.reconcile_status == "applied" and drift_detected:
            state.reconcile_status = "drift"
        await session.commit()
        await session.refresh(state)

    return {
        "scope": state.scope,
        "version": state.version,
        "status": state.reconcile_status,
        "desired": desired,
        "applied": applied,
        "observed": observed,
        "driftDetected": state.drift_detected,
        "lastError": state.last_error,
        "desiredUpdatedAt": state.desired_updated_at.isoformat() if state.desired_updated_at else None,
        "reconciledAt": state.reconciled_at.isoformat() if state.reconciled_at else None,
        "appliedAt": state.applied_at.isoformat() if state.applied_at else None,
    }


async def get_client_state(session: AsyncSession, username: str) -> BrokerDesiredState | None:
    return await session.get(BrokerDesiredState, _client_scope(username))


async def set_client_desired(session: AsyncSession, payload: Dict[str, Any]) -> BrokerDesiredState:
    desired = normalize_client_payload(payload)
    if desired is None:
        raise ValueError("Client desired state payload is empty")

    state = await get_client_state(session, desired["username"])
    now = _utcnow()

    if state is None:
        state = BrokerDesiredState(
            scope=_client_scope(desired["username"]),
            version=1,
            desired_payload_json=_dump_json(desired),
            reconcile_status="pending",
            drift_detected=False,
            desired_updated_at=now,
        )
        session.add(state)
    else:
        state.version += 1
        state.desired_payload_json = _dump_json(desired)
        state.reconcile_status = "pending"
        state.drift_detected = False
        state.last_error = None
        state.desired_updated_at = now

    await session.commit()
    await session.refresh(state)
    return state


async def reconcile_client(
    session: AsyncSession,
    username: str,
    creation_password: str | None = None,
) -> BrokerDesiredState:
    state = await get_client_state(session, username)
    if state is None:
        raise ValueError(f"No desired state found for client {username}")

    desired = normalize_client_payload(_load_json(state.desired_payload_json))
    if desired is None:
        raise ValueError("Desired client state payload is empty")

    staged_creation_password = creation_password
    if staged_creation_password is None and not desired.get("deleted", False):
        staged_creation_password = get_staged_client_creation_secret(username, state.version)

    errors = get_broker_reconciler().apply_client_projection(
        username,
        desired,
        creation_password=staged_creation_password,
    )

    observed = get_observed_client(username)
    now = _utcnow()

    state.observed_payload_json = _dump_json(observed or {})
    state.reconciled_at = now

    if errors:
        state.reconcile_status = "error"
        state.drift_detected = desired != observed
        state.last_error = "; ".join(errors)
    else:
        state.applied_payload_json = _dump_json(desired)
        state.applied_at = now
        state.drift_detected = desired != observed
        state.reconcile_status = "drift" if state.drift_detected else "applied"
        state.last_error = None
        if creation_password is None and staged_creation_password is not None:
            clear_staged_client_creation_secret(username, state.version)

    await session.commit()
    await session.refresh(state)
    return state


async def get_client_status(session: AsyncSession, username: str) -> Dict[str, Any]:
    state = await get_client_state(session, username)
    observed = get_observed_client(username)

    if state is None:
        return {
            "scope": _client_scope(username),
            "version": 0,
            "status": "unmanaged",
            "desired": observed,
            "applied": None,
            "observed": observed,
            "driftDetected": False,
            "lastError": None,
            "desiredUpdatedAt": None,
            "reconciledAt": None,
            "appliedAt": None,
        }

    desired = normalize_client_payload(_load_json(state.desired_payload_json))
    applied_raw = _load_json(state.applied_payload_json)
    applied = normalize_client_payload(applied_raw) if applied_raw else None
    drift_detected = desired != observed if desired is not None else False

    if drift_detected != state.drift_detected:
        state.drift_detected = drift_detected
        if state.reconcile_status == "applied" and drift_detected:
            state.reconcile_status = "drift"
        await session.commit()
        await session.refresh(state)

    return {
        "scope": state.scope,
        "version": state.version,
        "status": state.reconcile_status,
        "desired": desired,
        "applied": applied,
        "observed": observed,
        "driftDetected": state.drift_detected,
        "lastError": state.last_error,
        "desiredUpdatedAt": state.desired_updated_at.isoformat() if state.desired_updated_at else None,
        "reconciledAt": state.reconciled_at.isoformat() if state.reconciled_at else None,
        "appliedAt": state.applied_at.isoformat() if state.applied_at else None,
    }


async def get_role_state(session: AsyncSession, role_name: str) -> BrokerDesiredState | None:
    return await session.get(BrokerDesiredState, _role_scope(role_name))


async def set_role_desired(session: AsyncSession, payload: Dict[str, Any]) -> BrokerDesiredState:
    desired = normalize_role_payload(payload)
    if desired is None:
        raise ValueError("Role desired state payload is empty")

    state = await get_role_state(session, desired["rolename"])
    now = _utcnow()

    if state is None:
        state = BrokerDesiredState(
            scope=_role_scope(desired["rolename"]),
            version=1,
            desired_payload_json=_dump_json(desired),
            reconcile_status="pending",
            drift_detected=False,
            desired_updated_at=now,
        )
        session.add(state)
    else:
        state.version += 1
        state.desired_payload_json = _dump_json(desired)
        state.reconcile_status = "pending"
        state.drift_detected = False
        state.last_error = None
        state.desired_updated_at = now

    await session.commit()
    await session.refresh(state)
    return state


async def reconcile_role(session: AsyncSession, role_name: str) -> BrokerDesiredState:
    state = await get_role_state(session, role_name)
    if state is None:
        raise ValueError(f"No desired state found for role {role_name}")

    desired = normalize_role_payload(_load_json(state.desired_payload_json))
    if desired is None:
        raise ValueError("Desired role state payload is empty")

    errors = get_broker_reconciler().apply_role_projection(role_name, desired)

    observed = get_observed_role(role_name)
    now = _utcnow()
    state.observed_payload_json = _dump_json(observed or {})
    state.reconciled_at = now

    if errors:
        state.reconcile_status = "error"
        state.drift_detected = desired != observed
        state.last_error = "; ".join(errors)
    else:
        state.applied_payload_json = _dump_json(desired)
        state.applied_at = now
        state.drift_detected = desired != observed
        state.reconcile_status = "drift" if state.drift_detected else "applied"
        state.last_error = None

    await session.commit()
    await session.refresh(state)
    return state


async def get_role_status(session: AsyncSession, role_name: str) -> Dict[str, Any]:
    state = await get_role_state(session, role_name)
    observed = get_observed_role(role_name)

    if state is None:
        return {
            "scope": _role_scope(role_name),
            "version": 0,
            "status": "unmanaged",
            "desired": observed,
            "applied": None,
            "observed": observed,
            "driftDetected": False,
            "lastError": None,
            "desiredUpdatedAt": None,
            "reconciledAt": None,
            "appliedAt": None,
        }

    desired = normalize_role_payload(_load_json(state.desired_payload_json))
    applied_raw = _load_json(state.applied_payload_json)
    applied = normalize_role_payload(applied_raw) if applied_raw else None
    drift_detected = desired != observed if desired is not None else False

    if drift_detected != state.drift_detected:
        state.drift_detected = drift_detected
        if state.reconcile_status == "applied" and drift_detected:
            state.reconcile_status = "drift"
        await session.commit()
        await session.refresh(state)

    return {
        "scope": state.scope,
        "version": state.version,
        "status": state.reconcile_status,
        "desired": desired,
        "applied": applied,
        "observed": observed,
        "driftDetected": state.drift_detected,
        "lastError": state.last_error,
        "desiredUpdatedAt": state.desired_updated_at.isoformat() if state.desired_updated_at else None,
        "reconciledAt": state.reconciled_at.isoformat() if state.reconciled_at else None,
        "appliedAt": state.applied_at.isoformat() if state.applied_at else None,
    }


async def get_group_state(session: AsyncSession, group_name: str) -> BrokerDesiredState | None:
    return await session.get(BrokerDesiredState, _group_scope(group_name))


async def set_group_desired(session: AsyncSession, payload: Dict[str, Any]) -> BrokerDesiredState:
    desired = normalize_group_payload(payload)
    if desired is None:
        raise ValueError("Group desired state payload is empty")

    state = await get_group_state(session, desired["groupname"])
    now = _utcnow()

    if state is None:
        state = BrokerDesiredState(
            scope=_group_scope(desired["groupname"]),
            version=1,
            desired_payload_json=_dump_json(desired),
            reconcile_status="pending",
            drift_detected=False,
            desired_updated_at=now,
        )
        session.add(state)
    else:
        state.version += 1
        state.desired_payload_json = _dump_json(desired)
        state.reconcile_status = "pending"
        state.drift_detected = False
        state.last_error = None
        state.desired_updated_at = now

    await session.commit()
    await session.refresh(state)
    return state


async def reconcile_group(
    session: AsyncSession,
    group_name: str,
) -> BrokerDesiredState:
    state = await get_group_state(session, group_name)
    if state is None:
        raise ValueError(f"No desired state found for group {group_name}")

    desired = normalize_group_payload(_load_json(state.desired_payload_json))
    if desired is None:
        raise ValueError("Desired group state payload is empty")

    errors = get_broker_reconciler().apply_group_projection(group_name, desired)

    observed = get_observed_group(group_name)
    now = _utcnow()
    state.observed_payload_json = _dump_json(observed or {})
    state.reconciled_at = now

    if errors:
        state.reconcile_status = "error"
        state.drift_detected = desired != observed
        state.last_error = "; ".join(errors)
    else:
        state.applied_payload_json = _dump_json(desired)
        state.applied_at = now
        state.drift_detected = desired != observed
        state.reconcile_status = "drift" if state.drift_detected else "applied"
        state.last_error = None

    await session.commit()
    await session.refresh(state)
    return state


async def get_group_status(session: AsyncSession, group_name: str) -> Dict[str, Any]:
    state = await get_group_state(session, group_name)
    observed = get_observed_group(group_name)

    if state is None:
        return {
            "scope": _group_scope(group_name),
            "version": 0,
            "status": "unmanaged",
            "desired": observed,
            "applied": None,
            "observed": observed,
            "driftDetected": False,
            "lastError": None,
            "desiredUpdatedAt": None,
            "reconciledAt": None,
            "appliedAt": None,
        }

    desired = normalize_group_payload(_load_json(state.desired_payload_json))
    applied_raw = _load_json(state.applied_payload_json)
    applied = normalize_group_payload(applied_raw) if applied_raw else None
    drift_detected = desired != observed if desired is not None else False

    if drift_detected != state.drift_detected:
        state.drift_detected = drift_detected
        if state.reconcile_status == "applied" and drift_detected:
            state.reconcile_status = "drift"
        await session.commit()
        await session.refresh(state)

    return {
        "scope": state.scope,
        "version": state.version,
        "status": state.reconcile_status,
        "desired": desired,
        "applied": applied,
        "observed": observed,
        "driftDetected": state.drift_detected,
        "lastError": state.last_error,
        "desiredUpdatedAt": state.desired_updated_at.isoformat() if state.desired_updated_at else None,
        "reconciledAt": state.reconciled_at.isoformat() if state.reconciled_at else None,
        "appliedAt": state.applied_at.isoformat() if state.applied_at else None,
    }


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _normalize_tls_cert_entries(raw_entries: List[Any]) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for entry in raw_entries:
        if not isinstance(entry, dict):
            continue
        filename = entry.get("filename")
        if not isinstance(filename, str) or not filename:
            continue
        content_base64 = entry.get("contentBase64")
        deleted = bool(entry.get("deleted", False))
        extension = os.path.splitext(filename)[1].lower()
        normalized: Dict[str, Any] = {
            "filename": filename,
            "extension": extension,
            "deleted": deleted,
            "size": int(entry.get("size", 0)),
            "sha256": entry.get("sha256"),
        }
        if isinstance(content_base64, str) and content_base64:
            normalized["contentBase64"] = content_base64
            raw_bytes = base64.b64decode(content_base64.encode("ascii"))
            normalized["size"] = len(raw_bytes)
            normalized["sha256"] = _sha256_bytes(raw_bytes)
        entries.append(normalized)
    return sorted(entries, key=lambda item: item["filename"])


def _public_tls_cert_entries(raw_entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "filename": entry["filename"],
            "extension": entry.get("extension"),
            "size": entry.get("size", 0),
            "sha256": entry.get("sha256"),
            "deleted": bool(entry.get("deleted", False)),
        }
        for entry in _normalize_tls_cert_entries(raw_entries)
    ]


def _effective_tls_cert_entries(raw_entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [entry for entry in _public_tls_cert_entries(raw_entries) if not entry.get("deleted", False)]


def get_observed_tls_cert_store() -> Dict[str, Any]:
    if os.path.isdir(_CERTS_DIR):
        os.makedirs(_CERTS_DIR, exist_ok=True)
        entries: List[Dict[str, Any]] = []
        for filename in sorted(os.listdir(_CERTS_DIR)):
            path = os.path.join(_CERTS_DIR, filename)
            extension = os.path.splitext(filename)[1].lower()
            if not os.path.isfile(path) or extension not in _ALLOWED_CERT_EXTENSIONS:
                continue
            with open(path, "rb") as handle:
                content = handle.read()
            entries.append(
                {
                    "filename": filename,
                    "extension": extension,
                    "size": len(content),
                    "sha256": _sha256_bytes(content),
                    "deleted": False,
                }
            )
        return {"certs": entries}

    payload = broker_observability_client.fetch_broker_tls_certs_sync()
    return {"certs": payload.get("certs") or []}


async def get_tls_cert_store_state(session: AsyncSession) -> BrokerDesiredState | None:
    return await session.get(BrokerDesiredState, TLS_CERT_STORE_SCOPE)


async def _store_tls_cert_store_desired(session: AsyncSession, desired: Dict[str, Any]) -> BrokerDesiredState:
    state = await get_tls_cert_store_state(session)
    now = _utcnow()

    if state is None:
        state = BrokerDesiredState(
            scope=TLS_CERT_STORE_SCOPE,
            version=1,
            desired_payload_json=_dump_json(desired),
            reconcile_status="pending",
            drift_detected=False,
            desired_updated_at=now,
        )
        session.add(state)
    else:
        state.version += 1
        state.desired_payload_json = _dump_json(desired)
        state.reconcile_status = "pending"
        state.drift_detected = False
        state.last_error = None
        state.desired_updated_at = now

    await session.commit()
    await session.refresh(state)
    return state


async def upsert_tls_cert_desired(session: AsyncSession, filename: str, content: bytes) -> BrokerDesiredState:
    state = await get_tls_cert_store_state(session)
    current = _load_json(state.desired_payload_json) if state and state.desired_payload_json else {"certs": []}
    entries = _normalize_tls_cert_entries(current.get("certs", []))
    content_base64 = base64.b64encode(content).decode("ascii")
    next_entry = {
        "filename": filename,
        "extension": os.path.splitext(filename)[1].lower(),
        "contentBase64": content_base64,
        "deleted": False,
    }
    filtered = [entry for entry in entries if entry["filename"] != filename]
    filtered.append(next_entry)
    return await _store_tls_cert_store_desired(session, {"certs": filtered})


async def delete_tls_cert_desired(session: AsyncSession, filename: str) -> BrokerDesiredState:
    state = await get_tls_cert_store_state(session)
    current = _load_json(state.desired_payload_json) if state and state.desired_payload_json else {"certs": []}
    entries = _normalize_tls_cert_entries(current.get("certs", []))
    filtered = [entry for entry in entries if entry["filename"] != filename]
    filtered.append({"filename": filename, "extension": os.path.splitext(filename)[1].lower(), "deleted": True})
    return await _store_tls_cert_store_desired(session, {"certs": filtered})


async def reconcile_tls_cert_store(session: AsyncSession) -> BrokerDesiredState:
    state = await get_tls_cert_store_state(session)
    if state is None:
        raise ValueError("No desired state found for TLS cert store")

    desired = _load_json(state.desired_payload_json) or {"certs": []}
    desired_entries = _normalize_tls_cert_entries(desired.get("certs", []))
    errors = get_broker_reconciler().apply_tls_cert_store(desired_entries)

    observed = get_observed_tls_cert_store()
    desired_public = _public_tls_cert_entries(desired_entries)
    observed_public = _public_tls_cert_entries(observed.get("certs", []))
    desired_effective = _effective_tls_cert_entries(desired_entries)
    now = _utcnow()

    state.observed_payload_json = _dump_json(observed)
    state.reconciled_at = now

    if errors:
        state.reconcile_status = "error"
        state.drift_detected = desired_effective != observed_public
        state.last_error = "; ".join(errors)
    else:
        state.applied_payload_json = _dump_json({"certs": desired_entries})
        state.applied_at = now
        state.drift_detected = desired_effective != observed_public
        state.reconcile_status = "drift" if state.drift_detected else "applied"
        state.last_error = None

    await session.commit()
    await session.refresh(state)
    return state


async def get_tls_cert_store_status(session: AsyncSession) -> Dict[str, Any]:
    state = await get_tls_cert_store_state(session)
    observed = get_observed_tls_cert_store()
    observed_public = _public_tls_cert_entries(observed.get("certs", []))

    if state is None:
        return {
            "scope": TLS_CERT_STORE_SCOPE,
            "version": 0,
            "status": "unmanaged",
            "desired": {"certs": observed_public},
            "applied": None,
            "observed": {"certs": observed_public},
            "driftDetected": False,
            "lastError": None,
            "desiredUpdatedAt": None,
            "reconciledAt": None,
            "appliedAt": None,
        }

    desired = _load_json(state.desired_payload_json) or {"certs": []}
    applied = _load_json(state.applied_payload_json) if state.applied_payload_json else None
    desired_public = {"certs": _public_tls_cert_entries(desired.get("certs", []))}
    applied_public = {"certs": _public_tls_cert_entries(applied.get("certs", []))} if applied else None
    drift_detected = _effective_tls_cert_entries(desired.get("certs", [])) != observed_public

    if drift_detected != state.drift_detected:
        state.drift_detected = drift_detected
        if state.reconcile_status == "applied" and drift_detected:
            state.reconcile_status = "drift"
        await session.commit()
        await session.refresh(state)

    return {
        "scope": state.scope,
        "version": state.version,
        "status": state.reconcile_status,
        "desired": desired_public,
        "applied": applied_public,
        "observed": {"certs": observed_public},
        "driftDetected": state.drift_detected,
        "lastError": state.last_error,
        "desiredUpdatedAt": state.desired_updated_at.isoformat() if state.desired_updated_at else None,
        "reconciledAt": state.reconciled_at.isoformat() if state.reconciled_at else None,
        "appliedAt": state.applied_at.isoformat() if state.applied_at else None,
    }