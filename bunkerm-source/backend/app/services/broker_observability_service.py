"""Lectura broker-owned de artefactos observacionales compartidos."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict

from core.config import settings

_BROKER_LOG_MAX_LINES = 1000


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


def read_broker_logs(limit: int | None = None) -> Dict[str, Any]:
    source = get_broker_log_source_status()
    log_path = source["path"]
    if not source["enabled"]:
        return {"logs": [], "path": log_path, "error": "Log reading disabled", "source": source}
    if not source["available"]:
        return {"logs": [], "path": log_path, "error": "Log file not found", "source": source}

    max_lines = max(1, min(limit or _BROKER_LOG_MAX_LINES, 5000))
    with open(log_path, "r", errors="replace") as fh:
        lines = fh.readlines()
    tail = [line.rstrip("\n") for line in lines[-max_lines:]]
    return {"logs": tail, "path": log_path, "source": source}


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