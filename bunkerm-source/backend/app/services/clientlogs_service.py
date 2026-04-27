"""
Servicio de monitoreo de logs de clientes MQTT.
Extrae la clase MQTTMonitor y las funciones de fondo de clientlogs/main.py.
Estas funciones se ejecutan como hilos daemon, iniciados desde el lifespan del app principal.
"""
from __future__ import annotations

import logging
import os
import re
import time
import uuid
import threading
from collections import deque
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel
from sqlalchemy.orm import sessionmaker

from clientlogs.activity_storage import client_activity_storage
from core.config import settings
from core.sync_database import create_sync_engine_for_url, session_scope
from monitor.topic_history_storage import topic_history_storage
from models.orm import ClientMQTTEvent
from services import broker_observability_client


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes y patrones regex
# ---------------------------------------------------------------------------

# Regex para IDs de cliente generados automáticamente por mosquitto_ctrl
_AUTO_CLIENT_RE = re.compile(
    r"^auto-[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$"
)
_GREENHOUSE_CLIENT_RE = re.compile(r"^greenhouse-(?:publisher|subscriber)-(\d+)$")
_PLATFORM_INTERNAL_CLIENT_IDS = frozenset({
    "bunkerm-mqtt-monitor",
    "bunkerm-publish-monitor",
    "mqtt-monitor",
})

_MOSQUITTO_LOG_KEYWORDS = frozenset([
    "New", "Sending", "Received", "Client", "Warning", "Config",
    "Loading", "Opening", "No", "mosquitto", "Error", "Notice",
    "Socket", "Timeout", "Plugin", "Saving", "Using", "Log",
    "Restored", "Bridge", "Persistence", "TLS", "Websockets", "Info:",
])

# Captura timestamps Unix (dígitos) e ISO 8601 (Mosquitto 2.1.2)
_TS_CAPTURE = r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}|\d+)"
_TS_RE      = re.compile(r"^(?:\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}|\d+)$")

# Ventana de deduplicación temporal de eventos Publish (en segundos) - 0 = deshabilitada
_PUBLISH_DEDUP_SECONDS = 0

# Prefijos de tópicos internos de la plataforma que no se muestran en la UI
_INTERNAL_TOPIC_PREFIXES = ("$", "bunkerm/monitor/")


def _ts_to_iso(ts: str) -> str:
    """Convierte timestamp Unix o ISO 8601 a cadena ISO 8601 UTC."""
    if ts.isdigit():
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
    try:
        dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S")
        return dt.replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        return ts


def _ts_to_epoch(ts: str) -> float:
    """Convierte timestamp Unix o ISO 8601 a epoch UTC."""
    if ts.isdigit():
        return float(int(ts))
    try:
        dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S")
        return dt.replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return time.time()


# ---------------------------------------------------------------------------
# Modelo interno de evento MQTT (no es schema de API directamente)
# ---------------------------------------------------------------------------

class MQTTEvent(BaseModel):
    id: str
    timestamp: str
    event_type: str
    client_id: str
    details: str
    status: str
    protocol_level: str
    clean_session: bool
    keep_alive: int
    username: str
    ip_address: str
    port: int
    topic: Optional[str] = None
    qos: Optional[int] = None
    payload_bytes: Optional[int] = None
    retained: Optional[bool] = None
    disconnect_kind: Optional[str] = None


# ---------------------------------------------------------------------------
# Persistencia de eventos en BD
# ---------------------------------------------------------------------------

_db_engine = None
_db_session_factory = None
_db_lock = threading.Lock()


def _get_db_session_factory():
    """Lazy initialization del session factory."""
    global _db_engine, _db_session_factory
    if _db_session_factory is None:
        with _db_lock:
            if _db_session_factory is None:
                db_url = settings.resolved_control_plane_database_url
                _db_engine = create_sync_engine_for_url(db_url)
                _db_session_factory = sessionmaker(bind=_db_engine, expire_on_commit=False)
    return _db_session_factory


