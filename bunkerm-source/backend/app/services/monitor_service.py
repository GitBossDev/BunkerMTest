"""
Lógica de negocio del monitor MQTT: clases de estado, motor de alertas y
función de conexión al broker.
Extraído de monitor/main.py para separarlo de la capa HTTP.
"""
from __future__ import annotations

import json
import logging
import os
import re
import socket
import threading
import time
import uuid as _uuid
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from paho.mqtt import client as mqtt_client

# Importamos desde la ubicación original — no movemos ni copiamos el archivo
from monitor.data_storage import HistoricalDataStorage, PERIODS

from core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tópicos $SYS que el monitor procesa
# ---------------------------------------------------------------------------

MONITORED_TOPICS: Dict[str, str] = {
    "$SYS/broker/messages/sent":               "messages_sent",
    "$SYS/broker/messages/received":           "messages_received_total",
    "$SYS/broker/subscriptions/count":         "subscriptions",
    "$SYS/broker/retained messages/count":     "retained_messages",
    "$SYS/broker/messages/inflight":           "messages_inflight",
    "$SYS/broker/store/messages/count":        "messages_stored",
    "$SYS/broker/store/messages/bytes":        "messages_store_bytes",
    "$SYS/broker/clients/connected":           "connected_clients",
    "$SYS/broker/clients/total":               "clients_total",
    "$SYS/broker/clients/maximum":             "clients_maximum",
    "$SYS/broker/clients/disconnected":        "clients_disconnected",
    "$SYS/broker/clients/expired":             "clients_expired",
    "$SYS/broker/load/messages/received/1min": "load_msg_rx_1min",
    "$SYS/broker/load/messages/sent/1min":     "load_msg_tx_1min",
    "$SYS/broker/load/bytes/received/1min":    "load_bytes_rx_1min",
    "$SYS/broker/load/bytes/sent/1min":        "load_bytes_tx_1min",
    "$SYS/broker/load/bytes/received/15min":   "bytes_received_15min",
    "$SYS/broker/load/bytes/sent/15min":       "bytes_sent_15min",
    "$SYS/broker/load/connections/1min":       "load_connections_1min",
    "$SYS/broker/version":                     "broker_version",
    "$SYS/broker/uptime":                      "broker_uptime",
    "$SYS/broker/heap/current":                "heap_current",
    "$SYS/broker/heap/maximum":                "heap_maximum",
}

_FLOAT_TOPICS = {
    "$SYS/broker/load/messages/received/1min",
    "$SYS/broker/load/messages/sent/1min",
    "$SYS/broker/load/bytes/received/1min",
    "$SYS/broker/load/bytes/sent/1min",
    "$SYS/broker/load/bytes/received/15min",
    "$SYS/broker/load/bytes/sent/15min",
    "$SYS/broker/load/connections/1min",
}
_STRING_TOPICS = {
    "$SYS/broker/version",
    "$SYS/broker/uptime",
}

# ---------------------------------------------------------------------------
# Configuración de alertas (JSON persistido en disco, cached 30 s)
# ---------------------------------------------------------------------------

_ALERT_CONFIG_PATH = os.getenv("ALERT_CONFIG_PATH", "/nextjs/data/alert_config.json")
_alert_config_cache: dict = {}
_alert_config_ts: float = 0.0


def _default_alert_config() -> dict:
    return {
        "broker_down_grace_polls":  int(os.getenv("ALERT_BROKER_DOWN_GRACE_POLLS", "5")),
        "client_capacity_pct":      float(os.getenv("ALERT_CLIENT_CAPACITY_PCT", "80")),
        "reconnect_loop_count":     int(os.getenv("ALERT_RECONNECT_LOOP_COUNT", "5")),
        "reconnect_loop_window_s":  int(os.getenv("ALERT_RECONNECT_LOOP_WINDOW_S", "60")),
        "auth_fail_count":          int(os.getenv("ALERT_AUTH_FAIL_COUNT", "5")),
        "auth_fail_window_s":       int(os.getenv("ALERT_AUTH_FAIL_WINDOW_S", "60")),
        "cooldown_minutes":         int(os.getenv("ALERT_COOLDOWN_MINUTES", "15")),
    }


