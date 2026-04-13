"""
Servicio de monitoreo de logs de clientes MQTT.
Extrae la clase MQTTMonitor y las funciones de fondo de clientlogs/main.py.
Estas funciones se ejecutan como hilos daemon, iniciados desde el lifespan del app principal.
"""
from __future__ import annotations

import os
import re
import subprocess
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel

from clientlogs.sqlite_activity_storage import client_activity_storage
from core.config import settings
from monitor.topic_sqlite_storage import topic_history_storage

# ---------------------------------------------------------------------------
# Constantes y patrones regex
# ---------------------------------------------------------------------------

# Regex para IDs de cliente generados automáticamente por mosquitto_ctrl
_AUTO_CLIENT_RE = re.compile(
    r"^auto-[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$"
)

_MOSQUITTO_LOG_KEYWORDS = frozenset([
    "New", "Sending", "Received", "Client", "Warning", "Config",
    "Loading", "Opening", "No", "mosquitto", "Error", "Notice",
    "Socket", "Timeout", "Plugin", "Saving", "Using", "Log",
    "Restored", "Bridge", "Persistence", "TLS", "Websockets", "Info:",
])

# Captura timestamps Unix (dígitos) e ISO 8601 (Mosquitto 2.1.2)
_TS_CAPTURE = r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}|\d+)"
_TS_RE      = re.compile(r"^(?:\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}|\d+)$")

