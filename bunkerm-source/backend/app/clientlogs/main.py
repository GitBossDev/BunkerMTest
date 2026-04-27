# Copyright (c) 2025 BunkerM
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
# http://www.apache.org/licenses/LICENSE-2.0
# Distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.
#
import re
import json
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from collections import deque
import subprocess
from fastapi import FastAPI, HTTPException, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.security.api_key import APIKeyHeader
import uvicorn
from pydantic import BaseModel
import uuid
import os
from dotenv import load_dotenv

from services.clientlogs_service import persist_mqtt_event as _persist_mqtt_event_from_service

# Load environment variables
load_dotenv()

# Environment variables
MOSQUITTO_ADMIN_USERNAME = os.getenv("MOSQUITTO_ADMIN_USERNAME", "admin")
MOSQUITTO_ADMIN_PASSWORD = os.getenv("MOSQUITTO_ADMIN_PASSWORD", "Usuario@1")
MOSQUITTO_IP = os.getenv("MOSQUITTO_IP", "localhost")
MOSQUITTO_PORT = os.getenv("MOSQUITTO_PORT", "1883")

# Base command for mosquitto_ctrl
MOSQUITTO_BASE_COMMAND = [
    "mosquitto_ctrl",
    "-h", MOSQUITTO_IP,
    "-p", MOSQUITTO_PORT,
    "-u", MOSQUITTO_ADMIN_USERNAME,
    "-P", MOSQUITTO_ADMIN_PASSWORD,
    "dynsec"
]

# Regex for Mosquitto auto-generated client IDs used by mosquitto_ctrl.
# Pattern: auto-XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX  (UUID-like, all hex).
# These are ephemeral tool connections from localhost — never real clients.
_AUTO_CLIENT_RE = re.compile(
    r'^auto-[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$'
)

# Known Mosquitto log keywords that appear as the first token after the timestamp.
# Used to distinguish subscribe-type log lines from general log messages.
_MOSQUITTO_LOG_KEYWORDS = frozenset([
    'New', 'Sending', 'Received', 'Client', 'Warning', 'Config',
    'Loading', 'Opening', 'No', 'mosquitto', 'Error', 'Notice',
    'Socket', 'Timeout', 'Plugin', 'Saving', 'Using', 'Log',
    'Restored', 'Bridge', 'Persistence', 'TLS', 'Websockets', 'Info:',
])


# Captures both Unix timestamps (digits) and Mosquitto 2.1.2 ISO 8601 timestamps.
_TS_CAPTURE = r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}|\d+)'
# Pre-compiled for use in parse_subscription_log (no group needed there)
_TS_RE = re.compile(r'^(?:\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}|\d+)$')

# How long (seconds) to suppress duplicate Publish events for the same topic.
# Keeps the event stream readable when clients publish at high frequency.
# 0 = disabled, show all publish events
_PUBLISH_DEDUP_SECONDS = 0

# Topic prefixes that are internal to the BunkerM platform.
# These are never shown in the client events view — they are system/infrastructure
# traffic, not end-user MQTT data.
_INTERNAL_TOPIC_PREFIXES = ('$', 'bunkerm/monitor/')


def _ts_to_iso(ts: str) -> str:
    """Convert a Unix or ISO 8601 timestamp string to a UTC ISO 8601 string.

    Always produces UTC+00:00 output so the browser can convert to the
    user's local timezone correctly via new Date(...).
    """
    if ts.isdigit():
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
    try:
        dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S")
        return dt.replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        return ts


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
    topic: Optional[str] = None   # Populated for Subscribe and Publish events
    qos: Optional[int] = None     # Populated for Subscribe and Publish events


