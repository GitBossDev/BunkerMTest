"""Lectura broker-owned de artefactos observacionales y estado observado del broker."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict

from config.mosquitto_config import parse_mosquitto_conf
from core.config import settings
from services import dynsec_service

_BROKER_LOG_MAX_LINES = 1000
_ALLOWED_CERT_EXTENSIONS = {".pem", ".crt", ".cer", ".key"}


def _iso_mtime(path: str) -> str | None:
    if not os.path.exists(path):
        return None
    return datetime.fromtimestamp(os.path.getmtime(path), timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def get_broker_log_source_status() -> Dict[str, Any]:
    path = settings.broker_log_path
    enabled = settings.broker_log_read_enabled
    exists = os.path.isfile(path)
    return {
        "enabled": enabled,
        "path": path,
        "available": enabled and exists,
        "mode": "shared-log-file",
        "lastError": None if enabled and exists else (
            "disabled_by_config" if not enabled else "log_file_not_found"
        ),
    }


def read_broker_logs(limit: int | None = None, offset: int | None = None) -> Dict[str, Any]:
    source = get_broker_log_source_status()
    log_path = source["path"]
    if not source["enabled"]:
        return {"logs": [], "path": log_path, "error": "Log reading disabled", "source": source, "offset": offset, "next_offset": offset or 0, "has_more": False, "rewound": False}
    if not source["available"]:
        return {"logs": [], "path": log_path, "error": "Log file not found", "source": source, "offset": offset, "next_offset": offset or 0, "has_more": False, "rewound": False}

    max_lines = max(1, min(limit or _BROKER_LOG_MAX_LINES, 5000))
    if offset is None:
        with open(log_path, "r", errors="replace") as fh:
            lines = fh.readlines()
            next_offset = fh.tell()
        tail = [line.rstrip("\n") for line in lines[-max_lines:]]
        return {
            "logs": tail,
            "path": log_path,
            "source": source,
            "offset": None,
            "next_offset": next_offset,
            "has_more": False,
            "rewound": False,
        }

    requested_offset = max(0, int(offset))
    file_size = os.path.getsize(log_path)
    start_offset = requested_offset if requested_offset <= file_size else 0
    rewound = start_offset != requested_offset

    with open(log_path, "r", errors="replace") as fh:
        fh.seek(start_offset)
        lines: list[str] = []
        while len(lines) < max_lines:
            line = fh.readline()
            if not line:
                break
            lines.append(line.rstrip("\n"))
        next_offset = fh.tell()

    has_more = next_offset < os.path.getsize(log_path)
    return {
        "logs": lines,
        "path": log_path,
        "source": source,
        "offset": start_offset,
        "next_offset": next_offset,
        "has_more": has_more,
        "rewound": rewound,
    }


def get_broker_resource_source_status() -> Dict[str, Any]:
    path = settings.broker_resource_stats_path
    enabled = settings.broker_resource_stats_file_enabled
    exists = os.path.isfile(path)
    return {
        "enabled": enabled,
        "path": path,
        "available": enabled and exists,
        "mode": "shared-file",
        "lastError": None if enabled and exists else (
            "disabled_by_config" if not enabled else "stats_file_not_found"
        ),
        "lastReadAt": None,
    }


def read_broker_resource_stats_payload() -> Dict[str, Any]:
    source = get_broker_resource_source_status()
    stats_path = source["path"]
    if not source["enabled"] or not source["available"]:
        return {"stats": {}, "source": source}

    try:
        with open(stats_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            source["lastError"] = "invalid_stats_payload"
            return {"stats": {}, "source": source}
        source["lastReadAt"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        return {"stats": data, "source": source}
    except Exception as exc:
        source["lastError"] = str(exc)
        source["available"] = False
        return {"stats": {}, "source": source}


def get_broker_dynsec_source_status() -> Dict[str, Any]:
    path = settings.dynsec_path
    exists = os.path.isfile(path)
    return {
        "enabled": True,
        "path": path,
        "available": exists,
        "mode": "shared-file",
        "lastError": None if exists else "dynsec_file_not_found",
        "modifiedAt": _iso_mtime(path),
    }


def read_broker_dynsec_payload() -> Dict[str, Any]:
    source = get_broker_dynsec_source_status()
    if not source["available"]:
        return {"config": {}, "source": source}

    try:
        return {"config": dynsec_service.read_dynsec(), "source": source}
    except Exception as exc:
        source["available"] = False
        source["lastError"] = str(exc)
        return {"config": {}, "source": source}


def get_broker_mosquitto_config_source_status() -> Dict[str, Any]:
    path = settings.mosquitto_conf_path
    exists = os.path.isfile(path)
    return {
        "enabled": True,
        "path": path,
        "available": exists,
        "mode": "shared-file",
        "lastError": None if exists else "mosquitto_conf_not_found",
        "modifiedAt": _iso_mtime(path),
    }


def read_broker_mosquitto_config_payload() -> Dict[str, Any]:
    source = get_broker_mosquitto_config_source_status()
    if not source["available"]:
        return {
            "config": {},
            "listeners": [],
            "max_inflight_messages": None,
            "max_queued_messages": None,
            "tls": None,
            "available_certs": [],
            "certs_dir": settings.mosquitto_certs_dir,
            "content": "",
            "source": source,
        }

    try:
        with open(settings.mosquitto_conf_path, "r", encoding="utf-8") as handle:
            content = handle.read()
        parsed = parse_mosquitto_conf()
        listeners = parsed.get("listeners", [])
        tls_info = None
        for listener in listeners:
            raw = listener.get("_raw", {}) if isinstance(listener, dict) else {}
            if raw.get("cafile") or raw.get("certfile"):
                tls_info = {
                    "enabled": True,
                    "port": listener["port"],
                    "cafile": raw.get("cafile"),
                    "certfile": raw.get("certfile"),
                    "keyfile": raw.get("keyfile"),
                    "require_certificate": raw.get("require_certificate", "false") == "true",
                    "tls_version": raw.get("tls_version"),
                }
                break

        certs: list[str] = []
        cert_dir = settings.mosquitto_certs_dir
        if os.path.isdir(cert_dir):
            certs = [
                name for name in sorted(os.listdir(cert_dir))
                if os.path.isfile(os.path.join(cert_dir, name))
            ]

        return {
            "config": parsed.get("config", {}),
            "listeners": listeners,
            "max_inflight_messages": parsed.get("max_inflight_messages"),
            "max_queued_messages": parsed.get("max_queued_messages"),
            "tls": tls_info,
            "available_certs": certs,
            "certs_dir": cert_dir,
            "content": content,
            "source": source,
        }
    except Exception as exc:
        source["available"] = False
        source["lastError"] = str(exc)
        return {
            "config": {},
            "listeners": [],
            "max_inflight_messages": None,
            "max_queued_messages": None,
            "tls": None,
            "available_certs": [],
            "certs_dir": settings.mosquitto_certs_dir,
            "content": "",
            "source": source,
        }


def get_broker_passwd_source_status() -> Dict[str, Any]:
    path = settings.mosquitto_passwd_path
    exists = os.path.isfile(path)
    return {
        "enabled": True,
        "path": path,
        "available": exists,
        "mode": "shared-file",
        "lastError": None if exists else "mosquitto_passwd_not_found",
        "modifiedAt": _iso_mtime(path),
    }


def read_broker_passwd_payload() -> Dict[str, Any]:
    source = get_broker_passwd_source_status()
    if not source["available"]:
        return {
            "passwd": {
                "exists": False,
                "content": "",
                "users": [],
                "userCount": 0,
                "sizeBytes": 0,
                "sha256": None,
            },
            "source": source,
        }

    try:
        with open(settings.mosquitto_passwd_path, "r", encoding="utf-8") as handle:
            content = handle.read().replace("\r\n", "\n")
        if content and not content.endswith("\n"):
            content += "\n"
        users = [line.split(":", 1)[0] for line in content.splitlines() if line.strip()]
        raw = content.encode("utf-8")
        return {
            "passwd": {
                "exists": True,
                "content": content,
                "users": users,
                "userCount": len(users),
                "sizeBytes": len(raw),
                "sha256": _sha256_bytes(raw),
            },
            "source": source,
        }
    except Exception as exc:
        source["available"] = False
        source["lastError"] = str(exc)
        return {
            "passwd": {
                "exists": False,
                "content": "",
                "users": [],
                "userCount": 0,
                "sizeBytes": 0,
                "sha256": None,
            },
            "source": source,
        }


def get_broker_tls_certs_source_status() -> Dict[str, Any]:
    path = settings.mosquitto_certs_dir
    exists = os.path.isdir(path)
    return {
        "enabled": True,
        "path": path,
        "available": exists,
        "mode": "shared-directory",
        "lastError": None if exists else "tls_certs_dir_not_found",
        "modifiedAt": _iso_mtime(path),
    }


def read_broker_tls_certs_payload() -> Dict[str, Any]:
    source = get_broker_tls_certs_source_status()
    if not source["available"]:
        return {"certs": [], "source": source}

    entries: list[Dict[str, Any]] = []
    try:
        for filename in sorted(os.listdir(settings.mosquitto_certs_dir)):
            path = os.path.join(settings.mosquitto_certs_dir, filename)
            extension = os.path.splitext(filename)[1].lower()
            if not os.path.isfile(path) or extension not in _ALLOWED_CERT_EXTENSIONS:
                continue
            with open(path, "rb") as handle:
                content = handle.read()
            entries.append(
                {
                    "filename": filename,
                    "extension": extension,
                    "size": len(content),
                    "sha256": _sha256_bytes(content),
                    "deleted": False,
                }
            )
        return {"certs": entries, "source": source}
    except Exception as exc:
        source["available"] = False
        source["lastError"] = str(exc)
        return {"certs": [], "source": source}