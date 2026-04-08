# Copyright (c) 2025 BunkerM
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
# http://www.apache.org/licenses/LICENSE-2.0
# Distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.
#
# backend/app/config/mosquitto_config.py
from logging.handlers import RotatingFileHandler
import logging
import os
import re
import shutil
import subprocess
from datetime import datetime
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, File, HTTPException, Depends, Security, UploadFile, status
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel

# Router setup
router = APIRouter(tags=["mosquitto_config"])

# Configure logging
logger = logging.getLogger(__name__)

# Environment variables
_API_KEY_CACHE: dict = {"key": "", "ts": 0.0}

def _get_current_api_key() -> str:
    """Return the active API key, refreshing from file every 5 s."""
    import time as _t
    now = _t.time()
    if _API_KEY_CACHE["key"] and now - _API_KEY_CACHE["ts"] < 5.0:
        return _API_KEY_CACHE["key"]
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
    _API_KEY_CACHE["key"] = key
    _API_KEY_CACHE["ts"] = now
    return key

MOSQUITTO_CONF_PATH = os.getenv("MOSQUITTO_CONF_PATH", "/etc/mosquitto/mosquitto.conf")
BACKUP_DIR = os.getenv("MOSQUITTO_BACKUP_DIR", "/tmp/mosquitto_backups")

# Security
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

# Create backup directory if it doesn't exist
os.makedirs(BACKUP_DIR, exist_ok=True)


async def get_api_key(api_key_header: str = Security(api_key_header)):
    if api_key_header != _get_current_api_key():
        logger.warning(f"Invalid API key attempt")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API Key"
        )
    return api_key_header


# Models for request validation
class Listener(BaseModel):
    port: int
    bind_address: Optional[str] = None
    per_listener_settings: Optional[bool] = False
    max_connections: Optional[int] = -1
    protocol: Optional[str] = None   # None = MQTT/TCP (default); "websockets" = WebSocket


class TLSListenerConfig(BaseModel):
    enabled: bool = False
    port: int = 8883
    cafile: Optional[str] = None       # path inside container, e.g. /etc/mosquitto/certs/ca.crt
    certfile: Optional[str] = None
    keyfile: Optional[str] = None
    require_certificate: bool = False  # force mutual TLS (client certs)
    tls_version: Optional[str] = None  # e.g. 'tlsv1.3'; None = auto


class MosquittoConfig(BaseModel):
    config: Dict[str, Any]
    listeners: List[Listener] = []
    max_inflight_messages: Optional[int] = None   # global Mosquitto setting
    max_queued_messages: Optional[int] = None      # global Mosquitto setting
    tls: Optional[TLSListenerConfig] = None        # TLS listener (port 8883)


# Cert directory inside the container (shared volume)
CERTS_DIR = os.getenv("MOSQUITTO_CERTS_DIR", "/etc/mosquitto/certs")
# Required log types — always written regardless of user config
_REQUIRED_LOG_TYPES = ["error", "warning", "notice", "information", "subscribe"]

# Default configuration written when user resets mosquitto settings.
# Paths must match the standalone container's view (same as the shared volume paths).
DEFAULT_CONFIG = """# MQTT listener on port 1900
listener 1900
per_listener_settings false
max_connections -1
allow_anonymous false

# WebSocket listener
listener 9001
protocol websockets

# Dynamic Security Plugin configuration
plugin /usr/lib/mosquitto_dynamic_security.so
plugin_opt_config_file /var/lib/mosquitto/dynamic-security.json

# Custom bridge configs (written by aws-bridge / azure-bridge APIs)
include_dir /etc/mosquitto/conf.d

# Logging
log_dest stdout
log_type error
log_type warning
log_type notice
log_type information
log_type subscribe
log_timestamp true
log_timestamp_format %Y-%m-%dT%H:%M:%S
connection_messages true

# Persistence
persistence true
persistence_location /var/lib/mosquitto
persistence_file mosquitto.db
autosave_interval 300
"""


def _signal_mosquitto_reload() -> None:
    """Write the reload trigger file so the mosquitto entrypoint sends SIGHUP."""
    try:
        with open("/var/lib/mosquitto/.reload", "w") as _f:
            _f.write("")
        logger.info("Reload signal written for mosquitto standalone container")
    except Exception as e:
        logger.warning(f"Could not write mosquitto reload signal: {e}")


