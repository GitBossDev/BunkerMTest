# Copyright (c) 2025 BunkerM
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
# http://www.apache.org/licenses/LICENSE-2.0
# Distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.
#
# app/monitor/main.py
from fastapi import FastAPI, Depends, HTTPException, Request, Body
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from paho.mqtt import client as mqtt_client
import threading
import re
from typing import Dict, List, Optional
from collections import deque
import time
from datetime import datetime, timedelta, timezone
import json
import os
import jwt
import secrets
import logging
from logging.handlers import RotatingFileHandler
import ssl
from data_storage import HistoricalDataStorage, PERIODS as _STORAGE_PERIODS
import socket
import uuid as _uuid
import uvicorn
from contextlib import asynccontextmanager

# Add this for environment variable loading
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # If python-dotenv is not installed, just print a warning
    print("Warning: python-dotenv not installed. Using environment variables directly.")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
handler = RotatingFileHandler(
    'api_activity.log',
    maxBytes=10000000,  # 10MB
    backupCount=5
)
logger.addHandler(handler)

# MQTT Settings - Convert port to integer
MOSQUITTO_ADMIN_USERNAME = os.getenv("MOSQUITTO_ADMIN_USERNAME") or os.getenv("MQTT_USERNAME", "bunker")
MOSQUITTO_ADMIN_PASSWORD = os.getenv("MOSQUITTO_ADMIN_PASSWORD") or os.getenv("MQTT_PASSWORD", "bunker")
MOSQUITTO_IP = os.getenv("MOSQUITTO_IP", "127.0.0.1")
# Convert to int with a default value
MOSQUITTO_PORT = int(os.getenv("MOSQUITTO_PORT", "1900"))

# Security settings
JWT_SECRET = os.getenv("JWT_SECRET", secrets.token_urlsafe(32))
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION = 30  # minutes

# API Key settings
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)
API_KEY = os.getenv("API_KEY", "default_api_key_replace_in_production")
API_KEYS = {API_KEY}

_api_key_cache: dict = {"key": "", "ts": 0.0}

def _get_current_api_key() -> str:
    """Return the active API key, refreshing from file every 5 s."""
    import time as _t
    now = _t.time()
    if _api_key_cache["key"] and now - _api_key_cache["ts"] < 5.0:
        return _api_key_cache["key"]
    key = os.getenv("API_KEY", "")
    if not key or key == "default_api_key_replace_in_production":
        try:
            with open("/nextjs/data/.api_key") as _fh:
                file_key = _fh.read().strip()
                if file_key:
                    key = file_key
        except Exception:
            pass
    if not key:
        key = "default_api_key_replace_in_production"
    _api_key_cache["key"] = key
    _api_key_cache["ts"] = now
    return key

# Define the topics we're interested in
MONITORED_TOPICS = {
    # Counts
    "$SYS/broker/messages/sent":              "messages_sent",
    "$SYS/broker/messages/received":          "messages_received_total",
    "$SYS/broker/subscriptions/count":        "subscriptions",
    "$SYS/broker/retained messages/count":    "retained_messages",
    "$SYS/broker/messages/inflight":          "messages_inflight",
    "$SYS/broker/store/messages/count":       "messages_stored",
    "$SYS/broker/store/messages/bytes":       "messages_store_bytes",
    # Clients
    "$SYS/broker/clients/connected":          "connected_clients",
    "$SYS/broker/clients/total":              "clients_total",
    "$SYS/broker/clients/maximum":            "clients_maximum",
    "$SYS/broker/clients/disconnected":       "clients_disconnected",
    "$SYS/broker/clients/expired":            "clients_expired",
    # Load rates (float — msg/sec or bytes/sec)
    "$SYS/broker/load/messages/received/1min": "load_msg_rx_1min",
    "$SYS/broker/load/messages/sent/1min":     "load_msg_tx_1min",
    "$SYS/broker/load/bytes/received/1min":    "load_bytes_rx_1min",
    "$SYS/broker/load/bytes/sent/1min":        "load_bytes_tx_1min",
    "$SYS/broker/load/bytes/received/15min":   "bytes_received_15min",
    "$SYS/broker/load/bytes/sent/15min":       "bytes_sent_15min",
    "$SYS/broker/load/connections/1min":       "load_connections_1min",
    # Broker info (string)
    "$SYS/broker/version":                    "broker_version",
    "$SYS/broker/uptime":                     "broker_uptime",
    # Heap memory (bytes) — available cross-container via MQTT
    "$SYS/broker/heap/current":               "heap_current",
    "$SYS/broker/heap/maximum":               "heap_maximum",
}

# Topics whose payload is a float rate value
_FLOAT_TOPICS = {
    "$SYS/broker/load/messages/received/1min",
    "$SYS/broker/load/messages/sent/1min",
    "$SYS/broker/load/bytes/received/1min",
    "$SYS/broker/load/bytes/sent/1min",
    "$SYS/broker/load/bytes/received/15min",
    "$SYS/broker/load/bytes/sent/15min",
    "$SYS/broker/load/connections/1min",
}
# Topics whose payload is a plain string (not numeric)
_STRING_TOPICS = {
    "$SYS/broker/version",
    "$SYS/broker/uptime",
}

_max_connections_cache: dict = {"value": 0, "ts": 0.0}

def _read_max_connections() -> int:
    """Read the smallest positive max_connections from mosquitto.conf (cached 30s).
    Returns ALERT_CLIENT_MAX_DEFAULT env-var (default 10000) when no limit is configured."""
    import time as _t
    now = _t.time()
    if _max_connections_cache["value"] and now - _max_connections_cache["ts"] < 30.0:
        return _max_connections_cache["value"]
    conf_path = os.getenv("MOSQUITTO_CONF_PATH", "/etc/mosquitto/mosquitto.conf")
    limit = 0
    try:
        with open(conf_path) as _f:
            for line in _f:
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


