from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Security, status
from fastapi.responses import Response

from core.auth import get_api_key
from models.schemas import NotificationChannelUpsert
from services import notifications_service

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


def _normalize_export_format(export_format: str) -> str:
    normalized = export_format.strip().lower()
    if normalized not in {"csv", "json"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid format. Valid: ['csv', 'json']",
        )
    return normalized


def _csv_response(filename_prefix: str, rows: list[dict], fieldnames: list[str]) -> Response:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    headers = {"Content-Disposition": f'attachment; filename="{filename_prefix}-{stamp}.csv"'}
    csv_lines = [",".join(fieldnames)]
    for row in rows:
        serialized = []
        for field in fieldnames:
            value = row.get(field, "")
            text = "" if value is None else str(value)
            text = text.replace('"', '""')
            if any(ch in text for ch in [",", '"', "\n"]):
                text = f'"{text}"'
            serialized.append(text)
        csv_lines.append(",".join(serialized))
    return Response(content="\n".join(csv_lines), media_type="text/csv; charset=utf-8", headers=headers)


def _json_response(filename_prefix: str, payload: dict) -> Response:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    headers = {"Content-Disposition": f'attachment; filename="{filename_prefix}-{stamp}.json"'}
    return Response(content=json.dumps(payload, ensure_ascii=True, indent=2), media_type="application/json", headers=headers)


def _validate_channel_payload(payload: NotificationChannelUpsert) -> Dict[str, Any]:
    config = dict(payload.config or {})
    if payload.channelType == "email":
        recipients = config.get("recipients")
        if not isinstance(recipients, list) or not any(str(item).strip() for item in recipients):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email channels require at least one recipient",
            )
    if payload.channelType == "webhook":
        url = str(config.get("url") or "").strip()
        if not url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Webhook channels require a url",
            )
    return payload.model_dump()


@router.get("/channels")
async def get_notification_channels(include_disabled: bool = True, api_key: str = Security(get_api_key)):
    return notifications_service.list_notification_channels(include_disabled=include_disabled)


@router.post("/channels")
async def post_notification_channel(payload: NotificationChannelUpsert, api_key: str = Security(get_api_key)):
    return notifications_service.upsert_notification_channel(_validate_channel_payload(payload))


@router.get("/events")
async def get_notification_events(
    limit: int = 50,
    delivery_state: Optional[str] = None,
    alert_id: Optional[str] = None,
    api_key: str = Security(get_api_key),
):
    return notifications_service.list_notification_events(
        limit=limit,
        delivery_state=delivery_state,
        alert_id=alert_id,
    )


@router.get("/attempts")
async def get_notification_attempts(
    limit: int = 100,
    event_id: Optional[str] = None,
    channel_id: Optional[int] = None,
    attempt_state: Optional[str] = None,
    api_key: str = Security(get_api_key),
):
    return notifications_service.list_notification_attempts(
        limit=limit,
        event_id=event_id,
        channel_id=channel_id,
        attempt_state=attempt_state,
    )


@router.get("/export/events")
async def export_notification_events(
    limit: int = 200,
    delivery_state: Optional[str] = None,
    alert_id: Optional[str] = None,
    export_format: str = "csv",
    api_key: str = Security(get_api_key),
):
    payload = notifications_service.list_notification_events(
        limit=limit,
        delivery_state=delivery_state,
        alert_id=alert_id,
    )
    normalized = _normalize_export_format(export_format)
    if normalized == "json":
        return _json_response("notification-events", payload)
    return _csv_response(
        "notification-events",
        payload["events"],
        [
            "eventId",
            "alertId",
            "dedupeKey",
            "transition",
            "status",
            "deliveryState",
            "channelPolicyId",
            "channelCount",
            "type",
            "severity",
            "title",
            "description",
            "impact",
            "createdAt",
            "updatedAt",
            "nextAttemptAt",
        ],
    )


@router.get("/export/attempts")
async def export_notification_attempts(
    limit: int = 200,
    event_id: Optional[str] = None,
    channel_id: Optional[int] = None,
    attempt_state: Optional[str] = None,
    export_format: str = "csv",
    api_key: str = Security(get_api_key),
):
    payload = notifications_service.list_notification_attempts(
        limit=limit,
        event_id=event_id,
        channel_id=channel_id,
        attempt_state=attempt_state,
    )
    normalized = _normalize_export_format(export_format)
    if normalized == "json":
        return _json_response("notification-attempts", payload)
    return _csv_response(
        "notification-attempts",
        payload["attempts"],
        [
            "id",
            "eventId",
            "alertId",
            "channelId",
            "channelKey",
            "channelType",
            "displayName",
            "attemptNumber",
            "attemptState",
            "providerStatusCode",
            "providerMessageId",
            "errorClass",
            "errorDetail",
            "scheduledAt",
            "startedAt",
            "finishedAt",
            "createdAt",
        ],
    )