def parse_mosquitto_conf() -> Dict[str, Any]:
    """
    Parse the mosquitto.conf file into a dictionary.
    Keys that appear multiple times (e.g. log_type) are stored as lists.
    """
    config: Dict[str, Any] = {}
    listeners = []
    current_listener = None

    try:
        with open(MOSQUITTO_CONF_PATH, "r") as f:
            lines = f.readlines()

        for line in lines:
            line = line.strip()

            # Skip comments and empty lines
            if not line or line.startswith("#"):
                continue

            # Check if this is a listener line
            if line.startswith("listener "):
                parts = line.split()

                if current_listener:
                    listeners.append(current_listener)

                current_listener = {
                    "port": int(parts[1]),
                    "bind_address": parts[2] if len(parts) > 2 else "",
                    "per_listener_settings": False,
                    "max_connections": -1,
                    "protocol": None,
                }
            elif current_listener and line.startswith(
                ("per_listener_settings ", "max_connections ", "protocol ")
            ):
                key, value = line.split(" ", 1)
                if key == "per_listener_settings":
                    current_listener[key] = value.lower() == "true"
                elif key == "max_connections":
                    current_listener[key] = int(value)
                elif key == "protocol":
                    current_listener[key] = value.strip()
            else:
                # Regular configuration line
                if " " in line:
                    key, value = line.split(" ", 1)
                    # Keys that can appear multiple times are stored as lists
                    if key == "log_type":
                        existing = config.get("log_type", [])
                        if isinstance(existing, list):
                            existing.append(value)
                        else:
                            existing = [existing, value]
                        config["log_type"] = existing
                    else:
                        config[key] = value

        # Add the last listener if there is one
        if current_listener:
            listeners.append(current_listener)

        # Extract global performance settings into top-level keys for convenience
        max_inflight = config.pop("max_inflight_messages", None)
        max_queued = config.pop("max_queued_messages", None)

        return {
            "config": config,
            "listeners": listeners,
            "max_inflight_messages": int(max_inflight) if max_inflight is not None else None,
            "max_queued_messages": int(max_queued) if max_queued is not None else None,
        }

    except Exception as e:
        logger.error(f"Error parsing mosquitto.conf: {str(e)}")
        return {"config": {}, "listeners": []}