# Ventana de deduplicación temporal de eventos Publish (en segundos)
_PUBLISH_DEDUP_SECONDS = 60

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
    reason_code: Optional[str] = None


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

    # ── helpers ──────────────────────────────────────────────────────────────

    def _get_client_info(self, client_id: str) -> Tuple[str, str, str, int, bool, int]:
        """Devuelve (username, protocol, ip, port, clean_session, keep_alive)."""
        if client_id in self.connected_clients:
            ev = self.connected_clients[client_id]
            return ev.username, ev.protocol_level, ev.ip_address, ev.port, ev.clean_session, ev.keep_alive
        if client_id in self._client_usernames:
            return self._client_usernames[client_id], "MQTT vunknown", "unknown", 0, False, 0
        return "unknown", "MQTT vunknown", "unknown", 0, False, 0

    def _is_admin(self, username: str) -> bool:
        return username == os.getenv("MOSQUITTO_ADMIN_USERNAME", settings.mqtt_username)

    def _is_internal_auto_client(self, client_id: str) -> bool:
        return bool(_AUTO_CLIENT_RE.match(client_id))

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
            reason_code="not_authorised",
        )

    def parse_subscription_log(self, log_line: str) -> Optional[MQTTEvent]:
        if ": " not in log_line:
            return None
        ts_str, content = log_line.split(": ", 1)
        if not _TS_RE.match(ts_str):
            return None
        parts = content.split()
        if len(parts) != 3:
            return None
        client_id, qos_str, topic = parts
        if qos_str not in ("0", "1", "2"):
            return None
        if client_id in _MOSQUITTO_LOG_KEYWORDS:
            return None
        username, protocol_level, ip, port, clean, keep_alive = self._get_client_info(client_id)
        if self._is_admin(username):
            return None
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
        return event

    def parse_publish_log(self, log_line: str) -> Optional[MQTTEvent]:
        pattern = (
            _TS_CAPTURE
            + r": Received PUBLISH from (\S+)"
            r" \(d\d, q(\d), r\d, m\d+, '([^']+)', \.\.\. \((\d+) bytes\)\)"
        )
        m = re.match(pattern, log_line)
        if not m:
            return None
        ts, client_id, qos_str, topic, size_str = m.groups()
        if any(topic.startswith(p) for p in _INTERNAL_TOPIC_PREFIXES):
            return None
        username, protocol_level, ip, port, clean, keep_alive = self._get_client_info(client_id)
        if self._is_admin(username):
            return None
        event_ts = _ts_to_epoch(ts)
        self._publisher_clients_seen[self._activity_client_key(client_id, username)] = event_ts
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
        )

    # ── pipeline de procesamiento ─────────────────────────────────────────────

    def process_line(self, line: str, replay: bool = False) -> None:
        """Procesa una línea del log por todos los parsers en orden de prioridad."""
        if (
            ": Sending PUBLISH to " in line
            or ": Denied PUBLISH from " in line
            or ": Sending SUBACK to "  in line
            or ": Sending PUBACK to "  in line
            or ": Received SUBSCRIBE from " in line
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
                    topic_history_storage.record_subscribe(event.topic, event_ts=datetime.fromisoformat(event.timestamp))
                if not replay:
                    client_activity_storage.record_event(event)
                if not replay:
                    self.events.append(event)
                return

        event = self.parse_publish_log(line)
        if event is not None:
            if not replay:
                client_activity_storage.record_event(event)
            if not replay:
                self.events.append(event)
            return


# ---------------------------------------------------------------------------
# Singleton global accesible desde el router
# ---------------------------------------------------------------------------

mqtt_monitor = MQTTMonitor()


# ---------------------------------------------------------------------------
# Funciones de fondo (se ejecutan como hilos daemon en el lifespan)
# ---------------------------------------------------------------------------

def monitor_mosquitto_logs() -> None:
    """Lee el log de Mosquitto en tiempo real y alimenta el MQTTMonitor."""
    log_file = os.getenv("BROKER_LOG_PATH", settings.broker_log_path)
    print("Iniciando monitoreo de logs de Mosquitto...")

    # Replay de arranque: reconstruye el estado de conexiones y suscripciones
    try:
        result = subprocess.run(
            [
                "grep", "-E",
                "New client connected from|Client .+ disconnected|Client .+ closed its connection",
                log_file,
            ],
            capture_output=True,
            text=True,
        )
        for replay_line in result.stdout.splitlines():
            line = replay_line.strip()
            if line:
                mqtt_monitor.process_line(line, replay=True)
        print(
            f"Replay de arranque: {len(mqtt_monitor.connected_clients)} conectados, "
            f"{len(mqtt_monitor._client_usernames)} usernames conocidos."
        )
    except Exception as exc:
        print(f"Replay de arranque falló: {exc}")

    try:
        result_sub = subprocess.run(
            ["grep", "-E", r": [^ ]+ [012] [^ ]+$", log_file],
            capture_output=True,
            text=True,
        )
        for replay_line in result_sub.stdout.splitlines():
            line = replay_line.strip()
            if line:
                mqtt_monitor.process_line(line, replay=True)
        print(f"Replay de suscripciones: {len(mqtt_monitor._subscription_counts)} tópicos distintos.")
    except Exception as exc:
        print(f"Replay de suscripciones falló: {exc}")

    # Detección de reinicio de Mosquitto: si el broker terminó después de la última conexión,
    # los clientes "conectados" son fantasmas — los limpiamos
    try:
        term_grep = subprocess.run(
            ["grep", "mosquitto version .* terminating", log_file],
            capture_output=True,
            text=True,
        )
        if term_grep.returncode == 0:
            term_lines = [l.strip() for l in term_grep.stdout.splitlines() if l.strip()]
            if term_lines and mqtt_monitor.connected_clients:
                last_term_raw = term_lines[-1].split(": ")[0]
                if last_term_raw.isdigit():
                    last_term_dt = datetime.fromtimestamp(int(last_term_raw), tz=timezone.utc)
                else:
                    last_term_dt = datetime.fromisoformat(last_term_raw).replace(tzinfo=timezone.utc)
                last_conn_dt = max(
                    (datetime.fromisoformat(ev.timestamp) for ev in mqtt_monitor.connected_clients.values()),
                    default=datetime.min.replace(tzinfo=timezone.utc),
                )
                if last_term_dt > last_conn_dt:
                    stale = len(mqtt_monitor.connected_clients)
                    mqtt_monitor.connected_clients.clear()
                    mqtt_monitor._last_seen.clear()
                    print(f"Arranque: reinicio detectado — eliminados {stale} clientes obsoletos.")
    except Exception as exc:
        print(f"Arranque: detección de reinicio falló: {exc}")

    # Lectura continua con tail -f
    process = subprocess.Popen(
        ["tail", "-f", log_file],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )
    print("Monitoreo continuo de logs iniciado.")
    while True:
        line = process.stdout.readline()
        if line:
            mqtt_monitor.process_line(line.strip())


def monitor_mqtt_publishes() -> None:
    """
    Se suscribe a '#' como administrador para capturar eventos Publish adicionales
    vía MQTT (complementa el parser de logs).
    """
    try:
        import paho.mqtt.client as paho_mqtt
    except ImportError:
        print("paho-mqtt no disponible; monitoreo de publishes deshabilitado.")
        return

    broker_host = os.getenv("MOSQUITTO_IP", settings.mqtt_broker)
    broker_port = int(os.getenv("MOSQUITTO_PORT", str(settings.mqtt_port)))
    username    = os.getenv("MOSQUITTO_ADMIN_USERNAME", settings.mqtt_username)
    password    = os.getenv("MOSQUITTO_ADMIN_PASSWORD", settings.mqtt_password)

    def _on_connect(client, userdata, flags, rc, properties=None):
        if rc == 0:
            client.subscribe("#", 0)
            print("Monitor de publishes MQTT: suscrito a #")
        else:
            print(f"Monitor de publishes MQTT: error de conexión rc={rc}")

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
            print(f"Monitor de publishes MQTT error: {exc}. Reconectando en 10 s…")
            time.sleep(10)