def persist_mqtt_event(event: MQTTEvent) -> None:
    """Guarda un evento MQTT en la base de datos (async-safe)."""
    try:
        session_factory = _get_db_session_factory()
        with session_scope(session_factory) as session:
            db_event = ClientMQTTEvent(
                event_id=event.id,
                timestamp=datetime.fromisoformat(event.timestamp.replace('Z', '+00:00')) if isinstance(event.timestamp, str) else event.timestamp,
                event_type=event.event_type,
                client_id=event.client_id,
                username=event.username,
                ip_address=event.ip_address,
                port=event.port,
                protocol_level=event.protocol_level,
                clean_session=event.clean_session,
                keep_alive=event.keep_alive,
                status=event.status,
                details=event.details,
                topic=event.topic,
                qos=event.qos,
                payload_bytes=event.payload_bytes,
                retained=event.retained,
                disconnect_kind=event.disconnect_kind,
            )
            session.add(db_event)
            session.commit()
    except Exception as exc:
        logger.warning("Failed to persist MQTT event to database: %s", exc)


# ---------------------------------------------------------------------------
# Monitor de clientes MQTT
# ---------------------------------------------------------------------------

class MQTTMonitor:
    def __init__(self):
        self.connected_clients: Dict[str, MQTTEvent] = {}
        self.events: deque = deque(maxlen=1000)
        self._subscription_counts: Dict[str, int] = {}
        self._last_seen: Dict[str, float] = {}
        self._subscriber_clients_seen: Dict[str, float] = {}
        self._publisher_clients_seen: Dict[str, float] = {}
        self._pending_ip: Dict[str, Tuple[str, int]] = {}
        self._last_connection_info: Dict[str, dict] = {}
        self._last_publish_ts: Dict[str, float] = {}
        self._client_usernames: Dict[str, str] = {}
        self._pending_subscribe_client: Optional[Tuple[str, str]] = None

    # ── helpers ──────────────────────────────────────────────────────────────

    def _get_client_info(self, client_id: str) -> Tuple[str, str, str, int, bool, int]:
        """Devuelve (username, protocol, ip, port, clean_session, keep_alive)."""
        if client_id in self.connected_clients:
            ev = self.connected_clients[client_id]
            return ev.username, ev.protocol_level, ev.ip_address, ev.port, ev.clean_session, ev.keep_alive
        if client_id in self._client_usernames:
            username = self._client_usernames[client_id]
            last_conn = self._last_connection_info.get(username, {})
            return (
                username,
                "MQTT vunknown",
                last_conn.get("ip_address", "unknown"),
                last_conn.get("port", 0),
                False,
                0,
            )
        inferred_username = self._infer_username_from_client_id(client_id)
        if inferred_username:
            self._client_usernames[client_id] = inferred_username
            last_conn = self._last_connection_info.get(inferred_username, {})
            return (
                inferred_username,
                "MQTT vunknown",
                last_conn.get("ip_address", "unknown"),
                last_conn.get("port", 0),
                False,
                0,
            )
        return "unknown", "MQTT vunknown", "unknown", 0, False, 0

    def _infer_username_from_client_id(self, client_id: str) -> Optional[str]:
        match = _GREENHOUSE_CLIENT_RE.match(client_id)
        if not match:
            return None
        return str(int(match.group(1)))

    def _is_admin(self, username: str) -> bool:
        return username == os.getenv("MOSQUITTO_ADMIN_USERNAME", settings.mqtt_username)

    def _is_internal_auto_client(self, client_id: str) -> bool:
        return bool(_AUTO_CLIENT_RE.match(client_id))

    def _is_platform_internal_client(self, client_id: str) -> bool:
        return client_id in _PLATFORM_INTERNAL_CLIENT_IDS

    def _activity_client_key(self, client_id: str, username: str) -> str:
        if username and username not in ("unknown", "(broker-observed)"):
            return username
        return client_id

    def get_activity_summary(self, window_seconds: int = 600) -> Dict[str, int]:
        cutoff = time.time() - max(1, window_seconds)
        return {
            "subscribed_clients": sum(1 for seen_at in self._subscriber_clients_seen.values() if seen_at >= cutoff),
            "publisher_clients": sum(1 for seen_at in self._publisher_clients_seen.values() if seen_at >= cutoff),
            "window_seconds": window_seconds,
        }

    # ── parsers individuales ──────────────────────────────────────────────────

    def _parse_raw_new_connection(self, log_line: str) -> bool:
        m = re.match(_TS_CAPTURE + r": New connection from (\d+\.\d+\.\d+\.\d+):(\d+) on port", log_line)
        if not m:
            return False
        ts, ip, port = m.groups()
        self._pending_ip[ts] = (ip, int(port))
        if len(self._pending_ip) > 50:
            del self._pending_ip[min(self._pending_ip)]
        return True

    def parse_connection_log(self, log_line: str) -> Optional[MQTTEvent]:
        pattern = (
            _TS_CAPTURE
            + r": New client connected from (\d+\.\d+\.\d+\.\d+):(\d+)"
            r" as (\S+) \(p(\d+), c(\d+), k(\d+)(?:, u'([^']+)')?\)"
        )
        m = re.match(pattern, log_line)
        if not m:
            return None

        ts, ip, port, client_id, protocol, clean, keep_alive, username = m.groups()
        if username is None:
            username = client_id
        protocol_versions = {"3": "3.1", "4": "3.1.1", "5": "5.0"}

        event = MQTTEvent(
            id=str(uuid.uuid4()),
            timestamp=_ts_to_iso(ts),
            event_type="Client Connection",
            client_id=client_id,
            details=f"Connected from {ip}:{port}",
            status="success",
            protocol_level=f"MQTT v{protocol_versions.get(protocol, 'unknown')}",
            clean_session=clean == "1",
            keep_alive=int(keep_alive),
            username=username,
            ip_address=ip,
            port=int(port),
        )

        if len(self._client_usernames) > 2000:
            for k in list(self._client_usernames.keys())[:200]:
                del self._client_usernames[k]
        self._client_usernames[client_id] = username
        self._pending_ip.pop(ts, None)
        self._last_connection_info[username] = {
            "ip_address": ip,
            "port": int(port),
            "timestamp": event.timestamp,
        }
        if self._is_admin(username) and self._is_internal_auto_client(client_id):
            return None
        self.connected_clients[client_id] = event
        return event

    def parse_disconnection_log(self, log_line: str) -> Optional[MQTTEvent]:
        if "not authorised" in log_line:
            return None
        m = re.match(
            _TS_CAPTURE + r": Client (\S+)(?: \[[^\]]+\])? (?:disconnected|closed its connection)",
            log_line,
        )
        if not m:
            return None
        ts, client_id = m.groups()
        if client_id not in self.connected_clients:
            return None
        conn = self.connected_clients[client_id]
        disconnect_kind = "graceful" if "closed its connection" in log_line else "ungraceful"
        event = MQTTEvent(
            id=str(uuid.uuid4()),
            timestamp=_ts_to_iso(ts),
            event_type="Client Disconnection",
            client_id=client_id,
            details=f"Disconnected from {conn.ip_address}:{conn.port}",
            status="warning",
            protocol_level=conn.protocol_level,
            clean_session=conn.clean_session,
            keep_alive=conn.keep_alive,
            username=conn.username,
            ip_address=conn.ip_address,
            port=conn.port,
            disconnect_kind=disconnect_kind,
        )
        del self.connected_clients[client_id]
        self._last_seen.pop(client_id, None)
        return event

    def parse_auth_failure_log(self, log_line: str) -> Optional[MQTTEvent]:
        m = re.match(
            _TS_CAPTURE
            + r": Client (\S+)(?: \[(\d+\.\d+\.\d+\.\d+):(\d+)\])? disconnected: not authorised\.",
            log_line,
        )
        if not m:
            return None
        ts, client_id, ip_bracket, port_bracket = m.groups()
        if ip_bracket:
            ip, port = ip_bracket, int(port_bracket)
        else:
            ip, port = self._pending_ip.pop(ts, ("unknown", 0))
        return MQTTEvent(
            id=str(uuid.uuid4()),
            timestamp=_ts_to_iso(ts),
            event_type="Auth Failure",
            client_id=client_id,
            details=f"Auth refused from {ip}:{port}",
            status="error",
            protocol_level="MQTT vunknown",
            clean_session=False,
            keep_alive=0,
            username="unknown",
            ip_address=ip,
            port=port,
            disconnect_kind="auth_failure",
        )

    def parse_subscription_log(self, log_line: str) -> Optional[MQTTEvent]:
        header_match = re.match(_TS_CAPTURE + r": Received SUBSCRIBE from (\S+)$", log_line)
        if header_match:
            ts_str, client_id = header_match.groups()
            self._pending_subscribe_client = (ts_str, client_id)
            return None

        detail_match = re.match(_TS_CAPTURE + r":\s+(.+) \(QoS (\d)\)$", log_line)
        if detail_match and self._pending_subscribe_client is not None:
            detail_ts, topic, qos_str = detail_match.groups()
            header_ts, client_id = self._pending_subscribe_client
            if detail_ts == header_ts:
                return self._record_subscribe_event(header_ts, client_id, qos_str, topic)

        if ": " not in log_line:
            self._pending_subscribe_client = None
            return None
        ts_str, content = log_line.split(": ", 1)
        if not _TS_RE.match(ts_str):
            self._pending_subscribe_client = None
            return None
        parts = content.split()
        if len(parts) != 3:
            if not content.startswith("Received SUBSCRIBE from "):
                self._pending_subscribe_client = None
            return None
        client_id, qos_str, topic = parts
        if qos_str not in ("0", "1", "2"):
            self._pending_subscribe_client = None
            return None
        if client_id in _MOSQUITTO_LOG_KEYWORDS:
            self._pending_subscribe_client = None
            return None
        return self._record_subscribe_event(ts_str, client_id, qos_str, topic)

    def _record_subscribe_event(self, ts_str: str, client_id: str, qos_str: str, topic: str) -> Optional[MQTTEvent]:
        username, protocol_level, ip, port, clean, keep_alive = self._get_client_info(client_id)
        event_ts = _ts_to_epoch(ts_str)
        event = MQTTEvent(
            id=str(uuid.uuid4()),
            timestamp=_ts_to_iso(ts_str),
            event_type="Subscribe",
            client_id=client_id,
            details=f"Subscribed to {topic} (QoS {qos_str})",
            status="info",
            protocol_level=protocol_level,
            clean_session=clean,
            keep_alive=keep_alive,
            username=username,
            ip_address=ip,
            port=port,
            topic=topic,
            qos=int(qos_str),
        )
        self._subscription_counts[topic] = self._subscription_counts.get(topic, 0) + 1
        self._last_seen[client_id] = event_ts
        self._subscriber_clients_seen[self._activity_client_key(client_id, username)] = event_ts
        self._pending_subscribe_client = None
        return event

    def parse_publish_log(self, log_line: str) -> Optional[MQTTEvent]:
        """Parse PUBLISH with extreme flexibility - use search() not match()"""
        if "Received PUBLISH from" not in log_line:
            return None
        
        # Extraer timestamp (al inicio de la línea)
        ts_match = re.search(_TS_CAPTURE, log_line)
        if not ts_match:
            return None
        ts = ts_match.group(1)
        
        # Extraer client_id (texto después de "from")
        client_match = re.search(r"Received PUBLISH from (\S+)", log_line)
        if not client_match:
            logger.warning(f"Could not extract client_id from PUBLISH: {log_line[:80]}")
            return None
        client_id = client_match.group(1)
        
        # Extraer tópico (entre comillas simples)
        topic_match = re.search(r"'([^']+)'", log_line)
        if not topic_match:
            logger.warning(f"Could not extract topic from PUBLISH: {log_line[:80]}")
            return None
        topic = topic_match.group(1)
        
        # Extraer QoS (q seguido de dígito)
        qos_match = re.search(r"q(\d)", log_line)
        qos_str = qos_match.group(1) if qos_match else "0"
        
        # Extraer bytes
        bytes_match = re.search(r"\((\d+) bytes\)", log_line)
        size_str = bytes_match.group(1) if bytes_match else "0"
        retained_match = re.search(r"r(\d)", log_line)
        retained_bool = bool(int(retained_match.group(1))) if retained_match else False
        
        # Skip internal topics
        if any(topic.startswith(p) for p in _INTERNAL_TOPIC_PREFIXES):
            return None
        
        username, protocol_level, ip, port, clean, keep_alive = self._get_client_info(client_id)
        event_ts = _ts_to_epoch(ts)
        self._publisher_clients_seen[self._activity_client_key(client_id, username)] = event_ts
        
        # Deduplication check
        key = topic
        now_ts = event_ts
        if key in self._last_publish_ts and now_ts - self._last_publish_ts[key] < _PUBLISH_DEDUP_SECONDS:
            return None
        self._last_publish_ts[key] = now_ts
        
        return MQTTEvent(
            id=str(uuid.uuid4()),
            timestamp=_ts_to_iso(ts),
            event_type="Publish",
            client_id=client_id,
            details=f"Published to {topic} ({size_str} B, QoS {qos_str})",
            status="info",
            protocol_level=protocol_level,
            clean_session=clean,
            keep_alive=keep_alive,
            username=username,
            ip_address=ip,
            port=port,
            topic=topic,
            qos=int(qos_str),
            payload_bytes=int(size_str),
            retained=retained_bool,
        )

    # ── pipeline de procesamiento ─────────────────────────────────────────────

    def process_line(self, line: str, replay: bool = False) -> None:
        """Procesa una línea del log por todos los parsers en orden de prioridad."""
        if (
            ": Sending PUBLISH to " in line
            or ": Denied PUBLISH from " in line
            or ": Sending SUBACK to "  in line
            or ": Sending PUBACK to "  in line
            or ": Received PINGREQ from "  in line
            or ": Sending PINGRESP to "   in line
        ):
            return

        if self._parse_raw_new_connection(line):
            return

        for parser in (
            self.parse_connection_log,
            self.parse_disconnection_log,
            self.parse_auth_failure_log,
            self.parse_subscription_log,
        ):
            event = parser(line)
            if event is not None:
                if parser.__name__ == "parse_subscription_log" and not replay and event.topic:
                    try:
                        topic_history_storage.record_subscribe(
                            event.topic,
                            event_ts=datetime.fromisoformat(event.timestamp),
                        )
                    except Exception as exc:
                        logger.warning("Topic subscribe history persistence failed for topic %s: %s", event.topic, exc)
                if not replay:
                    client_activity_storage.record_event(event)
                if not replay:
                    self.events.append(event)
                    persist_mqtt_event(event)
                return

        event = self.parse_publish_log(line)
        if event is not None:
            if not replay:
                client_activity_storage.record_event(event)
            if not replay:
                self.events.append(event)
                persist_mqtt_event(event)
            return