def generate_mosquitto_conf(
    config_data: Dict[str, Any],
    listeners: List[Dict[str, Any]],
    max_inflight_messages: Optional[int] = None,
    max_queued_messages: Optional[int] = None,
) -> str:
    """
    Generate mosquitto.conf content from configuration data
    """
    lines = []

    # Add a header
    lines.append("# Mosquitto Broker Configuration")
    lines.append("# Generated on " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    lines.append("")

    # Add main configuration — skip keys handled separately
    _SKIP_KEYS = {"plugin", "plugin_opt_config_file", "log_type"}
    for key, value in config_data.items():
        if key in _SKIP_KEYS:
            continue
        if isinstance(value, bool):
            value = str(value).lower()
        lines.append(f"{key} {value}")

    # Always write the full required set of log_type lines so connection
    # messages are never silently dropped when the config is saved from the UI.
    lines.append("")
    lines.append("# Required log types — managed by BunkerM; do not reduce")
    for lt in _REQUIRED_LOG_TYPES:
        lines.append(f"log_type {lt}")

    # Add plugins configuration
    if "plugin" in config_data:
        lines.append("")
        lines.append("# Dynamic Security Plugin configuration")
        lines.append(f"plugin {config_data['plugin']}")

        if "plugin_opt_config_file" in config_data:
            lines.append(
                f"plugin_opt_config_file {config_data['plugin_opt_config_file']}"
            )

    # Add listeners
    for listener in listeners:
        lines.append("")
        lines.append(
            f"listener {listener['port']}{' ' + listener['bind_address'] if listener['bind_address'] else ''}"
        )

        if "per_listener_settings" in listener and listener["per_listener_settings"]:
            lines.append(f"per_listener_settings true")
        elif "per_listener_settings" in listener:
            lines.append(f"per_listener_settings false")

        if "max_connections" in listener and listener["max_connections"] != -1:
            lines.append(f"max_connections {listener['max_connections']}")

        if listener.get("protocol"):
            lines.append(f"protocol {listener['protocol']}")

    # Global performance settings (written after all listeners)
    if max_inflight_messages is not None and max_inflight_messages > 0:
        lines.append("")
        lines.append(f"max_inflight_messages {max_inflight_messages}")
    if max_queued_messages is not None and max_queued_messages > 0:
        lines.append(f"max_queued_messages {max_queued_messages}")

    return "\n".join(lines)


def _generate_tls_listener_block(tls: "TLSListenerConfig") -> str:
    """Return the mosquitto config block for a TLS listener."""
    lines = [
        "",
        "# TLS/SSL Listener",
        f"listener {tls.port}",
        "per_listener_settings false",
        "protocol mqtt",
    ]
    if tls.cafile:
        lines.append(f"cafile {tls.cafile}")
    if tls.certfile:
        lines.append(f"certfile {tls.certfile}")
    if tls.keyfile:
        lines.append(f"keyfile {tls.keyfile}")
    lines.append(f"require_certificate {'true' if tls.require_certificate else 'false'}")
    if tls.tls_version:
        lines.append(f"tls_version {tls.tls_version}")
    return "\n".join(lines)


@router.get("/mosquitto-config")
async def get_mosquitto_config(api_key: str = Security(get_api_key)):
    """
    Get the current Mosquitto configuration, including parsed TLS listener if present.
    """
    try:
        config_data = parse_mosquitto_conf()

        if not config_data["config"]:
            return {
                "success": False,
                "message": "Failed to parse Mosquitto configuration",
            }

        # Detect TLS listener (port != 1900, 9001, and has cafile/certfile)
        listeners = config_data.get("listeners", [])
        tls_info: Optional[dict] = None
        for lst in listeners:
            raw = lst.get("_raw", {})
            if raw.get("cafile") or raw.get("certfile"):
                tls_info = {
                    "enabled": True,
                    "port": lst["port"],
                    "cafile": raw.get("cafile"),
                    "certfile": raw.get("certfile"),
                    "keyfile": raw.get("keyfile"),
                    "require_certificate": raw.get("require_certificate", "false") == "true",
                    "tls_version": raw.get("tls_version"),
                }
                break

        # List available cert files
        certs: list = []
        try:
            os.makedirs(CERTS_DIR, exist_ok=True)
            certs = [
                f for f in os.listdir(CERTS_DIR)
                if os.path.isfile(os.path.join(CERTS_DIR, f))
            ]
        except Exception:
            pass

        return {
            "success": True,
            "config": config_data["config"],
            "listeners": config_data["listeners"],
            "max_inflight_messages": config_data.get("max_inflight_messages"),
            "max_queued_messages": config_data.get("max_queued_messages"),
            "tls": tls_info,
            "available_certs": certs,
            "certs_dir": CERTS_DIR,
        }

    except Exception as e:
        logger.error(f"Error getting Mosquitto configuration: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get Mosquitto configuration: {str(e)}",
        )


@router.post("/mosquitto-config")
async def save_mosquitto_config(
    config: MosquittoConfig, api_key: str = Security(get_api_key)
):

    try:
        # Convert listeners to the format expected by generate_mosquitto_conf
        listeners_list = []
        for listener in config.listeners:
            listeners_list.append(
                {
                    "port": listener.port,
                    "bind_address": listener.bind_address or "",
                    "per_listener_settings": listener.per_listener_settings,
                    "max_connections": listener.max_connections,
                    "protocol": listener.protocol,
                }
            )

        # Validate listeners for duplicate ports
        current_config = parse_mosquitto_conf()
        is_valid, error_message = validate_listeners(current_config.get("listeners", []), listeners_list)
        
        if not is_valid:
            logger.error(f"Validation error: {error_message}")
            return {
                "success": False,
                "message": error_message
            }

        # Create backup of current configuration
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(BACKUP_DIR, f"mosquitto.conf.bak.{timestamp}")

        if os.path.exists(MOSQUITTO_CONF_PATH):
            shutil.copy2(MOSQUITTO_CONF_PATH, backup_path)
            logger.info(f"Created backup of Mosquitto configuration at {backup_path}")

        # Generate new configuration content
        new_config_content = generate_mosquitto_conf(
            config.config,
            listeners_list,
            max_inflight_messages=config.max_inflight_messages,
            max_queued_messages=config.max_queued_messages,
        )

        # Append TLS listener block if requested
        if config.tls and config.tls.enabled:
            new_config_content += _generate_tls_listener_block(config.tls)

        # Write new configuration
        with open(MOSQUITTO_CONF_PATH, "w") as f:
            f.write(new_config_content)

        # Set proper permissions
        os.chmod(MOSQUITTO_CONF_PATH, 0o644)

        logger.info(f"Mosquitto configuration saved successfully")
        _signal_mosquitto_reload()
        return {
            "success": True,
            "message": "Mosquitto configuration saved successfully",
            "need_restart": True,
        }

    except Exception as e:
        logger.error(f"Error saving Mosquitto configuration: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save Mosquitto configuration: {str(e)}",
        )
        

@router.post("/reset-mosquitto-config")
async def reset_mosquitto_config(api_key: str = Security(get_api_key)):
    """
    Reset Mosquitto configuration to default
    """
    try:
        # Create backup of current configuration
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(BACKUP_DIR, f"mosquitto.conf.bak.{timestamp}")

        if os.path.exists(MOSQUITTO_CONF_PATH):
            shutil.copy2(MOSQUITTO_CONF_PATH, backup_path)
            logger.info(f"Created backup of Mosquitto configuration at {backup_path}")

        # Write default configuration
        with open(MOSQUITTO_CONF_PATH, "w") as f:
            f.write(DEFAULT_CONFIG)

        # Set proper permissions
        os.chmod(MOSQUITTO_CONF_PATH, 0o644)

        logger.info(f"Mosquitto configuration reset to default")
        _signal_mosquitto_reload()
        return {
            "success": True,
            "message": "Mosquitto configuration reset to default",
            "need_restart": True,
        }

    except Exception as e:
        logger.error(f"Error resetting Mosquitto configuration: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset Mosquitto configuration: {str(e)}",
        )


# ---------------------------------------------------------------------------
# TLS Certificate Management
# ---------------------------------------------------------------------------

_ALLOWED_CERT_EXTENSIONS = {".pem", ".crt", ".cer", ".key"}

@router.get("/tls-certs")
async def list_tls_certs(api_key: str = Security(get_api_key)):
    """List TLS certificate files available in the certs directory."""
    try:
        os.makedirs(CERTS_DIR, exist_ok=True)
        files = [
            f for f in os.listdir(CERTS_DIR)
            if os.path.isfile(os.path.join(CERTS_DIR, f))
            and os.path.splitext(f)[1].lower() in _ALLOWED_CERT_EXTENSIONS
        ]
        return {"success": True, "certs": files, "certs_dir": CERTS_DIR}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tls-certs/upload")
async def upload_tls_cert(
    file: UploadFile = File(...),
    api_key: str = Security(get_api_key),
):
    """Upload a PEM/CRT/KEY file to the certs directory."""
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in _ALLOWED_CERT_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Only {', '.join(_ALLOWED_CERT_EXTENSIONS)} files are accepted",
        )

    # Sanitize filename — only allow alphanumeric, dash, underscore, dot
    import re as _re
    safe_name = _re.sub(r"[^a-zA-Z0-9._-]", "_", os.path.basename(file.filename or "unknown"))
    if not safe_name:
        raise HTTPException(status_code=400, detail="Invalid filename")

    try:
        os.makedirs(CERTS_DIR, exist_ok=True)
        dest = os.path.join(CERTS_DIR, safe_name)
        content = await file.read()
        with open(dest, "wb") as fh:
            fh.write(content)
        os.chmod(dest, 0o640)
        logger.info(f"TLS cert uploaded: {safe_name}")
        return {"success": True, "filename": safe_name, "path": dest}
    except Exception as e:
        logger.error(f"Error uploading cert: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/tls-certs/{filename}")
