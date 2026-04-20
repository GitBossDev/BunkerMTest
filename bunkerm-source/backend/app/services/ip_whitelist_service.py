from __future__ import annotations

import ipaddress
import json
import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import AsyncSessionLocal
from models.orm import BrokerDesiredState, BrokerDesiredStateAudit

logger = logging.getLogger(__name__)

IP_WHITELIST_SCOPE = "security.ip_whitelist"
_AUDIT_EVENT_KIND = "desired_change"
_PUBLIC_PATHS = frozenset({"/api/v1/health", "/api/v1/monitor/health"})
_SCOPES = frozenset({"api_admin", "mqtt_clients"})
_ACTION_VALUES = frozenset({"allow", "deny"})
_MODE_VALUES = frozenset({"disabled", "audit", "enforce"})

_CACHE_LOCK = threading.Lock()
_CACHE: Dict[str, Any] = {
    "policy": None,
    "version": 0,
    "desiredUpdatedAt": None,
}

_RUNTIME_STATUS_LOCK = threading.Lock()
_RUNTIME_STATUS: Dict[str, Dict[str, Any]] = {
    "api_admin": {
        "lastDecisionAt": None,
        "lastDecisionResult": None,
        "lastMatchedEntryId": None,
        "lastEvaluatedIp": None,
    }
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _json_dump(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=True, sort_keys=True)


def _json_load(payload_json: str | None) -> Dict[str, Any] | None:
    if not payload_json:
        return None
    return json.loads(payload_json)


def default_ip_whitelist_policy() -> Dict[str, Any]:
    return {
        "mode": "disabled",
        "trustedProxies": [],
        "defaultAction": {"api_admin": "allow", "mqtt_clients": "allow"},
        "entries": [],
        "lastUpdatedBy": {"type": "system", "id": "bootstrap"},
    }


def _normalize_actor(raw_actor: Dict[str, Any] | None) -> Dict[str, str]:
    actor = raw_actor or {}
    actor_type = str(actor.get("type") or "system").strip().lower() or "system"
    actor_id = str(actor.get("id") or "unknown").strip() or "unknown"
    return {"type": actor_type, "id": actor_id}


def _normalize_proxy_list(values: list[Any] | None) -> list[str]:
    normalized: list[str] = []
    for raw_value in values or []:
        cidr = str(raw_value).strip()
        if not cidr:
            continue
        ipaddress.ip_network(cidr, strict=False)
        normalized.append(cidr)
    return sorted(dict.fromkeys(normalized))


def _normalize_entries(values: list[Dict[str, Any]] | None) -> list[Dict[str, Any]]:
    normalized: list[Dict[str, Any]] = []
    seen_ids: set[str] = set()
    for raw_entry in values or []:
        entry_id = str(raw_entry.get("id") or "").strip()
        if not entry_id:
            raise ValueError("Whitelist entries require a non-empty id")
        if entry_id in seen_ids:
            raise ValueError(f"Duplicate whitelist entry id: {entry_id}")
        cidr = str(raw_entry.get("cidr") or "").strip()
        if not cidr:
            raise ValueError(f"Whitelist entry {entry_id} requires a non-empty cidr")
        ipaddress.ip_network(cidr, strict=False)
        scope = str(raw_entry.get("scope") or "").strip().lower()
        if scope not in _SCOPES:
            raise ValueError(f"Whitelist entry {entry_id} has invalid scope: {scope}")
        seen_ids.add(entry_id)
        normalized.append(
            {
                "id": entry_id,
                "cidr": cidr,
                "scope": scope,
                "description": str(raw_entry.get("description") or "").strip(),
                "enabled": bool(raw_entry.get("enabled", True)),
            }
        )
    return sorted(normalized, key=lambda item: (item["scope"], item["cidr"], item["id"]))


def normalize_ip_whitelist_policy(payload: Dict[str, Any] | None) -> Dict[str, Any]:
    source = payload or {}
    mode = str(source.get("mode") or "disabled").strip().lower()
    if mode not in _MODE_VALUES:
        raise ValueError(f"Whitelist mode must be one of: {sorted(_MODE_VALUES)}")

    raw_default_action = source.get("defaultAction") or {}
    default_action = {
        scope: str(raw_default_action.get(scope) or "allow").strip().lower()
        for scope in _SCOPES
    }
    for scope, action in default_action.items():
        if action not in _ACTION_VALUES:
            raise ValueError(f"Whitelist defaultAction.{scope} must be one of: {sorted(_ACTION_VALUES)}")

    return {
        "mode": mode,
        "trustedProxies": _normalize_proxy_list(source.get("trustedProxies") or []),
        "defaultAction": default_action,
        "entries": _normalize_entries(source.get("entries") or []),
        "lastUpdatedBy": _normalize_actor(source.get("lastUpdatedBy")),
    }


def _policy_from_state(state: BrokerDesiredState | None) -> Dict[str, Any]:
    if state is None:
        policy = default_ip_whitelist_policy()
        policy["version"] = 0
        policy["lastUpdatedAt"] = None
        return policy

    policy = normalize_ip_whitelist_policy(_json_load(state.desired_payload_json))
    policy["version"] = state.version
    policy["lastUpdatedAt"] = state.desired_updated_at.isoformat() if state.desired_updated_at else None
    return policy


def clear_ip_whitelist_runtime_state() -> None:
    with _CACHE_LOCK:
        _CACHE["policy"] = None
        _CACHE["version"] = 0
        _CACHE["desiredUpdatedAt"] = None
    with _RUNTIME_STATUS_LOCK:
        _RUNTIME_STATUS["api_admin"] = {
            "lastDecisionAt": None,
            "lastDecisionResult": None,
            "lastMatchedEntryId": None,
            "lastEvaluatedIp": None,
        }


def prime_ip_whitelist_cache(policy: Dict[str, Any]) -> None:
    normalized = normalize_ip_whitelist_policy(policy)
    with _CACHE_LOCK:
        _CACHE["policy"] = normalized
        _CACHE["version"] = int(policy.get("version", 0) or 0)
        _CACHE["desiredUpdatedAt"] = policy.get("lastUpdatedAt")


def get_cached_ip_whitelist_policy() -> Dict[str, Any]:
    with _CACHE_LOCK:
        cached_policy = _CACHE["policy"]
        if cached_policy is None:
            policy = default_ip_whitelist_policy()
            policy["version"] = 0
            policy["lastUpdatedAt"] = None
            return policy
        policy = json.loads(_json_dump(cached_policy))
        policy["version"] = _CACHE["version"]
        policy["lastUpdatedAt"] = _CACHE["desiredUpdatedAt"]
        return policy


async def get_ip_whitelist_state(session: AsyncSession) -> BrokerDesiredState | None:
    return await session.get(BrokerDesiredState, IP_WHITELIST_SCOPE)


async def _commit_state_change(session: AsyncSession, state: BrokerDesiredState) -> BrokerDesiredState:
    session.add(
        BrokerDesiredStateAudit(
            scope=state.scope,
            version=state.version,
            event_kind=_AUDIT_EVENT_KIND,
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
    prime_ip_whitelist_cache(_policy_from_state(state))
    return state


async def set_ip_whitelist_desired(session: AsyncSession, payload: Dict[str, Any] | None) -> BrokerDesiredState:
    desired = normalize_ip_whitelist_policy(payload)
    state = await get_ip_whitelist_state(session)
    now = _utcnow()

    if state is None:
        state = BrokerDesiredState(
            scope=IP_WHITELIST_SCOPE,
            version=1,
            desired_payload_json=_json_dump(desired),
            applied_payload_json=_json_dump(desired),
            observed_payload_json=_json_dump(desired),
            reconcile_status="applied",
            drift_detected=False,
            last_error=None,
            desired_updated_at=now,
            reconciled_at=now,
            applied_at=now,
        )
        session.add(state)
    else:
        state.version += 1
        state.desired_payload_json = _json_dump(desired)
        state.applied_payload_json = _json_dump(desired)
        state.observed_payload_json = _json_dump(desired)
        state.reconcile_status = "applied"
        state.drift_detected = False
        state.last_error = None
        state.desired_updated_at = now
        state.reconciled_at = now
        state.applied_at = now

    return await _commit_state_change(session, state)


async def refresh_ip_whitelist_cache() -> None:
    try:
        async with AsyncSessionLocal() as session:
            state = await get_ip_whitelist_state(session)
    except Exception as exc:
        logger.warning("IP whitelist cache could not be refreshed from database: %s", exc)
        return

    if state is not None:
        prime_ip_whitelist_cache(_policy_from_state(state))


def _count_entries(policy: Dict[str, Any], scope: str) -> int:
    return sum(1 for entry in policy.get("entries", []) if entry.get("scope") == scope and entry.get("enabled", True))


def _build_status(policy: Dict[str, Any]) -> Dict[str, Any]:
    with _RUNTIME_STATUS_LOCK:
        api_runtime = dict(_RUNTIME_STATUS["api_admin"])

    return {
        "apiAdmin": {
            "mode": policy["mode"],
            "enforcementPoint": "http-ingress",
            "configuredEntries": _count_entries(policy, "api_admin"),
            "lastDecisionAt": api_runtime["lastDecisionAt"],
            "lastDecisionResult": api_runtime["lastDecisionResult"],
            "lastMatchedEntryId": api_runtime["lastMatchedEntryId"],
            "lastEvaluatedIp": api_runtime["lastEvaluatedIp"],
            "lastError": None,
        },
        "mqttClients": {
            "mode": policy["mode"],
            "enforcementPoint": "broker-control-plane",
            "configuredEntries": _count_entries(policy, "mqtt_clients"),
            "desiredVersion": policy["version"],
            "appliedVersion": policy["version"],
            "observedVersion": policy["version"],
            "driftDetected": False,
            "lastError": None,
        },
    }


async def get_ip_whitelist_document(session: AsyncSession) -> Dict[str, Any]:
    state = await get_ip_whitelist_state(session)
    policy = _policy_from_state(state)
    return {"policy": policy, "status": _build_status(policy)}


def _is_public_path(path: str) -> bool:
    return path in _PUBLIC_PATHS


def _resolve_effective_ip(request: Request, trusted_proxies: list[str]) -> str:
    client_host = (request.client.host if request.client else "127.0.0.1") or "127.0.0.1"
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if not forwarded_for:
        return client_host

    try:
        client_ip = ipaddress.ip_address(client_host)
    except ValueError:
        return client_host

    for raw_proxy in trusted_proxies:
        try:
            network = ipaddress.ip_network(raw_proxy, strict=False)
        except ValueError:
            continue
        if client_ip in network:
            forwarded_ip = forwarded_for.split(",", 1)[0].strip()
            if forwarded_ip:
                return forwarded_ip
    return client_host


def evaluate_api_admin_request(request: Request) -> Dict[str, Any]:
    path = request.url.path
    if not path.startswith("/api/v1") or _is_public_path(path):
        return {"allowed": True, "reason": "public_or_non_api", "effectiveIp": None}

    policy = get_cached_ip_whitelist_policy()
    if policy["mode"] == "disabled":
        return {"allowed": True, "reason": "disabled", "effectiveIp": None}

    effective_ip_raw = _resolve_effective_ip(request, policy.get("trustedProxies", []))
    try:
        effective_ip = ipaddress.ip_address(effective_ip_raw)
    except ValueError:
        effective_ip = None

    matched_entry = None
    for entry in policy.get("entries", []):
        if entry.get("scope") != "api_admin" or not entry.get("enabled", True):
            continue
        if effective_ip is None:
            continue
        network = ipaddress.ip_network(entry["cidr"], strict=False)
        if effective_ip in network:
            matched_entry = entry
            break

    default_action = policy.get("defaultAction", {}).get("api_admin", "allow")
    allowed_by_policy = matched_entry is not None or default_action == "allow"
    decision_result = "allowed" if allowed_by_policy else "denied"
    decision_at = datetime.now(timezone.utc).isoformat()

    with _RUNTIME_STATUS_LOCK:
        _RUNTIME_STATUS["api_admin"] = {
            "lastDecisionAt": decision_at,
            "lastDecisionResult": decision_result,
            "lastMatchedEntryId": matched_entry.get("id") if matched_entry else None,
            "lastEvaluatedIp": effective_ip_raw,
        }

    if not allowed_by_policy:
        logger.warning(
            "IP whitelist %s for api_admin path=%s ip=%s",
            "enforced deny" if policy["mode"] == "enforce" else "audit deny",
            path,
            effective_ip_raw,
        )

    if policy["mode"] == "enforce" and not allowed_by_policy:
        return {"allowed": False, "reason": "ip_not_allowed", "effectiveIp": effective_ip_raw}

    return {"allowed": True, "reason": decision_result, "effectiveIp": effective_ip_raw}