def read_alert_config() -> dict:
    """Lee la configuración de alertas del JSON, con caché de 30 s."""
    global _alert_config_cache, _alert_config_ts
    now = time.time()
    if _alert_config_cache and now - _alert_config_ts < 30.0:
        return _alert_config_cache
    try:
        with open(_ALERT_CONFIG_PATH) as fh:
            data = json.load(fh)
        cfg = {**_default_alert_config(), **data}
    except (FileNotFoundError, json.JSONDecodeError):
        cfg = _default_alert_config()
    _alert_config_cache = cfg
    _alert_config_ts = now
    return cfg


def save_alert_config(cfg: dict) -> None:
    """Persiste la configuración de alertas e invalida la caché."""
    global _alert_config_cache, _alert_config_ts
    os.makedirs(os.path.dirname(_ALERT_CONFIG_PATH), exist_ok=True)
    with open(_ALERT_CONFIG_PATH, "w") as fh:
        json.dump(cfg, fh, indent=2)
    _alert_config_cache = cfg
    _alert_config_ts = time.time()


_max_connections_cache: dict = {"value": 0, "ts": 0.0}


def read_max_connections() -> int:
    """Lee max_connections del mosquitto.conf (caché 30 s)."""
    now = time.time()
    if _max_connections_cache["value"] and now - _max_connections_cache["ts"] < 30.0:
        return _max_connections_cache["value"]
    limit = 0
    try:
        with open(settings.mosquitto_conf_path) as fh:
            for line in fh:
                line = line.strip()
                if line.startswith("max_connections "):
                    val = int(line.split()[1])
                    if val > 0 and (limit == 0 or val < limit):
                        limit = val
    except Exception:
        pass
    if limit <= 0:
        limit = int(os.getenv("ALERT_CLIENT_MAX_DEFAULT", "10000"))
    _max_connections_cache["value"] = limit
    _max_connections_cache["ts"] = now
    return limit


# ---------------------------------------------------------------------------
# Motor de alertas
# ---------------------------------------------------------------------------

