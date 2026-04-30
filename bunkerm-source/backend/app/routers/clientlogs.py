"""
Router ClientLogs: eventos de conexión/desconexión y actividad de clientes MQTT.
"""
from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, Set

from fastapi import APIRouter, Security, status
from sqlalchemy import desc, select
from sqlalchemy.orm import sessionmaker

from clientlogs.activity_storage import client_activity_storage
from core.auth import get_api_key
from core.config import settings
from core.sync_database import create_sync_engine_for_url
from monitor.data_storage import PERIODS as _STORAGE_PERIODS
from monitor.topic_history_storage import topic_history_storage
from models.orm import ClientMQTTEvent
from services import broker_desired_state_service as desired_state_svc
from services.clientlogs_service import mqtt_monitor, MQTTEvent, get_clientlogs_source_status
from services.monitor_service import mqtt_stats

router = APIRouter(prefix="/api/v1/clientlogs", tags=["clientlogs"])

_SYNTHETIC_INTERNAL_MONITOR_CLIENT_ID = "bunkerm-mqtt-monitor"


def _synthesize_internal_admin_event() -> MQTTEvent | None:
    if not getattr(mqtt_stats, "_is_connected", False):
        return None

    admin_username = os.getenv("MOSQUITTO_ADMIN_USERNAME") or settings.mqtt_username or "admin"
    last_conn = mqtt_monitor._last_connection_info.get(admin_username, {})
    event_timestamp = last_conn.get("timestamp") or datetime.now(timezone.utc).isoformat()

    return MQTTEvent(
        id=str(uuid.uuid4()),
        timestamp=event_timestamp,
        event_type="Client Connection",
        client_id=_SYNTHETIC_INTERNAL_MONITOR_CLIENT_ID,
        details="Connected via internal broker monitor",
        status="success",
        protocol_level="MQTT v5.0",
        clean_session=True,
        keep_alive=60,
        username=admin_username,
        ip_address=last_conn.get("ip_address", "127.0.0.1"),
        port=int(last_conn.get("port", 1901) or 1901),
    )


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

    connected_limit = max(
        int(mqtt_stats.get_client_counters().get("connected", 0) or 0),
        1 if getattr(mqtt_stats, "_is_connected", False) else 0,
    )
    synthetic_admin = None
    if connected_limit > len(result):
        admin_username = os.getenv("MOSQUITTO_ADMIN_USERNAME") or settings.mqtt_username or "admin"
        has_admin_connection = any(event.username == admin_username for event in result.values())
        if not has_admin_connection:
            synthetic_admin = _synthesize_internal_admin_event()
            if synthetic_admin is not None:
                result[synthetic_admin.client_id] = synthetic_admin

    if connected_limit <= 0 or len(result) <= connected_limit:
        return result

    anchored_client_ids = list(mqtt_monitor.connected_clients.keys())
    trimmed: Dict[str, MQTTEvent] = {
        client_id: result[client_id]
        for client_id in anchored_client_ids
        if client_id in result
    }
    remaining_slots = max(0, connected_limit - len(trimmed))

    inferred_client_ids = [
        client_id for client_id in result.keys()
        if client_id not in trimmed
    ]
    inferred_client_ids.sort(key=lambda client_id: mqtt_monitor._last_seen.get(client_id, 0.0), reverse=True)

    for client_id in inferred_client_ids[:remaining_slots]:
        trimmed[client_id] = result[client_id]

    return trimmed


def build_activity_summary(window_seconds: int = 600) -> Dict[str, int]:
    """Count active clients with effective subscribe/publish capability."""
    active_clients = _active_client_events(window_seconds=window_seconds)
    capability_map = _build_client_capability_map()

    subscribed_clients = 0
    publisher_clients = 0
    seen_usernames: Set[str] = set()

    for event in active_clients.values():
        username = event.username
        if not username or username in seen_usernames:
            continue
        seen_usernames.add(username)
        activity_key = mqtt_monitor._activity_client_key(event.client_id, username)
        caps = capability_map.get(username)

        if caps is None:
            if activity_key in mqtt_monitor._subscriber_clients_seen:
                subscribed_clients += 1
            if activity_key in mqtt_monitor._publisher_clients_seen:
                publisher_clients += 1
            continue

        if caps.get("subscribe", False):
            subscribed_clients += 1
        if caps.get("publish", False):
            publisher_clients += 1

    return {
        "subscribed_clients": subscribed_clients,
        "publisher_clients": publisher_clients,
        "window_seconds": window_seconds,
    }


