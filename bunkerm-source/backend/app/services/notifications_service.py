from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any, Dict

from sqlalchemy import Select, desc, select
from sqlalchemy.orm import Session, sessionmaker

from core.config import settings
from core.sync_database import create_sync_engine_for_url, iso_utc, session_scope, utc_now
from models.orm import AlertDeliveryAttempt, AlertDeliveryChannel, AlertDeliveryEvent

_RETRY_POLICY_SUMMARY = {
    "mode": "backoff-fixed",
    "maxAttempts": 5,
    "delaysSeconds": [30, 120, 600, 1800, 7200],
}


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


def _load_json(value: str | None) -> Dict[str, Any]:
    if not value:
        return {}
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _serialize_channel_config(channel_type: str, config: Dict[str, Any]) -> Dict[str, Any]:
    if channel_type == "email":
        recipients = config.get("recipients") if isinstance(config.get("recipients"), list) else []
        recipients = [str(item).strip() for item in recipients if str(item).strip()]
        return {
            "from": str(config.get("from") or "").strip() or None,
            "recipients": recipients,
            "recipientCount": len(recipients),
            "transport": {
                "starttls": _as_bool(str(config.get("starttls")) if config.get("starttls") is not None else None, default=True),
                "ssl": _as_bool(str(config.get("ssl")) if config.get("ssl") is not None else None, default=False),
            },
        }
    if channel_type == "webhook":
        headers = config.get("headers") if isinstance(config.get("headers"), dict) else {}
        return {
            "url": str(config.get("url") or "").strip() or None,
            "timeoutSeconds": int(config.get("timeout_seconds") or 15),
            "headerNames": sorted(str(key) for key in headers.keys()),
            "hasHeaders": bool(headers),
        }
    return {}


def _serialize_channel(channel: AlertDeliveryChannel) -> Dict[str, Any]:
    config = _load_json(channel.config_json)
    return {
        "id": channel.id,
        "channelKey": channel.channel_key,
        "channelType": channel.channel_type,
        "displayName": channel.display_name,
        "enabled": bool(channel.enabled),
        "managedBy": config.get("managedBy") or "database",
        "hasSecret": bool(channel.secret_ref),
        "secretRef": None,
        "config": _serialize_channel_config(channel.channel_type, config),
        "lastDeliveryStatus": channel.last_delivery_status,
        "lastAttemptAt": iso_utc(channel.last_attempt_at),
        "retryPolicySummary": dict(_RETRY_POLICY_SUMMARY),
        "createdAt": iso_utc(channel.created_at),
        "updatedAt": iso_utc(channel.updated_at),
    }


def _build_env_email_channel() -> Dict[str, Any] | None:
    if not _as_bool(os.getenv("ALERT_NOTIFY_ENABLED"), default=False):
        return None
    if not _as_bool(os.getenv("ALERT_NOTIFY_EMAIL_ENABLED"), default=True):
        return None
    recipients = _csv(os.getenv("ALERT_NOTIFY_EMAIL_TO"))
    if not recipients:
        return None
    return {
        "id": None,
        "channelKey": "env-email-inline",
        "channelType": "email",
        "displayName": "Environment SMTP",
        "enabled": True,
        "managedBy": "environment",
        "hasSecret": bool(os.getenv("ALERT_NOTIFY_SMTP_PASSWORD")),
        "secretRef": None,
        "config": {
            "from": os.getenv("ALERT_NOTIFY_EMAIL_FROM") or os.getenv("ALERT_NOTIFY_SMTP_USERNAME") or None,
            "recipients": recipients,
            "recipientCount": len(recipients),
            "transport": {
                "starttls": _as_bool(os.getenv("ALERT_NOTIFY_SMTP_STARTTLS"), default=True),
                "ssl": _as_bool(os.getenv("ALERT_NOTIFY_SMTP_SSL"), default=False),
            },
        },
        "lastDeliveryStatus": None,
        "lastAttemptAt": None,
        "retryPolicySummary": dict(_RETRY_POLICY_SUMMARY),
        "createdAt": None,
        "updatedAt": None,
    }


def list_notification_channels(*, include_disabled: bool = True, session_factory: sessionmaker[Session] | None = None) -> Dict[str, Any]:
    session_factory = session_factory or _get_session_factory()
    with session_factory() as session:
        stmt = select(AlertDeliveryChannel).order_by(AlertDeliveryChannel.display_name.asc(), AlertDeliveryChannel.id.asc())
        if not include_disabled:
            stmt = stmt.where(AlertDeliveryChannel.enabled.is_(True))
        channels = [_serialize_channel(channel) for channel in session.scalars(stmt).all()]

    if not channels:
        env_channel = _build_env_email_channel()
        if env_channel is not None:
            channels.append(env_channel)

    return {"channels": channels, "total": len(channels)}


