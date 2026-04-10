"""
Router ClientLogs: eventos de conexión/desconexión y actividad de clientes MQTT.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Dict

from fastapi import APIRouter, Security, status

from core.auth import get_api_key
from services.clientlogs_service import mqtt_monitor, MQTTEvent

router = APIRouter(prefix="/api/v1/clientlogs", tags=["clientlogs"])


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
    result: Dict[str, MQTTEvent] = dict(mqtt_monitor.connected_clients)
    cutoff = time.time() - 600
    for cid, last_ts in mqtt_monitor._last_seen.items():
        if last_ts < cutoff or cid in result:
            continue
        username, protocol_level, ip, port, clean, keep_alive = mqtt_monitor._get_client_info(cid)
        if mqtt_monitor._is_admin(username):
            continue
        last_conn = mqtt_monitor._last_connection_info.get(username, {})
        synthetic = MQTTEvent(
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
        result[cid] = synthetic
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