async def delete_tls_cert(filename: str, api_key: str = Security(get_api_key)):
    """Delete a certificate file from the certs directory."""
    import re as _re
    safe_name = _re.sub(r"[^a-zA-Z0-9._-]", "_", filename)
    dest = os.path.join(CERTS_DIR, safe_name)
    # Prevent path traversal
    if not os.path.abspath(dest).startswith(os.path.abspath(CERTS_DIR)):
        raise HTTPException(status_code=400, detail="Invalid path")
    if not os.path.isfile(dest):
        raise HTTPException(status_code=404, detail="File not found")
    os.remove(dest)
    return {"success": True, "filename": safe_name}


@router.post("/remove-mosquitto-listener")
async def remove_mosquitto_listener(
    listener_data: dict, api_key: str = Security(get_api_key)
):
    """
    Remove a specific listener from the Mosquitto configuration
    """
    try:
        # Extract listener port from request data
        port = listener_data.get("port")
        if not port:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Listener port is required",
            )

        # Read current configuration
        config_data = parse_mosquitto_conf()
        config_dict = config_data["config"]
        listeners_list = config_data["listeners"]
        
        # Find and remove the listener with the specified port
        found = False
        for i, listener in enumerate(listeners_list):
            if listener.get("port") == port:
                listeners_list.pop(i)
                found = True
                break
        
        if not found:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Listener with port {port} not found in configuration",
            )
        
        # Create backup of current configuration
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(BACKUP_DIR, f"mosquitto.conf.bak.{timestamp}")

        if os.path.exists(MOSQUITTO_CONF_PATH):
            shutil.copy2(MOSQUITTO_CONF_PATH, backup_path)
            logger.info(f"Created backup of Mosquitto configuration at {backup_path}")

        # Generate new configuration content
        new_config_content = generate_mosquitto_conf(config_dict, listeners_list)

        # Write new configuration
        with open(MOSQUITTO_CONF_PATH, "w") as f:
            f.write(new_config_content)

        # Set proper permissions
        os.chmod(MOSQUITTO_CONF_PATH, 0o644)

        logger.info(f"Listener on port {port} removed from Mosquitto configuration")
        return {
            "success": True,
            "message": f"Listener on port {port} removed from Mosquitto configuration",
            "need_restart": True,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing listener from Mosquitto configuration: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to remove listener from Mosquitto configuration: {str(e)}",
        )
        
        
