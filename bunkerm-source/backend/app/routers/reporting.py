from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Security, status
from fastapi.responses import Response

from core.auth import get_api_key
from reporting.sqlite_reporting import reporting_storage

router = APIRouter(prefix="/api/v1/reports", tags=["reporting"])


def _csv_response(filename_prefix: str, rows: list[dict], fieldnames: list[str]) -> Response:
    content = reporting_storage.to_csv_bytes(rows, fieldnames)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    headers = {"Content-Disposition": f'attachment; filename="{filename_prefix}-{stamp}.csv"'}
    return Response(content=content, media_type="text/csv; charset=utf-8", headers=headers)


def _json_response(filename_prefix: str, payload: dict) -> Response:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    headers = {"Content-Disposition": f'attachment; filename="{filename_prefix}-{stamp}.json"'}
    return Response(content=json.dumps(payload, ensure_ascii=True, indent=2), media_type="application/json", headers=headers)


def _normalize_csv_format(export_format: str) -> str:
    normalized = export_format.strip().lower()
    if normalized not in {"csv", "json"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid format. Valid: ['csv', 'json']",
        )
    return normalized


@router.get("/broker/daily")
async def get_broker_daily_report(days: int = 30, api_key: str = Security(get_api_key)):
    return reporting_storage.get_broker_daily_report(days=days)


@router.get("/broker/weekly")
async def get_broker_weekly_report(weeks: int = 8, api_key: str = Security(get_api_key)):
    return reporting_storage.get_broker_weekly_report(weeks=weeks)


@router.get("/clients/{username}/timeline")
async def get_client_timeline(username: str, days: int = 30, limit: int = 200, event_types: str | None = None,
                              api_key: str = Security(get_api_key)):
    types = [value for value in (event_types or "").split(",") if value.strip()]
    return reporting_storage.get_client_timeline(username=username, days=days, limit=limit, event_types=types)


@router.get("/incidents/clients")
async def get_client_incidents(days: int = 30, limit: int = 200, username: str | None = None,
                               incident_types: str | None = None, reconnect_window_minutes: int = 30,
                               reconnect_threshold: int = 3, api_key: str = Security(get_api_key)):
    types = [value for value in (incident_types or "").split(",") if value.strip()]
    return reporting_storage.get_client_incidents(
        days=days,
        limit=limit,
        username=username,
        incident_types=types,
        reconnect_window_minutes=reconnect_window_minutes,
        reconnect_threshold=reconnect_threshold,
    )


@router.get("/export/broker")
async def export_broker_report(scope: str = "daily", days: int = 30, weeks: int = 8, export_format: str = "csv",
                               api_key: str = Security(get_api_key)):
    normalized = _normalize_csv_format(export_format)
    if scope == "daily":
        payload = reporting_storage.get_broker_daily_report(days=days)
        rows = payload["items"]
        filename_prefix = "broker-daily-report"
        fields = [
            "day", "peak_connected_clients", "peak_active_sessions", "peak_max_concurrent",
            "total_messages_received", "total_messages_sent", "bytes_received_rate_sum",
            "bytes_sent_rate_sum", "latency_samples", "avg_latency_ms",
        ]
    elif scope == "weekly":
        payload = reporting_storage.get_broker_weekly_report(weeks=weeks)
        rows = payload["items"]
        filename_prefix = "broker-weekly-report"
        fields = [
            "week_start", "week_end", "days_covered", "peak_connected_clients",
            "peak_active_sessions", "peak_max_concurrent", "total_messages_received",
            "total_messages_sent", "bytes_received_rate_sum", "bytes_sent_rate_sum", "avg_latency_ms",
        ]
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid scope. Valid: ['daily', 'weekly']")

    if normalized == "json":
        return _json_response(filename_prefix, payload)
    return _csv_response(filename_prefix, rows, fields)


@router.get("/export/client-activity/{username}")
async def export_client_activity(username: str, days: int = 30, limit: int = 500, export_format: str = "csv",
                                 event_types: str | None = None, api_key: str = Security(get_api_key)):
    normalized = _normalize_csv_format(export_format)
    payload = reporting_storage.get_client_timeline(
        username=username,
        days=days,
        limit=limit,
        event_types=[value for value in (event_types or "").split(",") if value.strip()],
    )
    if normalized == "json":
        return _json_response(f"client-activity-{username}", payload)
    rows = payload["timeline"]
    return _csv_response(
        f"client-activity-{username}",
        rows,
        [
            "event_ts", "event_type", "client_id", "ip_address", "port", "protocol_level",
            "clean_session", "keep_alive", "disconnect_kind", "reason_code", "topic",
            "qos", "payload_bytes", "retained",
        ],
    )


@router.get("/retention/status")
async def get_retention_status(api_key: str = Security(get_api_key)):
    return reporting_storage.get_retention_status()


@router.post("/retention/purge")
async def purge_retention_data(api_key: str = Security(get_api_key)):
    return reporting_storage.execute_retention_purge()