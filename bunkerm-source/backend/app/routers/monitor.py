"""
Router Monitor: métricas del broker MQTT, alertas y publicación de mensajes.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Security, status
from fastapi.responses import JSONResponse

from core.auth import get_api_key
from monitor.data_storage import PERIODS as _STORAGE_PERIODS
from monitor.topic_history_storage import topic_history_storage
from models.schemas import AlertConfigUpdate, PublishRequest
from routers.clientlogs import build_activity_summary
from services import broker_observability_client
from services.monitor_service import (
    alert_engine,
    mqtt_stats,
    nonce_manager,
    read_alert_config,
    record_user_publish,
    save_alert_config,
    topic_store,
    mqtt_client_instance,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/monitor", tags=["monitor"])


# ---------------------------------------------------------------------------
# Estadísticas del broker
# ---------------------------------------------------------------------------

@router.get("/stats")
async def get_mqtt_stats(request: Request, nonce: str, timestamp: float,
                         api_key: str = Security(get_api_key)):
    """Estadísticas MQTT completas con validación de nonce anti-replay."""
    if not nonce_manager.validate(nonce, timestamp):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Invalid nonce or timestamp")
    try:
        stats = mqtt_stats.get_stats()
        stats.update(build_activity_summary(window_seconds=600))
        stats["mqtt_connected"] = mqtt_stats._is_connected
        if not mqtt_stats._is_connected:
            broker = os.getenv("MOSQUITTO_IP", "127.0.0.1")
            port   = os.getenv("MOSQUITTO_PORT", "1900")
            stats["connection_error"] = f"MQTT broker connection failed on {broker}:{port}"
    except Exception as exc:
        logger.error("Error en get_stats: %s", exc)
        stats = {
            "mqtt_connected": False,
            "connection_error": str(exc),
            "total_connected_clients": 0,
            "total_messages_received": "0",
            "total_subscriptions": 0,
            "retained_messages": 0,
            "messages_history": [0] * 15,
            "published_history": [0] * 15,
            "bytes_stats": {"timestamps": [], "bytes_received": [], "bytes_sent": []},
            "daily_message_stats": {"dates": [], "counts": []},
            "subscribed_clients": 0,
            "publisher_clients": 0,
        }
    return JSONResponse(content=stats)


@router.get("/stats/bytes")
async def get_bytes_for_period(period: str = "1h",
                               api_key: str = Security(get_api_key)):
    """Historial de bytes recibidos/enviados para el período indicado."""
    if period not in _STORAGE_PERIODS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Invalid period '{period}'. Valid: {list(_STORAGE_PERIODS.keys())}")
    return mqtt_stats.data_storage.get_bytes_for_period(period)


@router.get("/stats/messages")
async def get_messages_for_period(period: str = "1h",
                                  api_key: str = Security(get_api_key)):
    """Historial de mensajes recibidos/enviados para el período indicado."""
    if period not in _STORAGE_PERIODS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Invalid period '{period}'. Valid: {list(_STORAGE_PERIODS.keys())}")
    return mqtt_stats.data_storage.get_messages_for_period(period)


@router.get("/stats/daily-summary")
async def get_daily_summary(days: int = 7,
                            api_key: str = Security(get_api_key)):
    """Resumen diario persistido del broker para reporting operativo."""
    days = max(1, min(days, 365))
    return mqtt_stats.data_storage.get_daily_summary(days=days)


@router.get("/stats/topology")
async def get_topology_stats(limit: int = 15, period: str = "7d", api_key: str = Security(get_api_key)):
    """Top tópicos por conteo de mensajes y churn de clientes."""
    if period not in _STORAGE_PERIODS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Invalid period '{period}'. Valid: {list(_STORAGE_PERIODS.keys())}")
    data = topic_history_storage.get_top_published(limit=limit, period=period)
    if data["total_distinct_topics"] == 0:
        all_topics = topic_store.get_all()
        user_topics = [t for t in all_topics if not t["topic"].startswith("$")]
        data = {
            "top_topics": sorted(user_topics, key=lambda x: x.get("count", 0), reverse=True)[:limit],
            "total_distinct_topics": len(user_topics),
        }
    client_counts = mqtt_stats.get_client_counters()
    return {
        "top_topics": data["top_topics"],
        "total_distinct_topics": data["total_distinct_topics"],
        "clients_disconnected": client_counts["disconnected"],
        "clients_expired": client_counts["expired"],
    }


@router.get("/stats/health")
async def get_health_stats(api_key: str = Security(get_api_key)):
    """Tasas de carga y latencia round-trip del broker."""
    with mqtt_stats._lock:
        return {
            "load_msg_rx_1min":      round(mqtt_stats.load_msg_rx_1min, 2),
            "load_msg_tx_1min":      round(mqtt_stats.load_msg_tx_1min, 2),
            "load_bytes_rx_1min":    round(mqtt_stats.load_bytes_rx_1min, 2),
            "load_bytes_tx_1min":    round(mqtt_stats.load_bytes_tx_1min, 2),
            "load_connections_1min": round(mqtt_stats.load_connections_1min, 2),
            "latency_ms":            mqtt_stats.latency_ms,
        }


@router.get("/stats/resources")
async def get_resource_stats(api_key: str = Security(get_api_key)):
    """Recursos del broker Mosquitto desde cgroups o fallback local."""
    broker_stats = {}
    source = {
        "enabled": True,
        "available": False,
        "mode": "broker-observability-service",
        "lastError": None,
    }

    try:
        observability_payload = await broker_observability_client.fetch_broker_resource_stats()
        broker_stats = observability_payload.get("stats") or {}
        source = observability_payload.get("source") or source
    except broker_observability_client.BrokerObservabilityUnavailable as exc:
        source["lastError"] = str(exc)

    if broker_stats:
        return {
            "mosquitto_cpu_pct": broker_stats.get("cpu_pct"),
            "mosquitto_rss_bytes": broker_stats.get("memory_bytes"),
            "mosquitto_vms_bytes": None,
            "mosquitto_memory_limit_bytes": broker_stats.get("memory_limit_bytes"),
            "mosquitto_memory_pct": broker_stats.get("memory_pct"),
            "mosquitto_cpu_limit_cores": broker_stats.get("cpu_limit_cores"),
            "resource_timestamp": broker_stats.get("timestamp"),
            "source": source,
        }

    cpu_pct = None
    try:
        import psutil
        procs = [p for p in psutil.process_iter(["name", "cpu_percent"])
                 if "mosquitto" in (p.info.get("name") or "")]
        if procs:
            cpu_pct = round(procs[0].cpu_percent(interval=0.1), 1)
    except Exception as exc:
        logger.warning("Resource stats error: %s", exc)
    with mqtt_stats._lock:
        heap_cur = mqtt_stats.heap_current
        heap_max = mqtt_stats.heap_maximum
    return {
        "mosquitto_cpu_pct":   cpu_pct,
        "mosquitto_rss_bytes": heap_cur if heap_cur > 0 else None,
        "mosquitto_vms_bytes": heap_max if heap_max > 0 else None,
        "mosquitto_memory_limit_bytes": None,
        "mosquitto_memory_pct": None,
        "mosquitto_cpu_limit_cores": None,
        "resource_timestamp": None,
        "source": {
            **source,
            "mode": "fallback-process" if cpu_pct is not None or heap_cur > 0 or heap_max > 0 else "unavailable",
        },
    }


@router.get("/stats/resources/source-status")
async def get_resource_source_status(api_key: str = Security(get_api_key)):
    """Expone el estado operativo de la fuente compartida de resource stats del broker."""
    try:
        return await broker_observability_client.fetch_broker_resource_source_status()
    except broker_observability_client.BrokerObservabilityUnavailable as exc:
        return {
            "source": {
                "enabled": True,
                "available": False,
                "mode": "broker-observability-service",
                "lastError": str(exc),
            }
        }


@router.get("/stats/qos")
async def get_qos_stats(api_key: str = Security(get_api_key)):
    """Métricas de mensajes en vuelo y almacenados."""
    client_counts = mqtt_stats.get_client_counters()
    with mqtt_stats._lock:
        total_rx       = mqtt_stats.messages_received_total
        total_retained = mqtt_stats.retained_messages
        return {
            "messages_inflight":    mqtt_stats.messages_inflight,
            "messages_stored":      mqtt_stats.messages_stored,
            "messages_store_bytes": mqtt_stats.messages_store_bytes,
            "clients_disconnected": client_counts["disconnected"],
            "clients_expired":      client_counts["expired"],
            "retained_ratio":       round(total_retained / max(total_rx, 1) * 100, 1),
        }


# ---------------------------------------------------------------------------
# Tópicos
# ---------------------------------------------------------------------------

@router.get("/topics")
async def get_topics(source: str = "auto", api_key: str = Security(get_api_key)):
    # source=db fuerza la lectura desde PostgreSQL para no depender de memoria.
    try:
        topics = topic_history_storage.get_latest_topics(limit=5000)
        if source == "db":
            return {"topics": topics}
        if topics:
            return {"topics": topics}
    except Exception as exc:
        logger.warning("No se pudo leer topic_registry/topic_message_events: %s", exc)
        if source == "db":
            return {"topics": []}
    return {"topics": topic_store.get_all()}


@router.get("/topics/{topic_path:path}/history")
async def get_topic_history(topic_path: str, limit: int = 120, api_key: str = Security(get_api_key)):
    topic = (topic_path or "").strip()
    if not topic:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Topic is required")
    return topic_history_storage.get_topic_messages(topic=topic, limit=limit)


# ---------------------------------------------------------------------------
# Alertas
# ---------------------------------------------------------------------------

@router.get("/alerts/broker")
async def get_broker_alerts(api_key: str = Security(get_api_key)):
    return {"alerts": alert_engine.get_alerts()}


@router.get("/alerts/broker/history")
async def get_broker_alert_history(api_key: str = Security(get_api_key)):
    history = list(reversed(alert_engine.get_history()))
    return {"history": history, "total": len(history)}


@router.post("/alerts/broker/{alert_id}/acknowledge")
async def acknowledge_broker_alert(alert_id: str, api_key: str = Security(get_api_key)):
    if alert_engine.acknowledge(alert_id):
        return {"status": "acknowledged"}
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")


@router.get("/alerts/config")
async def get_alert_config_endpoint(api_key: str = Security(get_api_key)):
    import services.monitor_service as _svc
    _svc._alert_config_ts = 0.0  # fuerza recarga del caché
    return read_alert_config()


@router.put("/alerts/config")
async def update_alert_config(body: AlertConfigUpdate, api_key: str = Security(get_api_key)):
    current = read_alert_config()
    updated = {**current, **{k: v for k, v in body.model_dump().items() if v is not None}}
    if updated.get("broker_down_grace_polls", 1) < 1:
        updated["broker_down_grace_polls"] = 1
    cap_pct = updated.get("client_capacity_pct", 80.0)
    if not (1.0 <= cap_pct <= 100.0):
        raise HTTPException(status_code=422,
                            detail="client_capacity_pct must be between 1 and 100")
    if updated.get("reconnect_loop_count", 2) < 2:
        updated["reconnect_loop_count"] = 2
    if updated.get("auth_fail_count", 2) < 2:
        updated["auth_fail_count"] = 2
    save_alert_config(updated)
    return {"status": "saved", "config": updated}


# ---------------------------------------------------------------------------
# Publicar mensajes
# ---------------------------------------------------------------------------

@router.post("/publish")
async def publish_message(body: PublishRequest, api_key: str = Security(get_api_key)):
    """Publica un mensaje al broker MQTT."""
    import services.monitor_service as _svc
    client = _svc.mqtt_client_instance
    if client is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="MQTT client not connected")
    result = client.publish(body.topic, body.payload, qos=body.qos, retain=body.retain)
    if result.rc != 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Publish failed (rc={result.rc})")
    record_user_publish(
        body.topic,
        body.payload.encode("utf-8"),
        retained=body.retain,
        qos=body.qos,
        source="api-publish",
    )
    return {"status": "published", "topic": body.topic}


# ---------------------------------------------------------------------------
# Test / diagnóstico
# ---------------------------------------------------------------------------

@router.get("/test/mqtt-stats")
async def test_mqtt_stats(api_key: str = Security(get_api_key)):
    return {
        "messages_sent":               mqtt_stats.messages_sent,
        "subscriptions":               mqtt_stats.subscriptions,
        "connected_clients":           mqtt_stats.connected_clients,
        "data_storage_initialized":    hasattr(mqtt_stats, "data_storage"),
    }


@router.get("/test/storage")
async def test_storage(api_key: str = Security(get_api_key)):
    return {
        "file_exists": os.path.exists(mqtt_stats.data_storage.filename),
        "data":        mqtt_stats.data_storage.load_data(),
    }


@router.get("/health")
async def health():
    return {"status": "healthy"}