def upsert_notification_channel(
    payload: Dict[str, Any],
    *,
    session_factory: sessionmaker[Session] | None = None,
) -> Dict[str, Any]:
    session_factory = session_factory or _get_session_factory()
    now = utc_now().replace(tzinfo=None)
    with session_scope(session_factory) as session:
        channel: AlertDeliveryChannel | None = None
        channel_id = payload.get("id")
        channel_key = str(payload.get("channelKey") or "").strip()
        if channel_id is not None:
            channel = session.get(AlertDeliveryChannel, int(channel_id))
        if channel is None and channel_key:
            channel = session.scalar(select(AlertDeliveryChannel).where(AlertDeliveryChannel.channel_key == channel_key))

        if channel is None:
            channel = AlertDeliveryChannel(
                channel_key=channel_key,
                channel_type=str(payload.get("channelType") or "email"),
                display_name=str(payload.get("displayName") or channel_key),
                enabled=bool(payload.get("enabled", True)),
                config_json=json.dumps(payload.get("config") or {}, ensure_ascii=True, sort_keys=True),
                secret_ref=str(payload.get("secretRef") or "").strip() or None,
                last_delivery_status=None,
                last_attempt_at=None,
                created_at=now,
                updated_at=now,
            )
            session.add(channel)
            session.flush()
        else:
            channel.channel_key = channel_key
            channel.channel_type = str(payload.get("channelType") or channel.channel_type)
            channel.display_name = str(payload.get("displayName") or channel.display_name)
            channel.enabled = bool(payload.get("enabled", channel.enabled))
            channel.config_json = json.dumps(payload.get("config") or {}, ensure_ascii=True, sort_keys=True)
            channel.secret_ref = str(payload.get("secretRef") or "").strip() or None
            channel.updated_at = now
            session.flush()

        session.refresh(channel)
        return _serialize_channel(channel)


def _base_event_query(delivery_state: str | None, alert_id: str | None) -> Select[tuple[AlertDeliveryEvent]]:
    stmt = select(AlertDeliveryEvent)
    if delivery_state:
        stmt = stmt.where(AlertDeliveryEvent.delivery_state == delivery_state)
    if alert_id:
        stmt = stmt.where(AlertDeliveryEvent.alert_id == alert_id)
    return stmt.order_by(desc(AlertDeliveryEvent.created_at), desc(AlertDeliveryEvent.event_id))


def list_notification_events(
    *,
    limit: int = 50,
    delivery_state: str | None = None,
    alert_id: str | None = None,
    session_factory: sessionmaker[Session] | None = None,
) -> Dict[str, Any]:
    session_factory = session_factory or _get_session_factory()
    with session_factory() as session:
        rows = session.scalars(_base_event_query(delivery_state, alert_id).limit(max(1, min(limit, 200)))).all()

    items = []
    for event in rows:
        payload = _load_json(event.payload_json)
        items.append(
            {
                "eventId": event.event_id,
                "alertId": event.alert_id,
                "dedupeKey": event.dedupe_key,
                "transition": event.transition,
                "status": event.status,
                "deliveryState": event.delivery_state,
                "channelPolicyId": event.channel_policy_id,
                "channelCount": event.channel_count,
                "type": payload.get("type"),
                "severity": payload.get("severity"),
                "title": payload.get("title"),
                "description": payload.get("description"),
                "impact": payload.get("impact"),
                "source": payload.get("source") or {},
                "timestamps": payload.get("timestamps") or {},
                "links": payload.get("links") or {},
                "routing": payload.get("routing") or {},
                "createdAt": iso_utc(event.created_at),
                "updatedAt": iso_utc(event.updated_at),
                "nextAttemptAt": iso_utc(event.next_attempt_at),
            }
        )
    return {"events": items, "total": len(items)}


def list_notification_attempts(
    *,
    limit: int = 100,
    event_id: str | None = None,
    channel_id: int | None = None,
    attempt_state: str | None = None,
    session_factory: sessionmaker[Session] | None = None,
) -> Dict[str, Any]:
    session_factory = session_factory or _get_session_factory()
    with session_factory() as session:
        stmt = (
            select(AlertDeliveryAttempt, AlertDeliveryChannel, AlertDeliveryEvent)
            .join(AlertDeliveryChannel, AlertDeliveryChannel.id == AlertDeliveryAttempt.channel_id)
            .join(AlertDeliveryEvent, AlertDeliveryEvent.event_id == AlertDeliveryAttempt.event_id)
        )
        if event_id:
            stmt = stmt.where(AlertDeliveryAttempt.event_id == event_id)
        if channel_id is not None:
            stmt = stmt.where(AlertDeliveryAttempt.channel_id == channel_id)
        if attempt_state:
            stmt = stmt.where(AlertDeliveryAttempt.attempt_state == attempt_state)
        stmt = stmt.order_by(desc(AlertDeliveryAttempt.created_at), desc(AlertDeliveryAttempt.id)).limit(max(1, min(limit, 200)))
        rows = session.execute(stmt).all()

    items = []
    for attempt, channel, event in rows:
        items.append(
            {
                "id": attempt.id,
                "eventId": attempt.event_id,
                "alertId": event.alert_id,
                "channelId": attempt.channel_id,
                "channelKey": channel.channel_key,
                "channelType": channel.channel_type,
                "displayName": channel.display_name,
                "attemptNumber": attempt.attempt_number,
                "attemptState": attempt.attempt_state,
                "providerStatusCode": attempt.provider_status_code,
                "providerMessageId": attempt.provider_message_id,
                "errorClass": attempt.error_class,
                "errorDetail": attempt.error_detail,
                "scheduledAt": iso_utc(attempt.scheduled_at),
                "startedAt": iso_utc(attempt.started_at),
                "finishedAt": iso_utc(attempt.finished_at),
                "createdAt": iso_utc(attempt.created_at),
            }
        )
    return {"attempts": items, "total": len(items)}