class MQTTMonitor:
    def __init__(self):
        self.connected_clients: Dict[str, MQTTEvent] = {}
        self.events: deque = deque(maxlen=1000)
        # cumulative subscription count per topic pattern (resets on service restart)
        self._subscription_counts: Dict[str, int] = {}

        # Track last subscribe/publish timestamp per client_id.
        # Used as fallback to infer connectivity when connection log events are missing.
        self._last_seen: Dict[str, float] = {}

        # Track "New connection from IP:PORT" lines so auth failures
        # can be attributed to an IP address. Key = unix timestamp string.
        self._pending_ip: Dict[str, Tuple[str, int]] = {}

        # Last known connection info per username (ip, port, timestamp).
        # Updated on every successful connection, never cleared on disconnect.
        self._last_connection_info: Dict[str, dict] = {}

        # Time-based publish deduplication: topic → last-event unix timestamp.
        # Each unique topic is shown at most once per _PUBLISH_DEDUP_SECONDS.
        self._last_publish_ts: Dict[str, float] = {}

        # Username lookup for ALL clients (admin + non-admin), so subscribe/publish
        # parsers can correctly filter out admin-owned connections even when those
        # connections are not stored in connected_clients.
        self._client_usernames: Dict[str, str] = {}

    # ---------------------------------------------------------------- helpers

    def _get_client_info(self, client_id: str) -> Tuple[str, str, str, int, bool, int]:
        """Return (username, protocol, ip, port, clean_session, keep_alive)."""
        if client_id in self.connected_clients:
            ev = self.connected_clients[client_id]
            return ev.username, ev.protocol_level, ev.ip_address, ev.port, ev.clean_session, ev.keep_alive
        # Also check admin-only connections that are not in connected_clients
        if client_id in self._client_usernames:
            return self._client_usernames[client_id], "MQTT vunknown", "unknown", 0, False, 0
        return "unknown", "MQTT vunknown", "unknown", 0, False, 0

    def _is_admin(self, username: str) -> bool:
        return username == os.getenv("MOSQUITTO_ADMIN_USERNAME", "admin")

    def _is_internal_auto_client(self, client_id: str) -> bool:
        """Return True for mosquitto_ctrl ephemeral connections (auto-UUID pattern)."""
        return bool(_AUTO_CLIENT_RE.match(client_id))

    # ----------------------------------------------------- individual parsers

    def _parse_raw_new_connection(self, log_line: str) -> bool:
        """Track 'New connection from IP:PORT' for auth-failure attribution."""
        m = re.match(_TS_CAPTURE + r": New connection from (\d+\.\d+\.\d+\.\d+):(\d+) on port", log_line)
        if not m:
            return False
        ts, ip, port = m.groups()
        self._pending_ip[ts] = (ip, int(port))
        if len(self._pending_ip) > 50:
            del self._pending_ip[min(self._pending_ip)]
        return True

    def parse_connection_log(self, log_line: str) -> Optional[MQTTEvent]:
        # Username is optional in Mosquitto 2.1.2 for clients without credentials
        pattern = (_TS_CAPTURE + r": New client connected from (\d+\.\d+\.\d+\.\d+):(\d+)"
                   r" as (\S+) \(p(\d+), c(\d+), k(\d+)(?:, u'([^']+)')?\)")
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

        # Track username for ALL clients (admin + non-admin) before any early returns
        if len(self._client_usernames) > 2000:
            # Evict oldest 200 entries to cap memory under reconnect storms
            for k in list(self._client_usernames.keys())[:200]:
                del self._client_usernames[k]
        self._client_usernames[client_id] = username
        # Successful connection — remove from pending IP table
        self._pending_ip.pop(ts, None)
        # Update last known connection info for this username
        self._last_connection_info[username] = {
            "ip_address": ip,
            "port": int(port),
            "timestamp": event.timestamp,
        }

        # Internal mosquitto_ctrl connections (auto-UUID from localhost): skip entirely.
        # They are ephemeral tool calls — not real clients worth showing.
        if self._is_admin(username) and self._is_internal_auto_client(client_id):
            return None

        # All other clients (non-admin OR external admin like MQTT Explorer) → track
        self.connected_clients[client_id] = event
        return event

    def parse_disconnection_log(self, log_line: str) -> Optional[MQTTEvent]:
        # Do NOT handle "not authorised" here — that is for parse_auth_failure_log
        if "not authorised" in log_line:
            return None

        # Mosquitto 2.1.2 format: "Client X [IP:PORT] disconnected: reason."
        m = re.match(_TS_CAPTURE + r": Client (\S+)(?: \[[^\]]+\])? (?:disconnected|closed its connection)", log_line)
        if not m:
            return None

        ts, client_id = m.groups()
        if client_id not in self.connected_clients:
            return None

        conn = self.connected_clients[client_id]
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
        )
        del self.connected_clients[client_id]
        # Remove from _last_seen so the fallback in get_connected_clients() doesn't
        # re-surface a disconnected client as still-online during the 10-minute window.
        # If the client reconnects and sends a subscribe, _last_seen will be updated again.
        self._last_seen.pop(client_id, None)
        # Keep _client_usernames entry so auth failures on reconnect can show the last known username.
        return event

    def parse_auth_failure_log(self, log_line: str) -> Optional[MQTTEvent]:
        """Parse 'Client X [IP:PORT] disconnected: not authorised.' lines."""
        m = re.match(
            _TS_CAPTURE + r": Client (\S+)(?: \[(\d+\.\d+\.\d+\.\d+):(\d+)\])? disconnected: not authorised\.",
            log_line
        )
        if not m:
            return None

        ts, client_id, ip_bracket, port_bracket = m.groups()
        # Use IP embedded in the log line when present (Mosquitto 2.x format).
        # Fall back to _pending_ip keyed by timestamp for older formats.
        if ip_bracket:
            ip, port = ip_bracket, int(port_bracket)
        else:
            ip, port = self._pending_ip.pop(ts, ("unknown", 0))
        # Mosquitto does NOT log the attempted username on auth failure.
        # Showing any previously-known username would be misleading (e.g. the user
        # deliberately tried a different credential). Leave it as "unknown".

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
        )

    def parse_subscription_log(self, log_line: str) -> Optional[MQTTEvent]:
        """Parse Mosquitto subscribe-type log lines.

        Mosquitto emits these when log_type includes 'subscribe':
            <unix_ts>: <client_id> <qos> <topic>
        """
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
        # Accept any non-empty topic (bare names, wildcards # / +, and $SYS topics are all valid)

        username, protocol_level, ip, port, clean, keep_alive = self._get_client_info(client_id)
        if self._is_admin(username):
            return None

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
        # Track cumulative subscription count per topic pattern
        self._subscription_counts[topic] = self._subscription_counts.get(topic, 0) + 1
        # Record last activity timestamp for this client (for connectivity inference)
        self._last_seen[client_id] = time.time()
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
            return None
        client_id = client_match.group(1)
        
        # Extraer tópico (entre comillas simples)
        topic_match = re.search(r"'([^']+)'", log_line)
        if not topic_match:
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
        if self._is_admin(username):
            pass  # Allow admin publishes now
        
        event_ts = time.time()
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

    # ---------------------------------------------------- processing pipeline

    def process_line(self, line: str, replay: bool = False) -> None:
        """Run a log line through all parsers in priority order.

        During replay (startup), only connection state is rebuilt.
        Events are NOT added to the history (fresh history on service start).
        Publish deduplication is intentionally NOT pre-loaded from replay so
        the first live publish to each topic after a restart is always visible.
        """
        # Fast early-exit for high-frequency lines that no parser handles.
        # These dominate the log during normal operation and under connection storms.
        if (': Sending PUBLISH to ' in line
                or ': Denied PUBLISH from ' in line
                or ': Sending SUBACK to ' in line
                or ': Sending PUBACK to ' in line
                or ': Received SUBSCRIBE from ' in line
                or ': Received PINGREQ from ' in line
                or ': Sending PINGRESP to ' in line):
            return

        # Raw connection tracking (state only, no event)
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
                if not replay:
                    self.events.append(event)
                return

        # Publish: only process during live mode (not replay)
        if not replay:
            event = self.parse_publish_log(line)
            if event is not None:
                self.events.append(event)


ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "localhost").split(",")
# Origins permitidos para CORS (protocolo+host+puerto de la interfaz web)
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:2000").split(",")]

