"""
Router ClientLogs: eventos de conexión/desconexión y actividad de clientes MQTT.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Set

from fastapi import APIRouter, Security, status

from core.auth import get_api_key
from services import dynsec_service as dynsec_svc
from services.clientlogs_service import mqtt_monitor, MQTTEvent

router = APIRouter(prefix="/api/v1/clientlogs", tags=["clientlogs"])


def _active_client_events(window_seconds: int = 600) -> Dict[str, MQTTEvent]:
    """Current active clients, using subscribe activity as fallback when logs are incomplete."""
    result: Dict[str, MQTTEvent] = dict(mqtt_monitor.connected_clients)
    cutoff = time.time() - window_seconds
    for cid, last_ts in mqtt_monitor._last_seen.items():
        if last_ts < cutoff or cid in result:
            continue
        username, protocol_level, ip, port, clean, keep_alive = mqtt_monitor._get_client_info(cid)
        if mqtt_monitor._is_admin(username):
            continue
        last_conn = mqtt_monitor._last_connection_info.get(username, {})
        result[cid] = MQTTEvent(
            id=str(uuid.uuid4()),
            timestamp=datetime.fromtimestamp(last_ts, tz=timezone.utc).isoformat(),
            event_type="Client Connection",
            client_id=cid,
            details="Active (inferred from subscribe activity)",
            status="success",
            protocol_level=protocol_level,
            clean_session=clean,
            keep_alive=keep_alive,
            username=username,
            ip_address=last_conn.get("ip_address", ip),
            port=last_conn.get("port", port),
        )
    return result


def _connected_non_admin_events() -> Dict[str, MQTTEvent]:
    return {
        client_id: event
        for client_id, event in mqtt_monitor.connected_clients.items()
        if not mqtt_monitor._is_admin(event.username)
    }


def build_activity_summary(window_seconds: int = 600) -> Dict[str, int]:
    """Count currently connected non-admin clients with effective subscribe/publish capability."""
    active_clients = _connected_non_admin_events()
    capability_map = _build_client_capability_map()

    subscribed_clients = 0
    publisher_clients = 0
    seen_usernames: Set[str] = set()

    for event in active_clients.values():
        username = event.username
        if not username or username in seen_usernames:
            continue
        seen_usernames.add(username)
        caps = capability_map.get(username, {"publish": False, "subscribe": False})
        if caps["subscribe"]:
            subscribed_clients += 1
        if caps["publish"]:
            publisher_clients += 1

    return {
        "subscribed_clients": subscribed_clients,
        "publisher_clients": publisher_clients,
        "window_seconds": window_seconds,
    }


def _entry_names(items: Iterable[Any], key: str) -> Set[str]:
    names: Set[str] = set()
    for item in items or []:
        if isinstance(item, dict):
            name = item.get(key)
        else:
            name = item
        if isinstance(name, str) and name:
            names.add(name)
    return names


def _build_client_capability_map() -> Dict[str, Dict[str, bool]]:
    data = dynsec_svc.read_dynsec()
    default_acl = data.get("defaultACLAccess", {})
    default_publish = bool(default_acl.get("publishClientSend", True))
    default_subscribe = bool(default_acl.get("subscribe", True))

    role_caps: Dict[str, Dict[str, bool]] = {}
    for role in data.get("roles", []):
        role_name = role.get("rolename")
        if not isinstance(role_name, str) or not role_name:
            continue
        caps = {"publish": False, "subscribe": False}
        for acl in role.get("acls", []):
            acl_type = acl.get("acltype") or acl.get("aclType")
            allow = acl.get("allow")
            if allow is None:
                allow = str(acl.get("permission", "")).lower() == "allow"
            if not allow:
                continue
            if acl_type == "publishClientSend":
                caps["publish"] = True
            if acl_type in ("subscribe", "subscribeLiteral", "subscribePattern"):
                caps["subscribe"] = True
        role_caps[role_name] = caps

    group_roles: Dict[str, Set[str]] = {}
    group_clients: Dict[str, Set[str]] = {}
    for group in data.get("groups", []):
        group_name = group.get("groupname")
        if not isinstance(group_name, str) or not group_name:
            continue
        group_roles[group_name] = _entry_names(group.get("roles", []), "rolename")
        group_clients[group_name] = _entry_names(group.get("clients", []), "username")

    capability_map: Dict[str, Dict[str, bool]] = {}
    for client in data.get("clients", []):
        username = client.get("username")
        if not isinstance(username, str) or not username:
            continue
        direct_roles = _entry_names(client.get("roles", []), "rolename")
        client_groups = _entry_names(client.get("groups", []), "groupname")
        for group_name, members in group_clients.items():
            if username in members:
                client_groups.add(group_name)

        effective_roles = set(direct_roles)
        for group_name in client_groups:
            effective_roles.update(group_roles.get(group_name, set()))

        can_publish = default_publish
        can_subscribe = default_subscribe
        for role_name in effective_roles:
            caps = role_caps.get(role_name)
            if not caps:
                continue
            can_publish = can_publish or caps["publish"]
            can_subscribe = can_subscribe or caps["subscribe"]

        capability_map[username] = {
            "publish": can_publish,
            "subscribe": can_subscribe,
        }

    return capability_map


@router.get("/events")
async def get_mqtt_events(limit: int = 1000, api_key: str = Security(get_api_key)):
    """Devuelve los eventos MQTT más recientes (conexión, desconexión, auth failure, etc.)."""
    all_events = list(mqtt_monitor.events)
    sorted_events = sorted(all_events, key=lambda x: x.timestamp, reverse=True)[:limit]
    return {"events": [event.model_dump() for event in sorted_events]}


@router.get("/connected-clients")
async def get_connected_clients(api_key: str = Security(get_api_key)):
    """
    Devuelve clientes conectados.
    Usa la lista de conexiones rastreadas por log más clientes activos en los últimos 10 min
    como fallback (útil cuando el broker solo tiene log_type subscribe configurado).
    """
    result = _active_client_events(window_seconds=600)
    return {"clients": [client.model_dump() for client in result.values()]}


@router.get("/last-connection")
async def get_last_connection(api_key: str = Security(get_api_key)):
    """Devuelve la última info de conexión conocida (ip, puerto, timestamp) por username."""
    return {"info": mqtt_monitor._last_connection_info}


@router.get("/top-subscribed")
async def get_top_subscribed(limit: int = 15, api_key: str = Security(get_api_key)):
    """Devuelve los tópicos con más suscripciones acumuladas desde el arranque."""
    counts = mqtt_monitor._subscription_counts
    top = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:limit]
    return {
        "top_subscribed": [{"topic": t, "count": c} for t, c in top],
        "total_distinct_subscribed": len(counts),
    }


@router.get("/activity-summary")
async def get_activity_summary(window_seconds: int = 600, api_key: str = Security(get_api_key)):
    """Devuelve clientes activos con capacidad efectiva de subscribe o publish según DynSec."""
    return build_activity_summary(window_seconds=window_seconds)
