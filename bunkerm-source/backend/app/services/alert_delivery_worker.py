from __future__ import annotations

import json
import logging
import os
import smtplib
import socket
import uuid
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from functools import lru_cache
from typing import Any, Dict

import httpx
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, sessionmaker

from core.config import settings
from core.sync_database import create_sync_engine_for_url, session_scope, utc_now
from models.orm import AlertDeliveryAttempt, AlertDeliveryChannel, AlertDeliveryEvent

logger = logging.getLogger(__name__)

_RETRY_DELAYS_SECONDS = [30, 120, 600, 1800, 7200]
_MAX_ATTEMPTS = len(_RETRY_DELAYS_SECONDS)
_PROCESSABLE_EVENT_STATES = {"pending", "partially_delivered"}


class AlertDeliveryTransientError(RuntimeError):
    pass


class AlertDeliveryPermanentError(RuntimeError):
    pass


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


def _now_naive(now: datetime | None = None) -> datetime:
    current = now or utc_now()
    if current.tzinfo is not None:
        return current.astimezone(timezone.utc).replace(tzinfo=None)
    return current


def _load_json(value: str | None) -> Dict[str, Any]:
    if not value:
        return {}
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _build_email_subject(payload: Dict[str, Any]) -> str:
    severity = str(payload.get("severity") or "high").upper()
    title = str(payload.get("title") or "Broker Alert")
    return f"[BHM][{severity}] {title}"


def _build_email_body(payload: Dict[str, Any]) -> str:
    timestamps = payload.get("timestamps") or {}
    return (
        "BHM detected a technical alert transition\n\n"
        f"Alert ID: {payload.get('alertId', '')}\n"
        f"Event ID: {payload.get('eventId', '')}\n"
        f"Transition: {payload.get('transition', '')}\n"
        f"Status: {payload.get('status', '')}\n"
        f"Type: {payload.get('type', '')}\n"
        f"Severity: {payload.get('severity', '')}\n"
        f"Title: {payload.get('title', '')}\n"
        f"Description: {payload.get('description', '')}\n"
        f"Impact: {payload.get('impact', '')}\n"
        f"Observed At: {timestamps.get('observedAt', '')}\n"
        f"Raised At: {timestamps.get('raisedAt', '')}\n"
        f"Resolved At: {timestamps.get('resolvedAt', '')}\n"
    )


def _resolve_secret(secret_ref: str | None) -> str | None:
    if not secret_ref:
        return None
    if secret_ref.startswith("env:"):
        return os.getenv(secret_ref.split(":", 1)[1])
    return secret_ref


def _ensure_env_email_channel(session: Session, now: datetime) -> AlertDeliveryChannel:
    channel = session.scalar(
        select(AlertDeliveryChannel).where(AlertDeliveryChannel.channel_key == "env-email-inline")
    )
    recipients = _csv(os.getenv("ALERT_NOTIFY_EMAIL_TO"))
    sender = os.getenv("ALERT_NOTIFY_EMAIL_FROM") or os.getenv("ALERT_NOTIFY_SMTP_USERNAME") or "bhm-alerts@localhost"
    payload = json.dumps(
        {
            "managedBy": "environment",
            "recipients": recipients,
            "from": sender,
        },
        ensure_ascii=True,
        sort_keys=True,
    )
    if channel is None:
        channel = AlertDeliveryChannel(
            channel_key="env-email-inline",
            channel_type="email",
            display_name="Environment SMTP",
            enabled=True,
            config_json=payload,
            secret_ref=None,
            last_delivery_status=None,
            last_attempt_at=None,
            created_at=now,
            updated_at=now,
        )
        session.add(channel)
        session.flush()
        return channel

    channel.enabled = True
    channel.config_json = payload
    channel.updated_at = now
    session.flush()
    return channel


def _resolve_channels_for_event(session: Session, event: AlertDeliveryEvent, now: datetime) -> list[AlertDeliveryChannel]:
    if event.channel_policy_id == "env-email-inline":
        return [_ensure_env_email_channel(session, now)]

    rows = session.scalars(
        select(AlertDeliveryChannel)
        .where(AlertDeliveryChannel.enabled.is_(True))
        .order_by(AlertDeliveryChannel.id.asc())
    ).all()
    return list(rows)


def _latest_attempt(session: Session, event_id: str, channel_id: int) -> AlertDeliveryAttempt | None:
    return session.scalar(
        select(AlertDeliveryAttempt)
        .where(
            AlertDeliveryAttempt.event_id == event_id,
            AlertDeliveryAttempt.channel_id == channel_id,
        )
        .order_by(AlertDeliveryAttempt.attempt_number.desc())
    )


def _schedule_retry(now: datetime, attempt_number: int) -> datetime:
    delay_index = min(max(0, attempt_number - 1), len(_RETRY_DELAYS_SECONDS) - 1)
    return now + timedelta(seconds=_RETRY_DELAYS_SECONDS[delay_index])


