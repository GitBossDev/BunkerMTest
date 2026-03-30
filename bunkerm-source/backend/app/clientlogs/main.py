# Copyright (c) 2025 BunkerM
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
# http://www.apache.org/licenses/LICENSE-2.0
# Distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.
#
import re
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from collections import deque
import subprocess
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
import uvicorn
from pydantic import BaseModel
import uuid
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Environment variables
MOSQUITTO_ADMIN_USERNAME = os.getenv("MOSQUITTO_ADMIN_USERNAME", "bunker")
MOSQUITTO_ADMIN_PASSWORD = os.getenv("MOSQUITTO_ADMIN_PASSWORD", "bunker")
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
])


def _ts_to_iso(unix_ts: str) -> str:
    """Convert a Unix timestamp string to a UTC ISO 8601 string.

    Always produces UTC+00:00 output so the browser can convert to the
    user's local timezone correctly via new Date(...).
    """
    return datetime.fromtimestamp(int(unix_ts), tz=timezone.utc).isoformat()


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
        self.events: deque = deque(maxlen=500)

        # Track "New connection from IP:PORT" lines so auth failures
        # can be attributed to an IP address. Key = unix timestamp string.
        self._pending_ip: Dict[str, Tuple[str, int]] = {}

        # Track (client_id, topic) pairs for publish deduplication.
        # Reset per client on new connection.
        self._seen_publishes: set = set()

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
        return username == os.getenv("MOSQUITTO_ADMIN_USERNAME", "bunker")

    def _is_internal_auto_client(self, client_id: str) -> bool:
        """Return True for mosquitto_ctrl ephemeral connections (auto-UUID pattern)."""
        return bool(_AUTO_CLIENT_RE.match(client_id))

    # ----------------------------------------------------- individual parsers

    def _parse_raw_new_connection(self, log_line: str) -> bool:
        """Track 'New connection from IP:PORT' for auth-failure attribution."""
        m = re.match(r"(\d+): New connection from (\d+\.\d+\.\d+\.\d+):(\d+) on port", log_line)
        if not m:
            return False
        ts, ip, port = m.groups()
        self._pending_ip[ts] = (ip, int(port))
        if len(self._pending_ip) > 50:
            del self._pending_ip[min(self._pending_ip)]
        return True

    def parse_connection_log(self, log_line: str) -> Optional[MQTTEvent]:
        pattern = (r"(\d+): New client connected from (\d+\.\d+\.\d+\.\d+):(\d+)"
                   r" as (\S+) \(p(\d+), c(\d+), k(\d+), u'([^']+)'\)")
        m = re.match(pattern, log_line)
        if not m:
            return None

        ts, ip, port, client_id, protocol, clean, keep_alive, username = m.groups()
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
        self._client_usernames[client_id] = username
        # Successful connection — remove from pending IP table
        self._pending_ip.pop(ts, None)

        # Internal mosquitto_ctrl connections (auto-UUID from localhost): skip entirely.
        # They are ephemeral tool calls — not real clients worth showing.
        if self._is_admin(username) and self._is_internal_auto_client(client_id):
            return None

        # All other clients (non-admin OR external admin like MQTT Explorer) → track
        self.connected_clients[client_id] = event
        # Reset seen-publishes so first publish after reconnect is always recorded
        self._seen_publishes = {k for k in self._seen_publishes
                                if not k.startswith(f"{client_id}:")}
        return event

    def parse_disconnection_log(self, log_line: str) -> Optional[MQTTEvent]:
        # Do NOT handle "not authorised" here — that is for parse_auth_failure_log
        if "not authorised" in log_line:
            return None

        m = re.match(r"(\d+): Client (\S+) (?:disconnected|closed its connection)", log_line)
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
        # Keep _client_usernames entry so auth failures on reconnect can show the last known username.
        return event

    def parse_auth_failure_log(self, log_line: str) -> Optional[MQTTEvent]:
        """Parse 'Client X disconnected, not authorised.' lines."""
        m = re.match(r"(\d+): Client (\S+) disconnected, not authorised\.", log_line)
        if not m:
            return None

        ts, client_id = m.groups()
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
        if not ts_str.isdigit():
            return None

        parts = content.split()
        if len(parts) != 3:
            return None

        client_id, qos_str, topic = parts
        if qos_str not in ("0", "1", "2"):
            return None
        if client_id in _MOSQUITTO_LOG_KEYWORDS:
            return None
        # Topic must look like an MQTT topic (contains / or starts with $)
        if "/" not in topic and not topic.startswith("$"):
            return None

        username, protocol_level, ip, port, clean, keep_alive = self._get_client_info(client_id)
        if self._is_admin(username):
            return None

        return MQTTEvent(
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

    def parse_publish_log(self, log_line: str) -> Optional[MQTTEvent]:
        """Parse PUBLISH log entries, deduplicated by (client_id, topic)."""
        pattern = (r"(\d+): Received PUBLISH from (\S+)"
                   r" \(d\d, q(\d), r\d, m\d+, '([^']+)', \.\.\. \((\d+) bytes\)\)")
        m = re.match(pattern, log_line)
        if not m:
            return None

        ts, client_id, qos_str, topic, size_str = m.groups()
        username, protocol_level, ip, port, clean, keep_alive = self._get_client_info(client_id)
        if self._is_admin(username):
            return None

        key = f"{client_id}:{topic}"
        if key in self._seen_publishes:
            return None
        self._seen_publishes.add(key)

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
        )

    # ---------------------------------------------------- processing pipeline

    def process_line(self, line: str, replay: bool = False) -> None:
        """Run a log line through all parsers in priority order.

        During replay (startup), only connection state is rebuilt.
        Events are NOT added to the history (fresh history on service start).
        Publish deduplication is intentionally NOT pre-loaded from replay so
        the first live publish to each topic after a restart is always visible.
        """
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

# Initialize FastAPI app with versioning
app = FastAPI(
    title="Mosquitto Management API",
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[ALLOWED_HOSTS],
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
async def get_mqtt_events(limit: int = 200):
    all_events = list(mqtt_monitor.events)
    sorted_events = sorted(all_events, key=lambda x: x.timestamp, reverse=True)[:limit]
    return {"events": [event.dict() for event in sorted_events]}

@app.get("/api/v1/connected-clients")
async def get_connected_clients():
    return {"clients": [client.dict() for client in mqtt_monitor.connected_clients.values()]}

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

if __name__ == "__main__":
    # Start log monitoring in a separate thread
    import threading
    log_thread = threading.Thread(target=monitor_mosquitto_logs, daemon=True)
    log_thread.start()
    
    # Start the FastAPI server without SSL
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=1002
    )