# ---------------------------------------------------------------------------
# Singleton global accesible desde el router
# ---------------------------------------------------------------------------

mqtt_monitor = MQTTMonitor()

_source_status_lock = threading.Lock()
_source_status: Dict[str, Dict[str, object]] = {
    "logTail": {
        "enabled": settings.broker_log_tail_enabled,
        "running": False,
        "available": False,
        "path": settings.broker_log_path,
        "lastError": None,
        "lastEventAt": None,
        "replayCompleted": False,
    },
    "mqttPublish": {
        "enabled": False,
        "running": False,
        "broker": settings.mosquitto_internal_host,
        "port": settings.mosquitto_internal_port,
        "lastError": "integrated_into_primary_mqtt_monitor",
        "lastEventAt": None,
        "mode": "integrated-primary-monitor",
    },
}


def _update_source_status(source_name: str, **changes: object) -> None:
    with _source_status_lock:
        state = _source_status[source_name]
        state.update(changes)


def get_clientlogs_source_status() -> Dict[str, Dict[str, object]]:
    with _source_status_lock:
        return {
            source_name: dict(source_state)
            for source_name, source_state in _source_status.items()
        }


def _remember_recent_log_signature(
    signature: str,
    recent_signatures: deque[str],
    recent_signature_set: set[str],
) -> None:
    if signature in recent_signature_set:
        return
    if len(recent_signatures) == recent_signatures.maxlen:
        evicted = recent_signatures.popleft()
        recent_signature_set.discard(evicted)
    recent_signatures.append(signature)
    recent_signature_set.add(signature)