def _send_email(payload: Dict[str, Any], channel: AlertDeliveryChannel) -> Dict[str, Any]:
    config = _load_json(channel.config_json)
    recipients = config.get("recipients") if isinstance(config.get("recipients"), list) else _csv(os.getenv("ALERT_NOTIFY_EMAIL_TO"))
    recipients = [str(item).strip() for item in recipients if str(item).strip()]
    if not recipients:
        raise AlertDeliveryPermanentError("email_recipients_missing")

    smtp_host = os.getenv("ALERT_NOTIFY_SMTP_HOST", "")
    if not smtp_host:
        raise AlertDeliveryPermanentError("smtp_host_missing")

    smtp_port = int(os.getenv("ALERT_NOTIFY_SMTP_PORT", "587"))
    smtp_user = os.getenv("ALERT_NOTIFY_SMTP_USERNAME")
    smtp_pass = os.getenv("ALERT_NOTIFY_SMTP_PASSWORD")
    smtp_starttls = _as_bool(os.getenv("ALERT_NOTIFY_SMTP_STARTTLS"), default=True)
    smtp_ssl = _as_bool(os.getenv("ALERT_NOTIFY_SMTP_SSL"), default=False)
    sender = str(config.get("from") or os.getenv("ALERT_NOTIFY_EMAIL_FROM") or smtp_user or "bhm-alerts@localhost")

    msg = EmailMessage()
    msg["Subject"] = _build_email_subject(payload)
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg["Message-ID"] = f"<{payload.get('eventId', uuid.uuid4())}@bhm.local>"
    msg["X-BHM-Event-Id"] = str(payload.get("eventId") or "")
    msg["X-BHM-Alert-Id"] = str(payload.get("alertId") or "")
    msg.set_content(_build_email_body(payload))

    try:
        if smtp_ssl:
            with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15) as smtp:
                if smtp_user and smtp_pass:
                    smtp.login(smtp_user, smtp_pass)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as smtp:
                if smtp_starttls:
                    smtp.starttls()
                if smtp_user and smtp_pass:
                    smtp.login(smtp_user, smtp_pass)
                smtp.send_message(msg)
    except (socket.gaierror, socket.timeout, smtplib.SMTPServerDisconnected) as exc:
        raise AlertDeliveryTransientError(str(exc)) from exc
    except smtplib.SMTPAuthenticationError as exc:
        raise AlertDeliveryPermanentError(str(exc)) from exc
    except Exception as exc:
        raise AlertDeliveryPermanentError(str(exc)) from exc

    return {
        "provider_status_code": None,
        "provider_message_id": msg["Message-ID"],
        "response_payload_json": json.dumps({"recipients": recipients}, ensure_ascii=True, sort_keys=True),
    }


def _send_webhook(payload: Dict[str, Any], channel: AlertDeliveryChannel) -> Dict[str, Any]:
    config = _load_json(channel.config_json)
    url = str(config.get("url") or "").strip()
    if not url:
        raise AlertDeliveryPermanentError("webhook_url_missing")

    timeout_seconds = int(config.get("timeout_seconds") or 15)
    headers = {
        "Content-Type": "application/json",
        "X-BHM-Event-Id": str(payload.get("eventId") or ""),
        "X-BHM-Alert-Id": str(payload.get("alertId") or ""),
        "X-BHM-Dedupe-Key": str(payload.get("dedupeKey") or ""),
    }
    extra_headers = config.get("headers") if isinstance(config.get("headers"), dict) else {}
    headers.update({str(key): str(value) for key, value in extra_headers.items()})

    shared_secret = _resolve_secret(channel.secret_ref)
    if shared_secret:
        headers["X-BHM-Signature"] = shared_secret

    try:
        response = httpx.post(url, json=payload, headers=headers, timeout=timeout_seconds)
    except (httpx.TimeoutException, httpx.NetworkError) as exc:
        raise AlertDeliveryTransientError(str(exc)) from exc
    except Exception as exc:
        raise AlertDeliveryPermanentError(str(exc)) from exc

    if response.status_code == 429 or 500 <= response.status_code < 600:
        raise AlertDeliveryTransientError(f"http_{response.status_code}")
    if response.status_code >= 400:
        raise AlertDeliveryPermanentError(f"http_{response.status_code}")

    return {
        "provider_status_code": response.status_code,
        "provider_message_id": response.headers.get("X-Request-Id"),
        "response_payload_json": json.dumps({"status_code": response.status_code}, ensure_ascii=True, sort_keys=True),
    }


def _dispatch_channel(payload: Dict[str, Any], channel: AlertDeliveryChannel) -> Dict[str, Any]:
    if channel.channel_type == "email":
        return _send_email(payload, channel)
    if channel.channel_type == "webhook":
        return _send_webhook(payload, channel)
    raise AlertDeliveryPermanentError(f"unsupported_channel_type:{channel.channel_type}")