# Autenticación por clave API compartida
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)
_api_key_cache: dict = {"key": "", "ts": 0.0}


def _get_current_api_key() -> str:
    """Devuelve la clave API activa, refrescando desde archivo cada 5 s."""
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
    _api_key_cache["key"] = key
    _api_key_cache["ts"] = now
    return key


async def _require_api_key(api_key: str = Security(_api_key_header)) -> str:
    """Dependencia FastAPI que valida la clave API en el header X-API-Key."""
    if api_key != _get_current_api_key():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API Key")
    return api_key


# Initialize FastAPI app with versioning
app = FastAPI(
    title="Mosquitto Management API",
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
    # Todos los endpoints requieren autenticación por clave API
    dependencies=[Security(_require_api_key)],
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Trusted Host middleware
app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)

# Initialize MQTT monitor
mqtt_monitor = MQTTMonitor()

def execute_mosquitto_command(command: list) -> None:
    """Execute a mosquitto_ctrl command with the base configuration"""
    try:
        full_command = MOSQUITTO_BASE_COMMAND + command
        subprocess.run(full_command, check=True)
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Command failed: {str(e)}")

# Updated endpoint paths to match the frontend expectations
@app.post("/api/v1/enable/{username}")
async def enable_client(username: str):
    try:
        execute_mosquitto_command(["enableClient", username])
        return {"status": "success", "message": f"Client {username} Enabled"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to enable client: {str(e)}")

@app.post("/api/v1/disable/{username}")
async def disable_client(username: str):
    try:
        execute_mosquitto_command(["disableClient", username])
        return {"status": "success", "message": f"Client {username} Disabled"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to disable client: {str(e)}")

@app.get("/api/v1/events")
async def get_mqtt_events(limit: int = 1000):
    all_events = list(mqtt_monitor.events)
    sorted_events = sorted(all_events, key=lambda x: x.timestamp, reverse=True)[:limit]
    return {"events": [event.dict() for event in sorted_events]}

@app.get("/api/v1/connected-clients")
async def get_connected_clients():
    """Return connected clients.

    Primary source: clients tracked as connected via log-parsed CONNECT events.
    Fallback: clients seen via subscribe events in the last 10 minutes that are
    not marked as disconnected.  This handles the common case where the broker
    config only had 'log_type subscribe' (no notice/information) so connection
    events were never logged.
    """
    # Start with log-tracked clients (authoritative when present)
    result: Dict[str, MQTTEvent] = dict(mqtt_monitor.connected_clients)

    # Supplement with clients seen recently via subscribe events
    cutoff = time.time() - 600  # 10 minutes
    for cid, last_ts in mqtt_monitor._last_seen.items():
        if last_ts < cutoff:
            continue
        if cid in result:
            continue  # already tracked as connected
        username, protocol_level, ip, port, clean, keep_alive = mqtt_monitor._get_client_info(cid)
        if mqtt_monitor._is_admin(username):
            continue
        # Build a synthetic event using last known connection info when available
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

    return {"clients": [client.dict() for client in result.values()]}

@app.get("/api/v1/last-connection")
async def get_last_connection():
    """Return the last known connection info (ip, port, timestamp) per username."""
    return {"info": mqtt_monitor._last_connection_info}

@app.get("/api/v1/top-subscribed")
async def get_top_subscribed(limit: int = 15):
    """Return top topics by cumulative subscription count since service start."""
    counts = mqtt_monitor._subscription_counts
    top = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:limit]
    return {
        "top_subscribed": [{"topic": t, "count": c} for t, c in top],
        "total_distinct_subscribed": len(counts),
    }

def monitor_mosquitto_logs():
    print("Starting mosquitto log monitoring...")
    log_file = "/var/log/mosquitto/mosquitto.log"

    # --- Startup replay: scan the ENTIRE log for connection/disconnect events ---
    # Using grep is orders of magnitude faster than tail + full line processing,
    # and guarantees we find clients that connected a long time ago (e.g. the
    # simulator that has been running for hours before a service restart).
    # Lines are returned in file order, preserving chronological sequence.
    try:
        result = subprocess.run(
            [
                "grep", "-E",
                "New client connected from|Client .+ disconnected|Client .+ closed its connection",
                log_file,
            ],
            capture_output=True, text=True,
        )
        for replay_line in result.stdout.splitlines():
            replay_line = replay_line.strip()
            if replay_line:
                mqtt_monitor.process_line(replay_line, replay=True)
        print(
            f"Startup replay: {len(mqtt_monitor.connected_clients)} connected, "
            f"{len(mqtt_monitor._client_usernames)} known usernames."
        )
    except Exception as exc:
        print(f"Startup replay failed: {exc}")

    # Replay subscribe events so _subscription_counts is pre-populated.
    # Subscribe log format: "<timestamp>: <client_id> <qos> <topic>"
    # Exactly 3 tokens after the ": " separator; topic can't contain spaces.
    try:
        result_sub = subprocess.run(
            ["grep", "-E", r": [^ ]+ [012] [^ ]+$", log_file],
            capture_output=True, text=True,
        )
        for replay_line in result_sub.stdout.splitlines():
            replay_line = replay_line.strip()
            if replay_line:
                mqtt_monitor.process_line(replay_line, replay=True)
        print(
            f"Startup replay: {len(mqtt_monitor._subscription_counts)} distinct subscribed topics."
        )
    except Exception as exc:
        print(f"Startup subscribe replay failed: {exc}")

    # After all replays: detect if mosquitto was previously restarted.
    # If the last "terminating" log entry is more recent than the last client
    # connection event we replayed, those connections ended at shutdown and the
    # connected_clients / _last_seen dicts contain stale data.  Clear them so
    # the UI shows no ghost connections until clients actually reconnect.
    try:
        term_grep = subprocess.run(
            ["grep", "mosquitto version .* terminating", log_file],
            capture_output=True, text=True,
        )
        if term_grep.returncode == 0:
            term_lines = [l.strip() for l in term_grep.stdout.splitlines() if l.strip()]
            if term_lines and mqtt_monitor.connected_clients:
                last_term_raw = term_lines[-1].split(": ")[0]
                # Parse the terminating timestamp (ISO or unix)
                if last_term_raw.isdigit():
                    last_term_dt = datetime.fromtimestamp(int(last_term_raw), tz=timezone.utc)
                else:
                    last_term_dt = datetime.fromisoformat(last_term_raw).replace(tzinfo=timezone.utc)
                # Find the latest connection timestamp among replayed connected clients
                last_conn_dt = max(
                    (datetime.fromisoformat(ev.timestamp) for ev in mqtt_monitor.connected_clients.values()),
                    default=datetime.min.replace(tzinfo=timezone.utc),
                )
                if last_term_dt > last_conn_dt:
                    stale = len(mqtt_monitor.connected_clients)
                    mqtt_monitor.connected_clients.clear()
                    mqtt_monitor._last_seen.clear()
                    print(
                        f"Startup: mosquitto restart detected (term={last_term_raw}) — "
                        f"cleared {stale} stale connected client(s)."
                    )
    except Exception as exc:
        print(f"Startup: restart detection failed: {exc}")

    process = subprocess.Popen(
        ["tail", "-f", log_file],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )
    print("Mosquitto log monitoring started.")

    while True:
        line = process.stdout.readline()
        if line:
            mqtt_monitor.process_line(line.strip())


def monitor_mqtt_publishes() -> None:
    """Subscribe to '#' as admin to capture PUBLISH events.

    This runs in a background thread and appends Publish events to
    mqtt_monitor.events.  Deduplication is time-based: at most one event
    per topic per _PUBLISH_DEDUP_SECONDS seconds.

    The admin client is excluded from appearing in publish events just as
    it is in log-based parsers.
    """
    try:
        import paho.mqtt.client as paho_mqtt
    except ImportError:
        print("paho-mqtt not available; publish monitoring disabled.")
        return

    def _on_connect(client, userdata, flags, rc, properties=None):
        if rc == 0:
            client.subscribe('#', 0)
            print("MQTT publish monitor: subscribed to #")
        else:
            print(f"MQTT publish monitor: connect failed rc={rc}")

    def _on_message(client, userdata, message):
        # Skip internal broker topics ($SYS/...) and platform-internal topics.
        # NOTE: The paho subscription gives us topic/payload/QoS only — the MQTT
        # protocol does not expose the publisher's client ID or username to
        # subscribers. To get real publisher identity, enable log_type debug in
        # mosquitto.conf: the log-based parse_publish_log() parser handles those
        # lines and will populate client_id/username/ip correctly. The 60-second
        # dedup window prevents duplicate events when both paths are active.
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
            _persist_mqtt_event_from_service(event)
        except Exception as exc:
            print(f"Failed to persist event to database: {exc}")

    mqtt_client = paho_mqtt.Client(
        client_id="bunkerm-publish-monitor",
        protocol=paho_mqtt.MQTTv311,
    )
    mqtt_client.username_pw_set(MOSQUITTO_ADMIN_USERNAME, MOSQUITTO_ADMIN_PASSWORD)
    mqtt_client.on_connect = _on_connect
    mqtt_client.on_message = _on_message

    while True:
        try:
            mqtt_client.connect(MOSQUITTO_IP, int(MOSQUITTO_PORT), keepalive=60)
            mqtt_client.loop_forever()
        except Exception as exc:
            print(f"MQTT publish monitor error: {exc}. Reconnecting in 10 s…")
            time.sleep(10)


if __name__ == "__main__":
    import threading
    log_thread = threading.Thread(target=monitor_mosquitto_logs, daemon=True)
    log_thread.start()

    publish_thread = threading.Thread(target=monitor_mqtt_publishes, daemon=True)
    publish_thread.start()

    # Start the FastAPI server without SSL
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=1002
    )