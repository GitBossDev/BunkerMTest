from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from functools import lru_cache
from typing import Any, Dict

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from core.config import settings
from core.sync_database import create_sync_engine_for_url, session_scope, utc_now
from models.orm import AlertDeliveryChannel, AlertDeliveryEvent


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


@lru_cache(maxsize=1)
def _get_session_factory() -> sessionmaker[Session]:
    engine = create_sync_engine_for_url(settings.resolved_control_plane_database_url)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _env_email_delivery_enabled() -> bool:
    if not _as_bool(os.getenv("ALERT_NOTIFY_ENABLED"), default=False):
        return False
    if not _as_bool(os.getenv("ALERT_NOTIFY_EMAIL_ENABLED"), default=True):
        return False
    return bool(_csv(os.getenv("ALERT_NOTIFY_EMAIL_TO")))


def _resolve_channel_routing(session: Session) -> tuple[str | None, int]:
    db_channel_count = int(
        session.scalar(
            select(func.count(AlertDeliveryChannel.id)).where(AlertDeliveryChannel.enabled.is_(True))
        )
        or 0
    )
    if db_channel_count > 0:
        return ("db-channels", db_channel_count)
    if _env_email_delivery_enabled():
        return ("env-email-inline", 1)
    return (None, 0)


def build_alert_delivery_payload(
    alert: Dict[str, Any],
    *,
    transition: str,
    channel_policy_id: str | None,
    channel_count: int,
    event_id: str,
) -> Dict[str, Any]:
    alert_id = str(alert.get("id") or "")
    dedupe_key = f"{alert_id}:{transition}:{channel_policy_id or 'default'}"
    timestamp = str(alert.get("timestamp") or datetime.utcnow().isoformat() + "Z")
    return {
        "eventId": event_id,
        "alertId": alert_id,
        "dedupeKey": dedupe_key,
        "transition": transition,
        "status": str(alert.get("status") or "active"),
        "type": str(alert.get("type") or "unknown"),
        "severity": str(alert.get("severity") or "high"),
        "title": str(alert.get("title") or "Broker Alert"),
        "description": str(alert.get("description") or ""),
        "impact": str(alert.get("impact") or ""),
        "source": {
            "service": "bhm-api",
            "component": "monitor.alert-engine",
            "broker": "bhm-broker",
        },
        "timestamps": {
            "observedAt": timestamp,
            "raisedAt": timestamp if transition == "raised" else None,
            "resolvedAt": None,
        },
        "metrics": {
            "clientCapacityPct": alert.get("clientCapacityPct"),
            "reconnectCount": alert.get("reconnectCount"),
            "authFailCount": alert.get("authFailCount"),
        },
        "links": {
            "monitor": "/api/v1/monitor/alerts/broker",
            "alert": f"/api/v1/monitor/alerts/broker/{alert_id}",
        },
        "routing": {
            "channelPolicyId": channel_policy_id,
            "channelCount": channel_count,
        },
    }


def enqueue_alert_delivery_event(
    alert: Dict[str, Any],
    *,
    transition: str = "raised",
    session_factory: sessionmaker[Session] | None = None,
) -> str | None:
    if not _as_bool(os.getenv("ALERT_NOTIFY_ENABLED"), default=False):
        return None

    session_factory = session_factory or _get_session_factory()
    with session_scope(session_factory) as session:
        channel_policy_id, channel_count = _resolve_channel_routing(session)
        alert_id = str(alert.get("id") or "")
        dedupe_key = f"{alert_id}:{transition}:{channel_policy_id or 'default'}"

        existing = session.scalar(
            select(AlertDeliveryEvent).where(AlertDeliveryEvent.dedupe_key == dedupe_key)
        )
        if existing is not None:
            return existing.event_id

        event_id = str(uuid.uuid4())
        payload = build_alert_delivery_payload(
            alert,
            transition=transition,
            channel_policy_id=channel_policy_id,
            channel_count=channel_count,
            event_id=event_id,
        )
        now = utc_now().replace(tzinfo=None)
        session.add(
            AlertDeliveryEvent(
                event_id=event_id,
                alert_id=alert_id,
                dedupe_key=dedupe_key,
                transition=transition,
                status=str(alert.get("status") or "active"),
                delivery_state="pending",
                channel_policy_id=channel_policy_id,
                channel_count=channel_count,
                payload_json=json.dumps(payload, ensure_ascii=True, sort_keys=True),
                next_attempt_at=now,
                created_at=now,
                updated_at=now,
            )
        )
        return event_id