def _process_log_snapshot(
    lines: List[str],
    *,
    replay: bool,
    recent_signatures: deque[str],
    recent_signature_set: set[str],
) -> int:
    processed = 0
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line in recent_signature_set:
            continue
        mqtt_monitor.process_line(line, replay=replay)
        _remember_recent_log_signature(line, recent_signatures, recent_signature_set)
        processed += 1
    return processed


# ---------------------------------------------------------------------------
# Funciones de fondo (se ejecutan como hilos daemon en el lifespan)
# ---------------------------------------------------------------------------

def monitor_mosquitto_logs() -> None:
    """Consume snapshots de logs vía observabilidad broker-owned y alimenta el MQTTMonitor."""
    log_file = os.getenv("BROKER_LOG_PATH", settings.broker_log_path)
    log_offset: int | None = None
    recent_signatures: deque[str] = deque(maxlen=10000)
    recent_signature_set: set[str] = set()
    poll_interval = max(settings.broker_observability_log_poll_interval_seconds, 0.5)
    snapshot_limit = max(100, min(settings.broker_observability_log_snapshot_lines, 5000))
    _update_source_status(
        "logTail",
        enabled=settings.broker_log_tail_enabled,
        path=log_file,
        running=False,
        available=False,
        replayCompleted=False,
        lastError=None,
        mode="broker-observability-service",
        endpoint=settings.broker_observability_url,
    )

    if not settings.broker_log_tail_enabled:
        print("Monitoreo de logs de Mosquitto deshabilitado por configuración.")
        _update_source_status("logTail", lastError="disabled_by_config")
        return

    print("Iniciando monitoreo de logs vía broker observability...")
    replay_completed = False
    while True:
        try:
            payload = broker_observability_client.fetch_broker_logs_sync(limit=snapshot_limit, offset=log_offset)
            source = payload.get("source") or {}
            _update_source_status(
                "logTail",
                running=True,
                available=bool(source.get("available", False)),
                path=source.get("path", log_file),
                lastError=payload.get("error") or source.get("lastError"),
            )

            if payload.get("rewound"):
                recent_signatures.clear()
                recent_signature_set.clear()

            lines = payload.get("logs") or []
            if not replay_completed:
                processed = _process_log_snapshot(
                    lines,
                    replay=True,
                    recent_signatures=recent_signatures,
                    recent_signature_set=recent_signature_set,
                )
                replay_completed = True
                _update_source_status("logTail", replayCompleted=True, lastError=None)
                print(
                    "Replay de arranque vía broker observability: "
                    f"{processed} líneas, {len(mqtt_monitor.connected_clients)} conectados, "
                    f"{len(mqtt_monitor._subscription_counts)} tópicos con suscripciones."
                )
            else:
                processed = _process_log_snapshot(
                    lines,
                    replay=False,
                    recent_signatures=recent_signatures,
                    recent_signature_set=recent_signature_set,
                )
                if processed > 0:
                    _update_source_status(
                        "logTail",
                        lastEventAt=datetime.now(tz=timezone.utc).isoformat(),
                        lastError=None,
                    )
            log_offset = payload.get("next_offset", log_offset)
        except broker_observability_client.BrokerObservabilityUnavailable as exc:
            _update_source_status(
                "logTail",
                running=False,
                available=False,
                lastError=str(exc),
            )
            print(f"Monitoreo de logs vía broker observability no disponible: {exc}")
        time.sleep(poll_interval)