class AlertEngine:
    """Evalúa métricas del broker y emite alertas en memoria."""

    TYPE_BROKER_DOWN     = "broker_down"
    TYPE_CLIENT_CAPACITY = "client_capacity"
    TYPE_RECONNECT_LOOP  = "reconnect_loop"
    TYPE_AUTH_FAILURE    = "auth_failure"
    TYPE_DEVICE_SILENT   = "device_silent"

    _SEVERITY = {
        TYPE_BROKER_DOWN:     "critical",
        TYPE_CLIENT_CAPACITY: "high",
        TYPE_RECONNECT_LOOP:  "high",
        TYPE_AUTH_FAILURE:    "high",
        TYPE_DEVICE_SILENT:   "high",
    }
    _TITLES = {
        TYPE_BROKER_DOWN:     "Broker Unreachable",
        TYPE_CLIENT_CAPACITY: "Client Capacity Warning",
        TYPE_RECONNECT_LOOP:  "Client Reconnect Loop",
        TYPE_AUTH_FAILURE:    "Authentication Failures",
        TYPE_DEVICE_SILENT:   "Device Silent",
    }
    _IMPACT = {
        TYPE_BROKER_DOWN:     "New MQTT connections are rejected. All clients lose connectivity.",
        TYPE_CLIENT_CAPACITY: "Approaching the configured connection limit. New clients may be refused.",
        TYPE_RECONNECT_LOOP:  "Excessive reconnects consume broker resources and may indicate a client bug.",
        TYPE_AUTH_FAILURE:    "Repeated authentication failures may indicate a brute-force attempt.",
        TYPE_DEVICE_SILENT:   "A monitored topic has not published within the expected interval. The device may be offline, stuck, or losing connectivity.",
    }

    def __init__(self):
        self._lock = threading.Lock()
        self._active: Dict[str, dict] = {}
        self._broker_down_polls: int = 0
        self._reconnect_events: Dict[str, deque] = {}
        self._auth_fail_events: deque = deque()
        self._cooldown_until: Dict[str, float] = {}
        self._alert_history: deque = deque(maxlen=200)
        self._watchlist_cache: List[dict] = []
        self._watchlist_ts: float = 0.0
        self._watchlist_patterns: List[tuple] = []

    def get_alerts(self) -> List[dict]:
        with self._lock:
            return list(self._active.values())

    def get_history(self) -> List[dict]:
        with self._lock:
            return list(self._alert_history)

    def acknowledge(self, alert_id: str) -> bool:
        cooldown_secs = read_alert_config()["cooldown_minutes"] * 60
        with self._lock:
            for key, alert in list(self._active.items()):
                if alert["id"] == alert_id:
                    self._alert_history.append({
                        **alert,
                        "status": "acknowledged",
                        "resolved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    })
                    del self._active[key]
                    self._cooldown_until[key] = time.time() + cooldown_secs
                    return True
        return False

    def evaluate(self, stats: dict, topics: Optional[List[dict]] = None):
        """Evalúa condiciones de alerta con el snapshot de stats más reciente."""
        cfg         = read_alert_config()
        grace_polls = cfg["broker_down_grace_polls"]
        cap_pct     = cfg["client_capacity_pct"]
        max_clients = float(read_max_connections())
        watchlist   = self._load_watchlist() if topics is not None else []

        with self._lock:
            connected_flag = stats.get("mqtt_connected", False)
            if not connected_flag:
                self._broker_down_polls += 1
                if self._broker_down_polls >= grace_polls:
                    self._raise(
                        self.TYPE_BROKER_DOWN,
                        f"Broker has not responded for {self._broker_down_polls} consecutive polls "
                        f"(threshold: {grace_polls}).",
                    )
            else:
                self._broker_down_polls = 0
                self._clear(self.TYPE_BROKER_DOWN)

            connected = stats.get("total_connected_clients", 0)
            if max_clients > 0 and (connected / max_clients * 100) >= cap_pct:
                self._raise(
                    self.TYPE_CLIENT_CAPACITY,
                    f"{connected} clients connected ({connected / max_clients * 100:.1f}% of {int(max_clients)} max, "
                    f"threshold: {cap_pct:.0f}%).",
                )
            else:
                self._clear(self.TYPE_CLIENT_CAPACITY)

            if topics is not None and watchlist:
                self._check_silent_devices_locked(topics, watchlist)

    def record_connect_event(self, client_id: str):
        cfg         = read_alert_config()
        loop_count  = cfg["reconnect_loop_count"]
        window_secs = cfg["reconnect_loop_window_s"]
        now = time.time()
        with self._lock:
            if client_id not in self._reconnect_events:
                self._reconnect_events[client_id] = deque()
            q = self._reconnect_events[client_id]
            q.append(now)
            while q and now - q[0] > window_secs:
                q.popleft()
            if len(q) >= loop_count:
                self._raise(
                    self.TYPE_RECONNECT_LOOP,
                    f"Client '{client_id}' reconnected {len(q)} times in the last {window_secs}s "
                    f"(threshold: {loop_count}).",
                    alert_id_suffix=client_id[:32],
                )

    def record_auth_failure(self):
        cfg         = read_alert_config()
        fail_count  = cfg["auth_fail_count"]
        window_secs = cfg["auth_fail_window_s"]
        now = time.time()
        with self._lock:
            self._auth_fail_events.append(now)
            while self._auth_fail_events and now - self._auth_fail_events[0] > window_secs:
                self._auth_fail_events.popleft()
            if len(self._auth_fail_events) >= fail_count:
                self._raise(
                    self.TYPE_AUTH_FAILURE,
                    f"{len(self._auth_fail_events)} authentication failures in the last {window_secs}s "
                    f"(threshold: {fail_count}).",
                )

    # ── watchlist ────────────────────────────────────────────────────────────

    def _load_watchlist(self) -> List[dict]:
        path = os.getenv("ALERT_WATCHLIST_PATH", "/nextjs/data/silent_watchlist.json")
        now = time.time()
        if self._watchlist_cache is not None and now - self._watchlist_ts < 30.0:
            return self._watchlist_cache
        try:
            with open(path) as fh:
                data = json.load(fh)
            rules = data if isinstance(data, list) else []
        except (FileNotFoundError, json.JSONDecodeError):
            rules = []
        compiled = []
        for r in rules:
            pattern = r.get("pattern", "")
            max_s   = int(r.get("max_silence_secs", 0))
            label   = r.get("label", pattern)
            if pattern and max_s > 0:
                compiled.append((pattern, self._mqtt_to_regex(pattern), max_s, label))
        self._watchlist_cache = rules
        self._watchlist_patterns = compiled
        self._watchlist_ts = now
        return rules

    @staticmethod
    def _mqtt_to_regex(pattern: str) -> re.Pattern:
        escaped = re.escape(pattern)
        escaped = escaped.replace(r"\+", "[^/]+").replace(r"\#", ".+")
        return re.compile(f"^{escaped}$")

    def _check_silent_devices_locked(self, topics: List[dict], watchlist: List[dict]):
        now_dt = datetime.now(timezone.utc)
        for (pattern_str, rx, max_silence, label) in self._watchlist_patterns:
            matching = [t for t in topics if rx.match(t.get("topic", ""))]
            if not matching:
                continue
            for t in matching:
                topic  = t["topic"]
                ts_str = t.get("timestamp", "")
                suffix = f"{pattern_str}:{topic}"[:64]
                try:
                    last_dt  = datetime.fromisoformat(ts_str.rstrip("Z")).replace(tzinfo=timezone.utc)
                    age_secs = (now_dt - last_dt).total_seconds()
                except (ValueError, AttributeError):
                    continue
                if age_secs >= max_silence:
                    self._raise(
                        self.TYPE_DEVICE_SILENT,
                        f"Topic '{topic}' (rule: '{label}') silent for {int(age_secs // 60)} min "
                        f"(threshold: {max_silence // 60} min).",
                        alert_id_suffix=suffix,
                    )
                else:
                    self._clear_key(f"{self.TYPE_DEVICE_SILENT}:{suffix}")

    # ── helpers privados ─────────────────────────────────────────────────────

    def _raise(self, alert_type: str, description: str, alert_id_suffix: str = ""):
        key = f"{alert_type}:{alert_id_suffix}" if alert_id_suffix else alert_type
        if key not in self._active and self._cooldown_until.get(key, 0) > time.time():
            return
        if key not in self._active:
            entry = {
                "id": str(_uuid.uuid4()),
                "type": alert_type,
                "severity": self._SEVERITY.get(alert_type, "high"),
                "title": self._TITLES.get(alert_type, alert_type),
                "impact": self._IMPACT.get(alert_type, ""),
                "description": description,
                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "status": "active",
            }
            self._active[key] = entry
            self._alert_history.append({**entry})
        else:
            self._active[key]["description"] = description

    def _clear(self, alert_type: str):
        entry = self._active.pop(alert_type, None)
        if entry is not None:
            self._alert_history.append({
                **entry,
                "status": "cleared",
                "resolved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            })

    def _clear_key(self, key: str):
        entry = self._active.pop(key, None)
        if entry is not None:
            self._alert_history.append({
                **entry,
                "status": "cleared",
                "resolved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            })


# ---------------------------------------------------------------------------
# Contador de mensajes de usuario (ventana deslizante 7 días)
# ---------------------------------------------------------------------------

_MSG_COUNTS_PATH = os.getenv("MESSAGE_COUNTS_PATH", "/nextjs/data/message_counts.json")


class MessageCounter:
    def __init__(self):
        self.file_path = _MSG_COUNTS_PATH
        self.daily_counts = self._load_counts()

    def _load_counts(self) -> Dict[str, int]:
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path) as fh:
                    data = json.load(fh)
                    return {item["timestamp"].split()[0]: item["message_counter"]
                            for item in data}
            except Exception:
                pass
        return {}

    def _save_counts(self):
        data = [
            {"timestamp": f"{date} 00:00", "message_counter": count}
            for date, count in self.daily_counts.items()
        ]
        try:
            with open(self.file_path, "w") as fh:
                json.dump(data, fh, indent=2)
        except Exception as exc:
            logger.error("Error guardando message_counts: %s", exc)

    def increment_count(self):
        today = datetime.now().date().isoformat()
        self.daily_counts[today] = self.daily_counts.get(today, 0) + 1
        cutoff = (datetime.now() - timedelta(days=7)).date().isoformat()
        self.daily_counts = {d: c for d, c in self.daily_counts.items() if d >= cutoff}
        self._save_counts()

    def get_total_count(self) -> int:
        return sum(self.daily_counts.values())


# ---------------------------------------------------------------------------
# Almacén de tópicos (último valor visto de cada tópico no-$SYS)
# ---------------------------------------------------------------------------

class TopicStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._topics: Dict[str, dict] = {}

    def update(self, topic: str, payload: bytes, retained: bool = False, qos: int = 0):
        with self._lock:
            value = payload.decode("utf-8", errors="replace") if payload else ""
            prev = self._topics.get(topic, {})
            self._topics[topic] = {
                "topic": topic,
                "value": value,
                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "count": prev.get("count", 0) + 1,
                "retained": retained,
                "qos": qos,
            }

    def get_all(self) -> list:
        with self._lock:
            return sorted(self._topics.values(), key=lambda x: x["topic"])


# ---------------------------------------------------------------------------
# Gestor de nonces (anti-replay en el endpoint /stats)
# ---------------------------------------------------------------------------

class NonceManager:
    def __init__(self):
        self._used: set = set()
        t = threading.Thread(target=self._cleanup, daemon=True)
        t.start()

    def validate(self, nonce: str, timestamp: float) -> bool:
        if nonce in self._used:
            return False
        if time.time() - timestamp > 300:
            return False
        self._used.add(nonce)
        return True

    def _cleanup(self):
        while True:
            now = time.time()
            # Eliminamos nonces cuyo timestamp embedded supera los 300 s
            # El nonce puede ser cualquier cadena, así que simplemente
            # vaciamos el set periódicamente (tolerable para ventana de 5 min)
            self._used.clear()
            time.sleep(300)


# ---------------------------------------------------------------------------
# Estadísticas MQTT (estado central del monitor)
# ---------------------------------------------------------------------------

_HIST_DATA_PATH = os.getenv("HISTORICAL_DATA_PATH", "/nextjs/data/historical_data.json")


class MQTTStats:
    def __init__(self):
        self._lock = threading.Lock()
        # Valores directos de $SYS
        self.messages_sent = 0
        self.subscriptions = 0
        self.retained_messages = 0
        self.connected_clients = 0
        self.bytes_received_15min = 0.0
        self.bytes_sent_15min = 0.0
        self.clients_total = 0
        self.clients_maximum = 0
        self.clients_disconnected = 0
        self.clients_expired = 0
        self.messages_received_total = 0
        self.messages_inflight = 0
        self.messages_stored = 0
        self.messages_store_bytes = 0
        self.load_msg_rx_1min = 0.0
        self.load_msg_tx_1min = 0.0
        self.load_bytes_rx_1min = 0.0
        self.load_bytes_tx_1min = 0.0
        self.load_connections_1min = 0.0
        self.broker_version = ""
        self.broker_uptime = ""
        self.heap_current = 0
        self.heap_maximum = 0
        self.latency_ms: float = -1.0
        self.last_broker_sample_at = ""
        self._ping_sent_at: float = 0.0
        self._is_connected: bool = False
        self.message_counter = MessageCounter()
        self.data_storage = HistoricalDataStorage(filename=_HIST_DATA_PATH)
        self.last_storage_update = self._load_last_tick_time()
        self.messages_history: deque = deque(maxlen=15)
        self.published_history: deque = deque(maxlen=15)
        self.last_messages_sent = 0
        self.last_update = datetime.now()
        for _ in range(15):
            self.messages_history.append(0)
            self.published_history.append(0)

    def _load_last_tick_time(self) -> datetime:
        try:
            data = self.data_storage.load_data()
            ticks = data.get("bytes_ticks") or data.get("msg_ticks") or []
            if ticks:
                last_ts = ticks[-1].get("ts", "")
                parsed  = datetime.fromisoformat(last_ts.rstrip("Z"))
                age     = (datetime.now() - parsed).total_seconds()
                if 0 < age < 3600:
                    return parsed
        except Exception:
            pass
        return datetime.now()

    def format_number(self, number: int) -> str:
        if number >= 1_000_000:
            return f"{number / 1_000_000:.1f}M"
        if number >= 1_000:
            return f"{number / 1_000:.1f}K"
        return str(number)

    def increment_user_messages(self):
        with self._lock:
            self.message_counter.increment_count()

    def update_storage(self):
        """Escribe un tick de datos históricos cada 3 minutos."""
        now = datetime.now()
        if (now - self.last_storage_update).total_seconds() >= 180:
            self.last_storage_update = now
            try:
                self.data_storage.add_hourly_data(
                    float(self.bytes_received_15min),
                    float(self.bytes_sent_15min),
                )
                self.data_storage.add_tick(
                    bytes_received=float(self.bytes_received_15min),
                    bytes_sent=float(self.bytes_sent_15min),
                    msg_received=int(self.messages_received_total),
                    msg_sent=int(self.messages_sent),
                )
            except Exception as exc:
                logger.error("Error actualizando storage: %s", exc)

    def update_message_rates(self):
        now = datetime.now()
        if (now - self.last_update).total_seconds() >= 60:
            with self._lock:
                published_rate = max(0, self.messages_sent - self.last_messages_sent)
                self.published_history.append(published_rate)
                self.last_messages_sent = self.messages_sent
                self.last_update = now

    def _get_client_counters_locked(self) -> Dict[str, int]:
        """Normaliza contadores de clientes para que el dashboard sea coherente."""
        connected = max(0, self.connected_clients - 1)
        total = max(0, self.clients_total - 1)
        maximum = max(0, self.clients_maximum - 1)

        if total < connected:
            total = connected

        # `$SYS/broker/clients/disconnected` puede desbordarse bajo carga o tras
        # tormentas de reconexión. Derivarlo desde total-connected mantiene la UI
        # consistente con el resto de contadores del broker.
        disconnected = max(0, total - connected)
        expired = max(0, self.clients_expired)

        return {
            "connected": connected,
            "total": total,
            "maximum": maximum,
            "disconnected": disconnected,
            "expired": expired,
        }

    def get_client_counters(self) -> Dict[str, int]:
        with self._lock:
            return self._get_client_counters_locked()

    def get_stats(self) -> Dict[str, Any]:
        self.update_message_rates()
        self.update_storage()
        with self._lock:
            client_counts = self._get_client_counters_locked()
            actual_subscriptions = max(0, self.subscriptions - 2)
            total_messages = self.message_counter.get_total_count()
            hourly_data    = self.data_storage.get_hourly_data()
            daily_messages = self.data_storage.get_daily_messages()
            stats = {
                "total_connected_clients": client_counts["connected"],
                "total_messages_received": self.format_number(total_messages),
                "total_subscriptions": actual_subscriptions,
                "retained_messages": self.retained_messages,
                "messages_history": list(self.messages_history),
                "published_history": list(self.published_history),
                "bytes_stats": hourly_data,
                "daily_message_stats": daily_messages,
                "clients_total": client_counts["total"],
                "clients_maximum": client_counts["maximum"],
                "clients_disconnected": client_counts["disconnected"],
                "clients_expired": client_counts["expired"],
                "broker_version": self.broker_version,
                "broker_uptime": self.broker_uptime,
                "messages_received_raw": self.messages_received_total,
                "messages_sent_raw": self.messages_sent,
                "load_msg_rx_1min": round(self.load_msg_rx_1min, 2),
                "load_msg_tx_1min": round(self.load_msg_tx_1min, 2),
                "load_bytes_rx_1min": round(self.load_bytes_rx_1min, 2),
                "load_bytes_tx_1min": round(self.load_bytes_tx_1min, 2),
                "load_connections_1min": round(self.load_connections_1min, 2),
                "messages_inflight": self.messages_inflight,
                "messages_stored": self.messages_stored,
                "messages_store_bytes": self.messages_store_bytes,
                "latency_ms": self.latency_ms,
                "mqtt_connected": self._is_connected,
                "client_max_connections": read_max_connections(),
                "last_broker_sample_at": self.last_broker_sample_at,
            }
        try:
            alert_engine.evaluate(stats, topic_store.get_all())
        except Exception as exc:
            logger.warning("AlertEngine.evaluate error: %s", exc)
        return stats


# ---------------------------------------------------------------------------
# Singletons globales accesibles desde los routers
# ---------------------------------------------------------------------------

alert_engine  = AlertEngine()
mqtt_stats    = MQTTStats()
topic_store   = TopicStore()
nonce_manager = NonceManager()

# Referencia al cliente MQTT activo (inicializada en el lifespan de main.py)
mqtt_client_instance: Any = None


# ---------------------------------------------------------------------------
# Callbacks MQTT
# ---------------------------------------------------------------------------

def on_message(client, userdata, msg):
    if msg.topic in MONITORED_TOPICS:
        try:
            attr_name = MONITORED_TOPICS[msg.topic]
            raw = msg.payload.decode()
            sample_ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            with mqtt_stats._lock:
                if msg.topic in _STRING_TOPICS:
                    setattr(mqtt_stats, attr_name, raw)
                elif msg.topic in _FLOAT_TOPICS:
                    setattr(mqtt_stats, attr_name, float(raw))
                else:
                    setattr(mqtt_stats, attr_name, int(raw))
                mqtt_stats.last_broker_sample_at = sample_ts
        except ValueError as exc:
            logger.error("Error procesando %s: %s", msg.topic, exc)
    elif msg.topic == "bunkerm/monitor/ping":
        try:
            sent_at = float(msg.payload.decode())
            with mqtt_stats._lock:
                mqtt_stats.latency_ms = round((time.time() - sent_at) * 1000, 2)
                mqtt_stats.last_broker_sample_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        except (ValueError, AttributeError):
            pass
    elif not msg.topic.startswith("$SYS/"):
        mqtt_stats.increment_user_messages()
        topic_store.update(msg.topic, msg.payload, getattr(msg, "retain", False), msg.qos)


def connect_mqtt():
    """Conecta al broker MQTT y devuelve el cliente paho configurado."""
    broker_host = os.getenv("MOSQUITTO_IP", settings.mqtt_broker)
    broker_port = int(os.getenv("MOSQUITTO_PORT", str(settings.mqtt_port)))
    username    = os.getenv("MOSQUITTO_ADMIN_USERNAME", settings.mqtt_username)
    password    = os.getenv("MOSQUITTO_ADMIN_PASSWORD", settings.mqtt_password)

    def on_connect(client, userdata, flags, rc, properties=None):
        if rc == 0:
            logger.info("Conectado al broker MQTT %s:%s", broker_host, broker_port)
            mqtt_stats._is_connected = True
            client.subscribe([("$SYS/broker/#", 0), ("#", 2)])
        else:
            mqtt_stats._is_connected = False
            logger.error("Fallo de conexión al broker MQTT, código %s", rc)

    def on_disconnect(client, userdata, disconnect_flags, reason_code=None, properties=None):
        mqtt_stats._is_connected = False
        rc = reason_code if reason_code is not None else disconnect_flags
        if rc != 0:
            logger.warning("Desconexión inesperada del broker MQTT (rc=%s), reconectando…", rc)

    try:
        try:
            client = mqtt_client.Client(mqtt_client.CallbackAPIVersion.VERSION2)
        except AttributeError:
            client = mqtt_client.Client(client_id="mqtt-monitor", protocol=mqtt_client.MQTTv5)

        client.username_pw_set(username, password)
        client.on_connect    = on_connect
        client.on_disconnect = on_disconnect
        client.on_message    = on_message

        if not broker_host:
            raise ValueError("MOSQUITTO_IP no está configurado")

        client.connect(broker_host, broker_port, 60)
        return client

    except (ConnectionRefusedError, socket.error) as exc:
        logger.error("Fallo de conexión al broker: %s", exc)
    except Exception as exc:
        logger.error("Error inesperado al conectar al broker: %s", exc)

    # Devolvemos un cliente dummy que no produce excepciones al llamar loop_start/stop
    try:
        dummy = mqtt_client.Client(mqtt_client.CallbackAPIVersion.VERSION2)
    except AttributeError:
        dummy = mqtt_client.Client(client_id="dummy-client", protocol=mqtt_client.MQTTv5)
    dummy.loop_start = lambda: None
    dummy.loop_stop  = lambda: None
    return dummy