def _update_channel_status(channel: AlertDeliveryChannel, attempt_state: str, now: datetime) -> None:
    channel.last_delivery_status = attempt_state
    channel.last_attempt_at = now
    channel.updated_at = now


def _finalize_event_state(session: Session, event: AlertDeliveryEvent, channels: list[AlertDeliveryChannel], now: datetime) -> None:
    if not channels:
        event.delivery_state = "dead_letter"
        event.next_attempt_at = None
        event.updated_at = now
        return

    sent_channels = 0
    retry_times: list[datetime] = []
    exhausted_failures = 0

    for channel in channels:
        latest = _latest_attempt(session, event.event_id, channel.id)
        if latest is None:
            retry_times.append(now)
            continue
        if latest.attempt_state == "sent":
            sent_channels += 1
            continue
        if latest.attempt_state == "failed" and latest.attempt_number >= _MAX_ATTEMPTS:
            exhausted_failures += 1
            continue
        if latest.attempt_state == "failed":
            retry_times.append(latest.scheduled_at)

    if sent_channels == len(channels):
        event.delivery_state = "delivered"
        event.next_attempt_at = None
    elif sent_channels > 0:
        event.delivery_state = "partially_delivered"
        event.next_attempt_at = min(retry_times) if retry_times else None
    elif exhausted_failures == len(channels):
        event.delivery_state = "dead_letter"
        event.next_attempt_at = None
    else:
        event.delivery_state = "pending"
        event.next_attempt_at = min(retry_times) if retry_times else now
    event.updated_at = now


def process_pending_alert_delivery_events(
    *,
    limit: int = 20,
    session_factory: sessionmaker[Session] | None = None,
    now: datetime | None = None,
) -> Dict[str, int]:
    session_factory = session_factory or _get_session_factory()
    current_time = _now_naive(now)
    processed = 0
    delivered = 0
    failed = 0

    with session_scope(session_factory) as session:
        events = session.scalars(
            select(AlertDeliveryEvent)
            .where(
                AlertDeliveryEvent.delivery_state.in_(_PROCESSABLE_EVENT_STATES),
                or_(
                    AlertDeliveryEvent.next_attempt_at.is_(None),
                    AlertDeliveryEvent.next_attempt_at <= current_time,
                ),
            )
            .order_by(AlertDeliveryEvent.created_at.asc())
            .limit(max(1, limit))
        ).all()

        for event in events:
            payload = _load_json(event.payload_json)
            channels = _resolve_channels_for_event(session, event, current_time)
            processed += 1

            if not channels:
                failed += 1
                event.delivery_state = "dead_letter"
                event.next_attempt_at = None
                event.updated_at = current_time
                continue

            for channel in channels:
                latest = _latest_attempt(session, event.event_id, channel.id)
                if latest is not None and latest.attempt_state == "sent":
                    continue
                if latest is not None and latest.attempt_state == "failed" and latest.attempt_number >= _MAX_ATTEMPTS:
                    continue

                attempt_number = 1 if latest is None else latest.attempt_number + 1
                attempt = AlertDeliveryAttempt(
                    event_id=event.event_id,
                    channel_id=channel.id,
                    attempt_number=attempt_number,
                    attempt_state="pending",
                    scheduled_at=current_time,
                    started_at=current_time,
                    finished_at=None,
                    provider_status_code=None,
                    provider_message_id=None,
                    error_class=None,
                    error_detail=None,
                    response_payload_json=None,
                    created_at=current_time,
                )
                session.add(attempt)
                session.flush()

                try:
                    delivery_result = _dispatch_channel(payload, channel)
                    attempt.attempt_state = "sent"
                    attempt.provider_status_code = delivery_result.get("provider_status_code")
                    attempt.provider_message_id = delivery_result.get("provider_message_id")
                    attempt.response_payload_json = delivery_result.get("response_payload_json")
                    _update_channel_status(channel, "sent", current_time)
                except AlertDeliveryTransientError as exc:
                    attempt.attempt_state = "failed"
                    attempt.error_class = exc.__class__.__name__
                    attempt.error_detail = str(exc)
                    _update_channel_status(channel, "failed", current_time)
                    if attempt_number < _MAX_ATTEMPTS:
                        attempt.scheduled_at = _schedule_retry(current_time, attempt_number)
                    else:
                        failed += 1
                except AlertDeliveryPermanentError as exc:
                    attempt.attempt_state = "failed"
                    attempt.error_class = exc.__class__.__name__
                    attempt.error_detail = str(exc)
                    _update_channel_status(channel, "failed", current_time)
                    failed += 1
                finally:
                    attempt.finished_at = current_time

            _finalize_event_state(session, event, channels, current_time)
            if event.delivery_state == "delivered":
                delivered += 1

    return {
        "processed": processed,
        "delivered": delivered,
        "failed": failed,
    }