"""Servicios transicionales de control-plane para broker desired state."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from models.orm import BrokerDesiredState
from services import dynsec_service

DEFAULT_ACL_SCOPE = "dynsec.default_acl"
DEFAULT_ACL_KEYS = (
    "publishClientSend",
    "publishClientReceive",
    "subscribe",
    "unsubscribe",
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def normalize_default_acl(payload: Dict[str, Any] | None) -> Dict[str, bool]:
    source = payload or {}
    return {key: bool(source.get(key, True)) for key in DEFAULT_ACL_KEYS}


def _dump_payload(payload: Dict[str, bool]) -> str:
    return json.dumps(payload, sort_keys=True)


def _load_payload(payload_json: str | None) -> Dict[str, bool] | None:
    if not payload_json:
        return None
    return normalize_default_acl(json.loads(payload_json))


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

    await session.commit()
    await session.refresh(state)
    return state


async def reconcile_default_acl(session: AsyncSession) -> BrokerDesiredState:
    state = await get_default_acl_state(session)
    if state is None:
        raise ValueError("No desired state found for default ACL")

    desired = _load_payload(state.desired_payload_json)
    if desired is None:
        raise ValueError("Desired state payload is empty")

    observed_before = get_observed_default_acl()
    errors: list[str] = []

    if observed_before != desired:
        for acl_type, allow in desired.items():
            result = dynsec_service.execute_mosquitto_command(
                ["setDefaultACLAccess", acl_type, "allow" if allow else "deny"]
            )
            if not result["success"]:
                errors.append(f"{acl_type}: {result['error_output']}")

        if not errors:
            with dynsec_service._dynsec_lock:
                data = dynsec_service.read_dynsec()
                data["defaultACLAccess"] = desired
                dynsec_service.write_dynsec(data)

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