def validate_listeners(current_listeners: List[Dict[str, Any]], new_listeners: List[Dict[str, Any]]) -> tuple[bool, str]:
    """
    Validate that there are no duplicate listener ports
    Returns (is_valid, error_message)
    """
    # Get all port numbers from the new listeners
    port_counts = {}
    for listener in new_listeners:
        port = listener.get('port')
        if port in port_counts:
            port_counts[port] += 1
        else:
            port_counts[port] = 1
    
    # Check for duplicates within the new configuration
    for port, count in port_counts.items():
        if count > 1:
            return False, f"Duplicate listener port {port} found in configuration"
    
    return True, ""


# ---------------------------------------------------------------------------
# Broker Logs endpoint
# ---------------------------------------------------------------------------
BROKER_LOG_PATH = os.getenv("BROKER_LOG_PATH", "/var/log/mosquitto/mosquitto.log")
BROKER_LOG_MAX_LINES = 1000

_MOSQUITTO_PID_FILE = "/var/run/mosquitto.pid"

@router.post("/restart-mosquitto")
async def restart_mosquitto(api_key: str = Security(get_api_key)):
    """Signal the standalone mosquitto container to reload config via SIGHUP."""
    try:
        _signal_mosquitto_reload()
        logger.info("Reload signal written — mosquitto will reload config without dropping connections")
        return {"success": True, "message": "Broker reloading config. Connections are not dropped."}
    except Exception as e:
        logger.error(f"Failed to signal Mosquitto reload: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to signal Mosquitto reload: {str(e)}")


@router.get("/broker")
async def get_broker_logs(api_key: str = Security(get_api_key)):
    """Return the last N lines of the Mosquitto broker log as a JSON list."""
    log_path = BROKER_LOG_PATH
    if not os.path.isfile(log_path):
        logger.warning(f"Broker log file not found: {log_path}")
        return {"logs": [], "path": log_path, "error": "Log file not found"}
    try:
        with open(log_path, "r", errors="replace") as fh:
            lines = fh.readlines()
        tail = [line.rstrip("\n") for line in lines[-BROKER_LOG_MAX_LINES:]]
        return {"logs": tail, "path": log_path}
    except Exception as exc:
        logger.error(f"Failed to read broker log: {exc}")
        raise HTTPException(status_code=500, detail=f"Failed to read broker log: {str(exc)}")