class AlertEngine:
    """Evaluates broker metrics and emits in-memory alerts."""

    # Alert types — only broker management concerns (data interpretation is handled externally)
    TYPE_BROKER_DOWN      = "broker_down"
    TYPE_CLIENT_CAPACITY  = "client_capacity"
    TYPE_RECONNECT_LOOP   = "reconnect_loop"
    TYPE_AUTH_FAILURE     = "auth_failure"
    TYPE_DEVICE_SILENT    = "device_silent"

    # Severity for each alert type
    _SEVERITY = {
        TYPE_BROKER_DOWN:      "critical",
        TYPE_CLIENT_CAPACITY:  "high",
        TYPE_RECONNECT_LOOP:   "high",
        TYPE_AUTH_FAILURE:     "high",
        TYPE_DEVICE_SILENT:    "high",
    }

    # Human-readable titles
    _TITLES = {
        TYPE_BROKER_DOWN:      "Broker Unreachable",
        TYPE_CLIENT_CAPACITY:  "Client Capacity Warning",
        TYPE_RECONNECT_LOOP:   "Client Reconnect Loop",
        TYPE_AUTH_FAILURE:     "Authentication Failures",
        TYPE_DEVICE_SILENT:    "Device Silent",
    }

    # Human-readable impact descriptions
    _IMPACT = {
        TYPE_BROKER_DOWN:      "New MQTT connections are rejected. All clients lose connectivity.",
        TYPE_CLIENT_CAPACITY:  "Approaching the configured connection limit. New clients may be refused.",
        TYPE_RECONNECT_LOOP:   "Excessive reconnects consume broker resources and may indicate a client bug.",
        TYPE_AUTH_FAILURE:     "Repeated authentication failures may indicate a brute-force attempt.",
        TYPE_DEVICE_SILENT:    "A monitored topic has not published within the expected interval. The device may be offline, stuck, or losing connectivity.",
    }

    def __init__(self):
        self._lock = threading.Lock()
        self._active: Dict[str, dict] = {}   # keyed by alert type (one per type)
        self._broker_down_polls: int = 0
        # per-client connect timestamps (sliding window for reconnect loop detection)
        self._reconnect_events: Dict[str, deque] = {}
        # auth failure timestamps (sliding window)
        self._auth_fail_events: deque = deque()
        # cooldown: don't re-raise an alert type until this timestamp (per alert key)
        self._cooldown_until: Dict[str, float] = {}
        # persistent history of raised alerts (max 200 entries)
        self._alert_history: deque = deque(maxlen=200)
        # watchlist cache for device_silent checks
        self._watchlist_cache: List[dict] = []
        self._watchlist_ts: float = 0.0
        self._watchlist_patterns: List[tuple] = []  # (pattern_str, compiled_re, max_silence_secs, label)

    # ── public interface ──────────────────────────────────────────────────────

    def get_alerts(self) -> List[dict]:
        with self._lock:
            return list(self._active.values())

    def get_history(self) -> List[dict]:
        with self._lock:
            return list(self._alert_history)

    def acknowledge(self, alert_id: str) -> bool:
        cooldown_secs = int(os.getenv("ALERT_COOLDOWN_MINUTES", "15")) * 60
        with self._lock:
            for key, alert in list(self._active.items()):
                if alert["id"] == alert_id:
                    # Record in history as acknowledged
                    self._alert_history.append({
                        **alert,
                        "status": "acknowledged",
                        "resolved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    })
                    del self._active[key]
                    # Set cooldown so this alert type won't re-fire immediately
                    self._cooldown_until[key] = time.time() + cooldown_secs
                    return True
        return False

    def evaluate(self, stats: dict, topics: Optional[List[dict]] = None):
        """Called periodically with the latest stats snapshot."""
        grace_polls   = int(os.getenv("ALERT_BROKER_DOWN_GRACE_POLLS", "3"))
        cap_pct       = float(os.getenv("ALERT_CLIENT_CAPACITY_PCT", "80"))
        max_clients   = float(_read_max_connections())
        # Load watchlist before taking the lock (involves file I/O)
        watchlist = self._load_watchlist() if topics is not None else []

        with self._lock:
            broker_connected = stats.get("mqtt_connected", False)

            # ── Broker down ───────────────────────────────────────────────────
            if not broker_connected:
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

            # ── Client capacity ───────────────────────────────────────────────
            connected   = stats.get("total_connected_clients", 0)
            clients_max = max_clients
            if clients_max > 0 and (connected / clients_max * 100) >= cap_pct:
                self._raise(
                    self.TYPE_CLIENT_CAPACITY,
                    f"{connected} clients connected ({connected / clients_max * 100:.1f}% of {int(clients_max)} max, "
                    f"threshold: {cap_pct:.0f}%).",
                )
            else:
                self._clear(self.TYPE_CLIENT_CAPACITY)

            # ── Device silent ─────────────────────────────────────────────────
            if topics is not None and watchlist:
                self._check_silent_devices_locked(topics, watchlist)

    def record_connect_event(self, client_id: str):
        """Called whenever a client connect event is observed."""
        loop_count  = int(os.getenv("ALERT_RECONNECT_LOOP_COUNT", "5"))
        window_secs = int(os.getenv("ALERT_RECONNECT_LOOP_WINDOW_S", "60"))
        now = time.time()
        with self._lock:
            if client_id not in self._reconnect_events:
                self._reconnect_events[client_id] = deque()
            q = self._reconnect_events[client_id]
            q.append(now)
            # Trim old events outside the window
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
        """Called whenever an authentication failure is detected in Mosquitto logs."""
        fail_count  = int(os.getenv("ALERT_AUTH_FAIL_COUNT", "5"))
        window_secs = int(os.getenv("ALERT_AUTH_FAIL_WINDOW_S", "60"))
        now = time.time()
        with self._lock:
            self._auth_fail_events.append(now)
            # Trim old events
            while self._auth_fail_events and now - self._auth_fail_events[0] > window_secs:
                self._auth_fail_events.popleft()
            if len(self._auth_fail_events) >= fail_count:
                self._raise(
                    self.TYPE_AUTH_FAILURE,
                    f"{len(self._auth_fail_events)} authentication failures in the last {window_secs}s "
                    f"(threshold: {fail_count}).",
                )

    # ── watchlist helpers ─────────────────────────────────────────────────────

    def _load_watchlist(self) -> List[dict]:
        """Read silent_watchlist.json, cache result for 30 s."""
        path = os.getenv("ALERT_WATCHLIST_PATH", "/app/monitor/silent_watchlist.json")
        now = time.time()
        if self._watchlist_cache is not None and now - self._watchlist_ts < 30.0:
            return self._watchlist_cache
        try:
            with open(path) as _f:
                data = json.load(_f)
            rules = data if isinstance(data, list) else []
        except (FileNotFoundError, json.JSONDecodeError):
            rules = []
        # Compile regexes for each rule
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
        """Convert an MQTT topic pattern (using + and #) to a compiled regex.
        +  matches a single level (no slashes)
        #  matches the rest of the topic path (must appear only at the end)
        """
        # Escape all regex metacharacters, then restore + and # semantics
        escaped = re.escape(pattern)
        escaped = escaped.replace(r"\+", "[^/]+").replace(r"\#", ".+")
        return re.compile(f"^{escaped}$")

    def _check_silent_devices_locked(self, topics: List[dict], watchlist: List[dict]):
        """Raise / clear device_silent alerts. Assumes self._lock is held."""
        now_dt = datetime.now(timezone.utc)
        now_ts = time.time()
        for (pattern_str, regex, max_silence, label) in self._watchlist_patterns:
            matching = [t for t in topics if regex.match(t.get("topic", ""))]
            if not matching:
                # Pattern configured but never seen in the broker — not an alert;
                # could be a new deployment or a legitimate topic gap.
                continue
            for t in matching:
                topic     = t["topic"]
                ts_str    = t.get("timestamp", "")
                suffix    = f"{pattern_str}:{topic}"[:64]
                try:
                    last_dt = datetime.fromisoformat(ts_str.rstrip("Z")).replace(tzinfo=timezone.utc)
                    age_secs = (now_dt - last_dt).total_seconds()
                except (ValueError, AttributeError):
                    continue
                if age_secs >= max_silence:
                    mins_silent   = int(age_secs // 60)
                    mins_thresh   = max_silence // 60
                    self._raise(
                        self.TYPE_DEVICE_SILENT,
                        f"Topic '{topic}' (rule: '{label}') silent for {mins_silent} min "
                        f"(threshold: {mins_thresh} min).",
                        alert_id_suffix=suffix,
                    )
                else:
                    self._clear_key(f"{self.TYPE_DEVICE_SILENT}:{suffix}")

    # ── private helpers ───────────────────────────────────────────────────────

    def _raise(self, alert_type: str, description: str, alert_id_suffix: str = ""):
        """Upsert an alert. Respects cooldown; records new events in history."""
        key = f"{alert_type}:{alert_id_suffix}" if alert_id_suffix else alert_type
        # Respect per-key cooldown set after acknowledgement
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
            # Also add to history when first raised
            self._alert_history.append({**entry})
        else:
            # Update description in case the numbers changed, keep id & timestamp
            self._active[key]["description"] = description

    def _clear(self, alert_type: str):
        entry = self._active.pop(alert_type, None)
        if entry is not None:
            # Record as auto-resolved in history
            self._alert_history.append({
                **entry,
                "status": "cleared",
                "resolved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            })

    def _clear_key(self, key: str):
        """Clear an alert by its full key (used for suffixed alerts like device_silent)."""
        entry = self._active.pop(key, None)
        if entry is not None:
            self._alert_history.append({
                **entry,
                "status": "cleared",
                "resolved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            })


# Global alert engine instance
_alert_engine = AlertEngine()


class MQTTStats:
    def __init__(self):
        self._lock = threading.Lock()
        # Direct values from $SYS topics
        self.messages_sent = 0
        self.subscriptions = 0
        self.retained_messages = 0
        self.connected_clients = 0
        self.bytes_received_15min = 0.0
        self.bytes_sent_15min = 0.0
        # Extended $SYS fields — clients
        self.clients_total = 0
        self.clients_maximum = 0
        self.clients_disconnected = 0
        self.clients_expired = 0
        # Extended $SYS fields — messages
        self.messages_received_total = 0
        self.messages_inflight = 0
        self.messages_stored = 0
        self.messages_store_bytes = 0
        # Extended $SYS fields — load rates
        self.load_msg_rx_1min = 0.0
        self.load_msg_tx_1min = 0.0
        self.load_bytes_rx_1min = 0.0
        self.load_bytes_tx_1min = 0.0
        self.load_connections_1min = 0.0
        # Broker info
        self.broker_version = ""
        self.broker_uptime = ""
        # Heap memory from $SYS (available cross-container; replaces psutil)
        self.heap_current = 0
        self.heap_maximum = 0
        # Latency round-trip
        self.latency_ms: float = -1.0
        self._ping_sent_at: float = 0.0
        # Real MQTT connection state (set by on_connect / on_disconnect callbacks)
        self._is_connected: bool = False
        # Cache for clientlogs count (avoid HTTP call on every stats request)
        self._clientlogs_count_cache: int = 0
        self._clientlogs_count_ts: float = 0.0

        # Initialize message counter
        self.message_counter = MessageCounter()
        
        # Initialize data storage
        self.data_storage = HistoricalDataStorage()
        # Resume the tick timer from the last persisted tick so that a
        # patch-backend restart doesn't delay the next tick by a full interval.
        self.last_storage_update = self._load_last_tick_time()
        
        # Message rate tracking
        self.messages_history = deque(maxlen=15)
        self.published_history = deque(maxlen=15)
        self.last_messages_sent = 0
        self.last_update = datetime.now()
        
        # Initialize history with zeros
        for _ in range(15):
            self.messages_history.append(0)
            self.published_history.append(0)

    def _load_last_tick_time(self) -> datetime:
        """Return the timestamp of the last persisted tick, or now() if none exists.
        This allows the tick timer to resume correctly after a process restart
        instead of always waiting a full 3-minute interval."""
        try:
            data = self.data_storage.load_data()
            ticks = data.get('bytes_ticks') or data.get('msg_ticks') or []
            if ticks:
                last_ts = ticks[-1].get('ts', '')
                # Strip the trailing 'Z' before parsing (Python < 3.11 fromisoformat)
                parsed = datetime.fromisoformat(last_ts.rstrip('Z'))
                # If the last tick is in the past by less than one interval, use it;
                # otherwise fall back to now() so we don't write immediately on a
                # very stale restart (e.g. after days offline).
                age = (datetime.now() - parsed).total_seconds()
                if 0 < age < 3600:   # within the last hour
                    return parsed
        except Exception:
            pass
        return datetime.now()

    def format_number(self, number: int) -> str:
        """Format large numbers with K/M suffix"""
        if number >= 1_000_000:
            return f"{number/1_000_000:.1f}M"
        elif number >= 1_000:
            return f"{number/1_000:.1f}K"
        return str(number)

    def increment_user_messages(self):
        """Increment the message counter for non-$SYS messages"""
        with self._lock:
            self.message_counter.increment_count()

    def update_storage(self):
        """Update storage every 3 minutes"""
        now = datetime.now()
        if (now - self.last_storage_update).total_seconds() >= 180:  # 3 minutes
            self.last_storage_update = now   # always advance timer, even on error
            try:
                self.data_storage.add_hourly_data(
                    float(self.bytes_received_15min),
                    float(self.bytes_sent_15min)
                )
                # Also write a fine tick for the period-based charts
                self.data_storage.add_tick(
                    bytes_received=float(self.bytes_received_15min),
                    bytes_sent=float(self.bytes_sent_15min),
                    msg_received=int(self.messages_received_total),
                    msg_sent=int(self.messages_sent),
                )
            except Exception as e:
                logger.error(f"Error updating storage: {e}")

    def update_message_rates(self):
        """Calculate message rates for the last minute"""
        now = datetime.now()
        if (now - self.last_update).total_seconds() >= 60:
            with self._lock:
                published_rate = max(0, self.messages_sent - self.last_messages_sent)
                self.published_history.append(published_rate)
                self.last_messages_sent = self.messages_sent
                self.last_update = now

    def _get_clientlogs_count(self) -> int:
        """Query clientlogs service for count of non-admin connected clients (cached 5s)."""
        now = time.time()
        if now - self._clientlogs_count_ts < 5.0:
            return self._clientlogs_count_cache
        try:
            import urllib.request
            with urllib.request.urlopen(
                "http://127.0.0.1:1002/api/v1/connected-clients", timeout=2
            ) as resp:
                data = json.loads(resp.read().decode())
                count = len(data.get("clients", []))
        except Exception:
            # Fall back to $SYS count minus self when clientlogs is unavailable
            count = max(0, self.connected_clients - 1)
        self._clientlogs_count_cache = count
        self._clientlogs_count_ts = now
        return count

    def get_stats(self) -> Dict:
        """Get current MQTT statistics"""
        self.update_message_rates()
        self.update_storage()

        actual_connected_clients = self._get_clientlogs_count()

        with self._lock:
            actual_subscriptions = max(0, self.subscriptions - 2)
            
            # Get total messages from last 7 days
            total_messages = self.message_counter.get_total_count()
            
            # Get hourly data
            hourly_data = self.data_storage.get_hourly_data()
            daily_messages = self.data_storage.get_daily_messages()
            
            stats = {
                "total_connected_clients": actual_connected_clients,
                "total_messages_received": self.format_number(total_messages),
                "total_subscriptions": actual_subscriptions,
                "retained_messages": self.retained_messages,
                "messages_history": list(self.messages_history),
                "published_history": list(self.published_history),
                "bytes_stats": hourly_data,  # This contains timestamps, bytes_received, and bytes_sent
                "daily_message_stats": daily_messages,  # This contains dates and counts
                # Extended client info for gauge (subtract 1 to exclude broker monitor)
                "clients_total": max(0, self.clients_total - 1),
                "clients_maximum": max(0, self.clients_maximum - 1),
                "clients_disconnected": self.clients_disconnected,
                "clients_expired": self.clients_expired,
                # Broker info
                "broker_version": self.broker_version,
                "broker_uptime": self.broker_uptime,
                # Raw message counts for period reference
                "messages_received_raw": self.messages_received_total,
                "messages_sent_raw": self.messages_sent,
                # Load rates
                "load_msg_rx_1min": round(self.load_msg_rx_1min, 2),
                "load_msg_tx_1min": round(self.load_msg_tx_1min, 2),
                "load_bytes_rx_1min": round(self.load_bytes_rx_1min, 2),
                "load_bytes_tx_1min": round(self.load_bytes_tx_1min, 2),
                "load_connections_1min": round(self.load_connections_1min, 2),
                # QoS metrics
                "messages_inflight": self.messages_inflight,
                "messages_stored": self.messages_stored,
                "messages_store_bytes": self.messages_store_bytes,
                # Latency
                "latency_ms": self.latency_ms,
                # Real MQTT connection flag for alert evaluation
                "mqtt_connected": self._is_connected,
                # Configured connection limit (for gauge scale)
                "client_max_connections": _read_max_connections(),
            }

        # Evaluate alert conditions outside the lock
        try:
            _alert_engine.evaluate(stats, topic_store.get_all())
        except Exception as _ae:
            logger.warning("AlertEngine.evaluate error: %s", _ae)

        return stats

class MessageCounter:
    def __init__(self, file_path="message_counts.json"):
        self.file_path = file_path
        self.daily_counts = self._load_counts()

    def _load_counts(self) -> Dict[str, int]:
        """Load existing counts from JSON file"""
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, 'r') as f:
                    data = json.load(f)
                    # Convert to dict with date string keys
                    return {item['timestamp'].split()[0]: item['message_counter'] 
                           for item in data}
            except json.JSONDecodeError:
                return {}
        return {}

    def _save_counts(self):
        """Save counts to JSON file"""
        # Convert to list of dicts with timestamps
        data = [
            {
                "timestamp": f"{date} 00:00",
                "message_counter": count
            }
            for date, count in self.daily_counts.items()
        ]
        with open(self.file_path, 'w') as f:
            json.dump(data, f, indent=2)

    def increment_count(self):
        """Increment today's count and maintain 7-day window"""
        today = datetime.now().date().isoformat()
        
        # Increment or initialize today's count
        self.daily_counts[today] = self.daily_counts.get(today, 0) + 1

        # Remove counts older than 7 days
        cutoff_date = (datetime.now() - timedelta(days=7)).date().isoformat()
        self.daily_counts = {
            date: count 
            for date, count in self.daily_counts.items() 
            if date >= cutoff_date
        }

        # Save updated counts
        self._save_counts()

    def get_total_count(self) -> int:
        """Get sum of messages over last 7 days"""
        return sum(self.daily_counts.values())

# Initialize MQTT Stats
mqtt_stats = MQTTStats()

# Rate limiting
limiter = Limiter(key_func=get_remote_address)

ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "localhost").split(",")

# Global MQTT client reference (set during lifespan startup)
_mqtt_client = None

# Define the lifespan context manager for FastAPI
@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio, time as _t
    global _mqtt_client
    client = connect_mqtt()
    _mqtt_client = client
    client.loop_start()

    async def _latency_pinger():
        """Publish a ping every 15 s to measure round-trip broker latency."""
        await asyncio.sleep(5)  # let MQTT connect first
        while True:
            try:
                if _mqtt_client is not None:
                    sent_at = _t.time()
                    with mqtt_stats._lock:
                        mqtt_stats._ping_sent_at = sent_at
                    _mqtt_client.publish("bunkerm/monitor/ping", str(sent_at), qos=0)
            except Exception:
                pass
            await asyncio.sleep(15)

    _ping_task = asyncio.create_task(_latency_pinger())
    yield
    _ping_task.cancel()
    client.loop_stop()
    _mqtt_client = None

# Initialize FastAPI app with versioning (only do this once!)
app = FastAPI(
    title="MQTT Monitor API",
    version="1.0.0",
    docs_url="/api/v1/docs",
    openapi_url="/api/v1/openapi.json",
    lifespan=lifespan  # Use the lifespan context manager
)

# Add state for limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Trusted Host middleware
app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)

async def get_api_key(api_key: str = Depends(api_key_header)):
    """Validate API key"""
    logger.info(f"Received API Key Header: {api_key}")
    
    if not api_key:
        logger.error("No API key provided")
        raise HTTPException(
            status_code=403,
            detail="No API key provided"
        )
    
    if api_key != _get_current_api_key():
        logger.error(f"Invalid API key provided: {api_key}")
        raise HTTPException(
            status_code=403,
            detail="Invalid API key"
        )
    return api_key

async def log_request(request: Request):
    """Log API request details"""
    logger.info(
        f"Request: {request.method} {request.url} "
        f"Client: {request.client.host} "
        f"User-Agent: {request.headers.get('user-agent')} "
        f"Time: {datetime.now().isoformat()}"
    )

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers to all responses"""
    response = await call_next(request)
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response

class NonceManager:
    def __init__(self):
        self.used_nonces = set()
        self._cleanup_thread = threading.Thread(target=self._cleanup_expired_nonces, daemon=True)
        self._cleanup_thread.start()

    def validate_nonce(self, nonce: str, timestamp: float) -> bool:
        """Validate nonce and timestamp"""
        if nonce in self.used_nonces:
            return False
        
        # Check if timestamp is within acceptable range (5 minutes)
        current_time = datetime.now().timestamp()
        if current_time - timestamp > 300:  # 5 minutes
            return False
            
        self.used_nonces.add(nonce)
        return True

    def _cleanup_expired_nonces(self):
        """Clean up expired nonces periodically"""
        while True:
            current_time = datetime.now().timestamp()
            self.used_nonces = {
                nonce for nonce in self.used_nonces
                if current_time - float(nonce.split(':')[0]) <= 300
            }
            time.sleep(300)  # Clean up every 5 minutes

nonce_manager = NonceManager()

class TopicStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._topics: Dict[str, dict] = {}

    def update(self, topic: str, payload: bytes, retained: bool = False, qos: int = 0):
        with self._lock:
            value = payload.decode('utf-8', errors='replace') if payload else ''
            prev = self._topics.get(topic, {})
            self._topics[topic] = {
                'topic': topic,
                'value': value,
                'timestamp': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
                'count': prev.get('count', 0) + 1,
                'retained': retained,
                'qos': qos,
            }

    def get_all(self) -> list:
        with self._lock:
            return sorted(self._topics.values(), key=lambda x: x['topic'])

topic_store = TopicStore()

def on_message(client, userdata, msg):
    """Handle messages from MQTT broker"""
    if msg.topic in MONITORED_TOPICS:
        try:
            attr_name = MONITORED_TOPICS[msg.topic]
            raw = msg.payload.decode()
            with mqtt_stats._lock:
                if msg.topic in _STRING_TOPICS:
                    setattr(mqtt_stats, attr_name, raw)
                elif msg.topic in _FLOAT_TOPICS:
                    setattr(mqtt_stats, attr_name, float(raw))
                else:
                    setattr(mqtt_stats, attr_name, int(raw))
        except ValueError as e:
            logger.error(f"Error processing message from {msg.topic}: {e}")
    # Latency round-trip: measure time from when we sent the ping
    elif msg.topic == "bunkerm/monitor/ping":
        try:
            import time as _t
            sent_at = float(msg.payload.decode())
            with mqtt_stats._lock:
                mqtt_stats.latency_ms = round((_t.time() - sent_at) * 1000, 2)
        except (ValueError, AttributeError):
            pass
    # Count non-$SYS messages and track topics
    elif not msg.topic.startswith('$SYS/'):
        mqtt_stats.increment_user_messages()
        topic_store.update(msg.topic, msg.payload, getattr(msg, 'retain', False), msg.qos)

def connect_mqtt():
    """Connect to MQTT broker"""
    try:
        # Using the v5 callback format
        def on_connect(client, userdata, flags, rc, properties=None):
            if rc == 0:
                logger.info(f"Connected to MQTT Broker at {MOSQUITTO_IP}:{MOSQUITTO_PORT}!")
                mqtt_stats._is_connected = True
                client.subscribe([
                    ("$SYS/broker/#", 0),
                    ("#", 2)
                ])
                logger.info("Subscribed to topics")
            else:
                mqtt_stats._is_connected = False
                logger.error(f"Failed to connect to MQTT broker, return code {rc}")
                error_codes = {
                    1: "Incorrect protocol version",
                    2: "Invalid client identifier",
                    3: "Server unavailable",
                    4: "Bad username or password",
                    5: "Not authorized"
                }
                logger.error(f"Error details: {error_codes.get(rc, 'Unknown error')}")

        def on_disconnect(client, userdata, disconnect_flags, reason_code=None, properties=None):
            mqtt_stats._is_connected = False
            rc = reason_code if reason_code is not None else disconnect_flags
            if rc != 0:
                logger.warning(f"Unexpected MQTT disconnect (rc={rc}), will auto-reconnect")

        # Use MQTTv5 client
        try:
            client = mqtt_client.Client(mqtt_client.CallbackAPIVersion.VERSION2)
        except AttributeError:
            # Fall back to older MQTT client if necessary
            client = mqtt_client.Client(client_id="mqtt-monitor", protocol=mqtt_client.MQTTv5)
        
        client.username_pw_set(MOSQUITTO_ADMIN_USERNAME, MOSQUITTO_ADMIN_PASSWORD)
        client.on_connect = on_connect
        client.on_disconnect = on_disconnect
        client.on_message = on_message
        
        logger.info(f"Attempting to connect to MQTT broker at {MOSQUITTO_IP}:{MOSQUITTO_PORT}")
        
        # Verify parameters
        if not MOSQUITTO_IP:
            logger.error("MOSQUITTO_IP is not set or is None")
            raise ValueError("MOSQUITTO_IP must be set")
            
        # Connect with proper parameters
        client.connect(MOSQUITTO_IP, MOSQUITTO_PORT, 60)  # Fixed: use variable not string
        return client
    
    except (ConnectionRefusedError, socket.error) as e:
        logger.error(f"Connection to MQTT broker failed: {e}")
        logger.error(f"Check if Mosquitto is running on {MOSQUITTO_IP}:{MOSQUITTO_PORT}")
        # Return a dummy client that won't crash your app
        try:
            dummy_client = mqtt_client.Client(mqtt_client.CallbackAPIVersion.VERSION2)
        except AttributeError:
            dummy_client = mqtt_client.Client(client_id="dummy-client", protocol=mqtt_client.MQTTv5)
        # Override methods to do nothing
        dummy_client.loop_start = lambda: None
        dummy_client.loop_stop = lambda: None
        return dummy_client
    except Exception as e:
        logger.error(f"Unexpected error connecting to MQTT broker: {e}")
        logger.exception(e)
        # Return a dummy client that won't crash your app
        try:
            dummy_client = mqtt_client.Client(mqtt_client.CallbackAPIVersion.VERSION2)
        except AttributeError:
            dummy_client = mqtt_client.Client(client_id="dummy-client", protocol=mqtt_client.MQTTv5)
        # Override methods to do nothing
        dummy_client.loop_start = lambda: None
        dummy_client.loop_stop = lambda: None
        return dummy_client

# API endpoints
@app.get("/api/v1/stats", dependencies=[Depends(get_api_key)])
async def get_mqtt_stats(
    request: Request,
    nonce: str,
    timestamp: float
):
    """Get MQTT statistics"""
    await log_request(request)
    logger.info(f"Received request with nonce: {nonce}, timestamp: {timestamp}")
    
    try:
        if not nonce_manager.validate_nonce(nonce, timestamp):
            raise HTTPException(
                status_code=400,
                detail="Invalid nonce or timestamp"
            )
        
        # Add debug logging
        logger.info("Nonce validation passed")
        
        try:
            stats = mqtt_stats.get_stats()
            
            # Add MQTT connection status
            mqtt_connected = mqtt_stats.connected_clients > 0
            stats["mqtt_connected"] = mqtt_connected
            
            # If MQTT is not connected, add a message
            if not mqtt_connected:
                stats["connection_error"] = f"MQTT broker connection failed. Check if Mosquitto is running on {MOSQUITTO_IP}:{MOSQUITTO_PORT}"
                logger.warning(f"Serving stats with MQTT disconnected warning: {MOSQUITTO_IP}:{MOSQUITTO_PORT}")
            else:
                logger.info("Successfully retrieved stats with active MQTT connection")
        except Exception as stats_error:
            logger.error(f"Error in mqtt_stats.get_stats(): {str(stats_error)}")
            logger.exception(stats_error)  # This will log the full traceback
            
            # Return partial stats with error flag
            stats = {
                "mqtt_connected": False,
                "connection_error": f"Error getting MQTT stats: {str(stats_error)}",
                # Default values for essential fields
                "total_connected_clients": 0,
                "total_messages_received": "0",
                "total_subscriptions": 0,
                "retained_messages": 0,
                "messages_history": [0] * 15,
                "published_history": [0] * 15,
                "bytes_stats": {
                    "timestamps": [],
                    "bytes_received": [],
                    "bytes_sent": []
                },
                "daily_message_stats": {
                    "dates": [],
                    "counts": []
                }
            }
        
        response = JSONResponse(content=stats)
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, DELETE, PUT"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-API-Key"
        response.headers["Access-Control-Allow-Origin"] = os.getenv("FRONTEND_URL", "http://localhost:2000")
        response.headers["Access-Control-Allow-Credentials"] = "true"
        return response
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Unexpected error in get_stats endpoint: {str(e)}")
        logger.exception(e)  # This will log the full traceback
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )
        
        
@app.get("/api/v1/test/mqtt-stats")
async def test_mqtt_stats():
    """Test endpoint to verify MQTT stats functionality"""
    try:
        if not mqtt_stats:
            return JSONResponse(
                status_code=500,
                content={"error": "MQTT stats not initialized"}
            )
            
        # Test basic functionality
        basic_info = {
            "messages_sent": mqtt_stats.messages_sent,
            "subscriptions": mqtt_stats.subscriptions,
            "connected_clients": mqtt_stats.connected_clients,
            "data_storage_initialized": hasattr(mqtt_stats, 'data_storage')
        }
        
        return JSONResponse(content=basic_info)
        
    except Exception as e:
        logger.error(f"Error in test endpoint: {str(e)}")
        logger.exception(e)
        return JSONResponse(
            status_code=500,
            content={"error": f"Test failed: {str(e)}"}
        )

@app.get("/api/v1/test/storage")
async def test_storage():
    """Test endpoint to verify storage functionality"""
    try:
        if not hasattr(mqtt_stats, 'data_storage'):
            return JSONResponse(
                status_code=500,
                content={"error": "Data storage not initialized"}
            )
            
        # Test storage functionality
        storage_info = {
            "file_exists": os.path.exists(mqtt_stats.data_storage.filename),
            "data": mqtt_stats.data_storage.load_data()
        }
        
        return JSONResponse(content=storage_info)
        
    except Exception as e:
        logger.error(f"Error in storage test endpoint: {str(e)}")
        logger.exception(e)
        return JSONResponse(
            status_code=500,
            content={"error": f"Storage test failed: {str(e)}"}
        )

@app.get("/api/v1/stats/bytes", dependencies=[Depends(get_api_key)])
async def get_bytes_for_period(request: Request, period: str = "1h"):
    """Get bytes received/sent history for the given period (15m/30m/1h/12h/1d/7d)"""
    await log_request(request)
    if period not in _STORAGE_PERIODS:
        raise HTTPException(status_code=400, detail=f"Invalid period '{period}'. Valid: {list(_STORAGE_PERIODS.keys())}")
    return mqtt_stats.data_storage.get_bytes_for_period(period)

@app.get("/api/v1/stats/messages", dependencies=[Depends(get_api_key)])
async def get_messages_for_period(request: Request, period: str = "1h"):
    """Get messages received/sent history for the given period."""
    await log_request(request)
    if period not in _STORAGE_PERIODS:
        raise HTTPException(status_code=400, detail=f"Invalid period '{period}'. Valid: {list(_STORAGE_PERIODS.keys())}")
    return mqtt_stats.data_storage.get_messages_for_period(period)

@app.get("/api/v1/stats/topology", dependencies=[Depends(get_api_key)])
async def get_topology_stats(request: Request, limit: int = 15):
    """Top topics by message count plus client churn info."""
    await log_request(request)
    all_topics = topic_store.get_all()
    user_topics = [t for t in all_topics if not t['topic'].startswith('$')]
    top_n = sorted(user_topics, key=lambda x: x.get('count', 0), reverse=True)[:limit]
    with mqtt_stats._lock:
        return {
            "top_topics": top_n,
            "total_distinct_topics": len(user_topics),
            "clients_disconnected": mqtt_stats.clients_disconnected,
            "clients_expired": mqtt_stats.clients_expired,
        }

@app.get("/api/v1/stats/health", dependencies=[Depends(get_api_key)])
async def get_health_stats(request: Request):
    """Broker load rates and round-trip latency."""
    await log_request(request)
    with mqtt_stats._lock:
        return {
            "load_msg_rx_1min":      round(mqtt_stats.load_msg_rx_1min, 2),
            "load_msg_tx_1min":      round(mqtt_stats.load_msg_tx_1min, 2),
            "load_bytes_rx_1min":    round(mqtt_stats.load_bytes_rx_1min, 2),
            "load_bytes_tx_1min":    round(mqtt_stats.load_bytes_tx_1min, 2),
            "load_connections_1min": round(mqtt_stats.load_connections_1min, 2),
            "latency_ms":            mqtt_stats.latency_ms,
        }

@app.get("/api/v1/stats/resources", dependencies=[Depends(get_api_key)])
async def get_resource_stats(request: Request):
    """Mosquitto process resource usage. CPU% is only available when Mosquitto
    runs in the same container; heap memory is always available via $SYS topics."""
    await log_request(request)
    cpu_pct = None
    try:
        import psutil
        procs = [p for p in psutil.process_iter(['name', 'pid', 'cpu_percent', 'memory_info'])
                 if 'mosquitto' in (p.info.get('name') or '')]
        if procs:
            proc = procs[0]
            cpu_pct = round(proc.cpu_percent(interval=0.1), 1)
    except Exception as _e:
        logger.warning("Resource stats error: %s", _e)
    with mqtt_stats._lock:
        heap_cur = mqtt_stats.heap_current
        heap_max = mqtt_stats.heap_maximum
    return {
        "mosquitto_cpu_pct": cpu_pct,
        "mosquitto_rss_bytes": heap_cur if heap_cur > 0 else None,
        "mosquitto_vms_bytes": heap_max if heap_max > 0 else None,
    }

@app.get("/api/v1/stats/qos", dependencies=[Depends(get_api_key)])
async def get_qos_stats(request: Request):
    """QoS in-flight and stored message metrics."""
    await log_request(request)
    with mqtt_stats._lock:
        total_rx = mqtt_stats.messages_received_total
        total_retained = mqtt_stats.retained_messages
        retained_ratio = round(total_retained / max(total_rx, 1) * 100, 1)
        return {
            "messages_inflight":    mqtt_stats.messages_inflight,
            "messages_stored":      mqtt_stats.messages_stored,
            "messages_store_bytes": mqtt_stats.messages_store_bytes,
            "clients_disconnected": mqtt_stats.clients_disconnected,
            "clients_expired":      mqtt_stats.clients_expired,
            "retained_ratio":       retained_ratio,
        }

@app.get("/api/v1/alerts/broker", dependencies=[Depends(get_api_key)])
async def get_broker_alerts(request: Request):
    """Return currently active broker alerts."""
    await log_request(request)
    return {"alerts": _alert_engine.get_alerts()}


@app.get("/api/v1/alerts/broker/history", dependencies=[Depends(get_api_key)])
async def get_broker_alert_history(request: Request):
    """Return the alert history (up to 200 most recent events, newest first)."""
    await log_request(request)
    history = list(reversed(_alert_engine.get_history()))
    return {"history": history, "total": len(history)}


@app.post("/api/v1/alerts/broker/{alert_id}/acknowledge", dependencies=[Depends(get_api_key)])
async def acknowledge_broker_alert(request: Request, alert_id: str):
    """Acknowledge (dismiss) a broker alert by its id."""
    await log_request(request)
    if _alert_engine.acknowledge(alert_id):
        return {"status": "acknowledged"}
    raise HTTPException(status_code=404, detail="Alert not found")


@app.get("/api/v1/topics", dependencies=[Depends(get_api_key)])
async def get_topics(request: Request):
    """Get all tracked MQTT topics with latest values"""
    await log_request(request)
    return {"topics": topic_store.get_all()}

class PublishRequest(BaseModel):
    topic: str
    payload: str = ""
    qos: int = 0
    retain: bool = False

@app.post("/api/v1/publish", dependencies=[Depends(get_api_key)])
async def publish_message(request: Request, body: PublishRequest):
    """Publish a message to a topic via the broker"""
    await log_request(request)
    if _mqtt_client is None:
        raise HTTPException(status_code=503, detail="MQTT client not connected")
    result = _mqtt_client.publish(body.topic, body.payload, qos=body.qos, retain=body.retain)
    if result.rc != 0:
        raise HTTPException(status_code=500, detail=f"Publish failed (rc={result.rc})")
    return {"status": "published", "topic": body.topic}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}

if __name__ == "__main__":
    try:
        # Check if the port is already in use
        port = int(os.getenv("APP_PORT", "1001"))
        host = os.getenv("APP_HOST", "0.0.0.0")
        
        # Try to bind to the port to check if it's available
        test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        test_socket.settimeout(1)
        
        # Set SO_REUSEADDR option to avoid "address already in use" errors
        test_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            test_socket.bind((host, port))
            port_available = True
        except socket.error:
            port_available = False
        finally:
            test_socket.close()
        
        if not port_available:
            logger.warning(f"Port {port} is already in use, switching to port 1002")
            port = 1002
        
        # Update logging level
        logging.basicConfig(level=logging.WARNING)
        
        # Run the application
        logger.info(f"Starting MQTT Monitor API on {host}:{port}")
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="warning"
        )
    except Exception as e:
        logger.critical(f"Failed to start application: {e}")
        logger.exception(e)