def monitor_mqtt_publishes() -> None:
    _update_source_status(
        "mqttPublish",
        enabled=False,
        running=False,
        lastError="integrated_into_primary_mqtt_monitor",
        mode="integrated-primary-monitor",
    )
    return
    try:
        import paho.mqtt.client as paho_mqtt
    except ImportError:
        print("paho-mqtt no disponible; monitoreo de publishes deshabilitado.")
        _update_source_status("mqttPublish", running=False, lastError="paho_mqtt_not_available")
        return

    if not settings.broker_publish_monitor_enabled:
        print("Monitoreo MQTT de publishes deshabilitado por configuración.")
        _update_source_status("mqttPublish", running=False, lastError="disabled_by_config")
        return

    broker_host = os.getenv("MOSQUITTO_IP", settings.mqtt_broker)
    broker_port = int(os.getenv("MOSQUITTO_PORT", str(settings.mqtt_port)))
    username    = os.getenv("MOSQUITTO_ADMIN_USERNAME", settings.mqtt_username)
    password    = os.getenv("MOSQUITTO_ADMIN_PASSWORD", settings.mqtt_password)
    _update_source_status(
        "mqttPublish",
        enabled=settings.broker_publish_monitor_enabled,
        broker=broker_host,
        port=broker_port,
        running=False,
        lastError=None,
    )

    def _on_connect(client, userdata, flags, rc, properties=None):
        if rc == 0:
            client.subscribe("#", 0)
            print("Monitor de publishes MQTT: suscrito a #")
            _update_source_status("mqttPublish", running=True, lastError=None)
        else:
            print(f"Monitor de publishes MQTT: error de conexión rc={rc}")
            _update_source_status("mqttPublish", running=False, lastError=f"connect_rc={rc}")

    def _on_message(client, userdata, message):
        if any(message.topic.startswith(p) for p in _INTERNAL_TOPIC_PREFIXES):
            return
        now_ts = time.time()
        key = message.topic
        if now_ts - mqtt_monitor._last_publish_ts.get(key, 0) < _PUBLISH_DEDUP_SECONDS:
            return
        mqtt_monitor._last_publish_ts[key] = now_ts
        event = MQTTEvent(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
            event_type="Publish",
            client_id="(broker-observed)",
            details=f"Published to {message.topic} ({len(message.payload)} B, QoS {message.qos})",
            status="info",
            protocol_level="MQTT v3.1.1",
            clean_session=True,
            keep_alive=0,
            username="(broker-observed)",
            ip_address="",
            port=0,
            topic=message.topic,
            qos=message.qos,
        )
        mqtt_monitor.events.append(event)
        try:
            from services import monitor_service

            try:
                msg_retained = bool(getattr(message, "retain", False))
            except (AttributeError, TypeError):
                msg_retained = False
            monitor_service.record_user_publish(
                message.topic,
                message.payload,
                retained=msg_retained,
                qos=message.qos,
                source="broker-observed",
            )
        except Exception as exc:
            print(f"Monitor mirror for observed publish failed: {exc}")
        _update_source_status(
            "mqttPublish",
            lastEventAt=datetime.now(tz=timezone.utc).isoformat(),
        )

    client = paho_mqtt.Client(
        client_id="bunkerm-publish-monitor",
        protocol=paho_mqtt.MQTTv311,
    )
    client.username_pw_set(username, password)
    client.on_connect = _on_connect
    client.on_message = _on_message

    while True:
        try:
            client.connect(broker_host, broker_port, keepalive=60)
            client.loop_forever()
        except Exception as exc:
            _update_source_status("mqttPublish", running=False, lastError=str(exc))
            print(f"Monitor de publishes MQTT error: {exc}. Reconectando en 10 s…")
            time.sleep(10)