def _build_client_capability_map() -> Dict[str, Dict[str, bool]]:
    try:
        return desired_state_svc.get_cached_observed_dynsec_capability_map()
    except Exception:
        return {}


@router.get("/clients")
async def get_clients_list(
    page: int = 1,
    limit: int = 50,
    search: str = "",
    exact: bool = False,
    api_key: str = Security(get_api_key),
):
    """Devuelve lista paginada de clientes con su último evento registrado."""
    try:
        index = desired_state_svc.get_cached_observed_dynsec_index()
        client_activity_storage.reconcile_dynsec_clients_throttled(index.get("client_lookup", {}).values())
    except Exception:
        pass
    return client_activity_storage.get_clients_list(page=page, limit=limit, search=search, exact=exact)


@router.get("/events")
async def get_mqtt_events(limit: int = 1000, api_key: str = Security(get_api_key)):
    """Devuelve los eventos MQTT más recientes desde la base de datos (conexión, desconexión, auth failure, etc.)."""
    try:
        # Try to read from database first
        db_url = settings.resolved_history_database_url
        engine = create_sync_engine_for_url(db_url)
        session_factory = sessionmaker(bind=engine)
        
        with session_factory() as session:
            rows = session.execute(
                select(ClientMQTTEvent)
                .order_by(desc(ClientMQTTEvent.event_ts))
                .limit(limit)
            ).scalars().all()
            
            events = []
            for row in rows:
                event = MQTTEvent(
                    id=row.event_id,
                    timestamp=row.event_ts.isoformat().replace('+00:00', 'Z') if row.event_ts else '',
                    event_type=row.event_type,
                    client_id=row.client_id,
                    details=row.details,
                    status=row.status,
                    protocol_level=row.protocol_level or 'MQTT vunknown',
                    clean_session=row.clean_session or False,
                    keep_alive=row.keep_alive or 0,
                    username=row.username or 'unknown',
                    ip_address=row.ip_address or 'unknown',
                    port=row.port or 0,
                    topic=row.topic,
                    qos=row.qos,
                    payload_bytes=row.payload_bytes,
                    retained=row.retained,
                    disconnect_kind=row.disconnect_kind,
                    reason_code=row.reason_code,
                )
                events.append(event)
            
            return {"events": [event.model_dump() for event in events]}
    except Exception as exc:
        # Fallback to in-memory events if database read fails
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
async def get_top_subscribed(limit: int = 15, period: str = "7d", api_key: str = Security(get_api_key)):
    """Devuelve los tópicos con más eventos de suscripción dentro de la ventana pedida."""
    if period not in _STORAGE_PERIODS:
        from fastapi import HTTPException
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Invalid period '{period}'. Valid: {list(_STORAGE_PERIODS.keys())}")
    data = topic_history_storage.get_top_subscribed(limit=limit, period=period)
    if data["total_distinct_subscribed"] == 0:
        counts = mqtt_monitor._subscription_counts
        top = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:limit]
        return {
            "top_subscribed": [{"topic": t, "count": c} for t, c in top],
            "total_distinct_subscribed": len(counts),
        }
    return data


@router.get("/activity-summary")
async def get_activity_summary(window_seconds: int = 600, api_key: str = Security(get_api_key)):
    """Devuelve clientes activos con capacidad efectiva de subscribe o publish según DynSec."""
    return build_activity_summary(window_seconds=window_seconds)


@router.get("/source-status")
async def get_source_status(api_key: str = Security(get_api_key)):
    """Expone el estado operativo de las fuentes que alimentan ClientLogs."""
    return {"sources": get_clientlogs_source_status()}


@router.get("/activity/{username}")
async def get_client_activity(username: str, days: int = 30, limit: int = 200,
                              api_key: str = Security(get_api_key)):
    """Devuelve auditoría persistida reciente de un cliente MQTT."""
    try:
        index = desired_state_svc.get_cached_observed_dynsec_index()
        client_activity_storage.reconcile_dynsec_clients_throttled(index.get("client_lookup", {}).values())
    except Exception:
        pass
    return client_activity_storage.get_client_activity(username=username, days=days, limit=limit)
