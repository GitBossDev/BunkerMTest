import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from core.database import Base
from models.orm import AlertDeliveryAttempt, AlertDeliveryChannel, AlertDeliveryEvent
from services.alert_delivery_outbox import enqueue_alert_delivery_event
import services.alert_delivery_worker as worker


def _build_session_factory():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def test_process_pending_alert_delivery_events_delivers_env_email(monkeypatch):
    session_factory = _build_session_factory()
    monkeypatch.setenv("ALERT_NOTIFY_ENABLED", "true")
    monkeypatch.setenv("ALERT_NOTIFY_EMAIL_ENABLED", "true")
    monkeypatch.setenv("ALERT_NOTIFY_EMAIL_TO", "ops@example.com")

    enqueue_alert_delivery_event(
        {
            "id": "alert-003",
            "type": "broker_down",
            "severity": "critical",
            "title": "Broker Unreachable",
            "description": "Broker has not responded for 5 polls.",
            "impact": "All MQTT clients lose connectivity.",
            "timestamp": "2026-04-20T08:00:00Z",
            "status": "active",
        },
        session_factory=session_factory,
    )

    def fake_send_email(payload, channel):
        assert payload["alertId"] == "alert-003"
        assert channel.channel_key == "env-email-inline"
        return {
            "provider_status_code": None,
            "provider_message_id": "<event-003@bhm.local>",
            "response_payload_json": json.dumps({"recipients": ["ops@example.com"]}, ensure_ascii=True),
        }

    monkeypatch.setattr(worker, "_send_email", fake_send_email)

    result = worker.process_pending_alert_delivery_events(session_factory=session_factory, now=datetime(2026, 4, 20, 8, 1, 0, tzinfo=timezone.utc))

    with session_factory() as session:
        event = session.scalar(select(AlertDeliveryEvent).where(AlertDeliveryEvent.alert_id == "alert-003"))
        attempts = session.scalars(select(AlertDeliveryAttempt).where(AlertDeliveryAttempt.event_id == event.event_id)).all()
        channel = session.scalar(select(AlertDeliveryChannel).where(AlertDeliveryChannel.channel_key == "env-email-inline"))

    assert result == {"processed": 1, "delivered": 1, "failed": 0}
    assert event is not None
    assert event.delivery_state == "delivered"
    assert len(attempts) == 1
    assert attempts[0].attempt_state == "sent"
    assert channel is not None
    assert channel.last_delivery_status == "sent"


def test_process_pending_alert_delivery_events_retries_transient_failure(monkeypatch):
    session_factory = _build_session_factory()
    now = datetime(2026, 4, 20, 8, 5, 0, tzinfo=timezone.utc)

    with session_factory() as session:
        channel = AlertDeliveryChannel(
            channel_key="ops-webhook",
            channel_type="webhook",
            display_name="Ops Webhook",
            enabled=True,
            config_json=json.dumps({"url": "https://ops.example/webhook"}, ensure_ascii=True),
            secret_ref=None,
            last_delivery_status=None,
            last_attempt_at=None,
            created_at=now.replace(tzinfo=None),
            updated_at=now.replace(tzinfo=None),
        )
        session.add(channel)
        session.flush()
        session.add(
            AlertDeliveryEvent(
                event_id="event-004",
                alert_id="alert-004",
                dedupe_key="alert-004:raised:db-channels",
                transition="raised",
                status="active",
                delivery_state="pending",
                channel_policy_id="db-channels",
                channel_count=1,
                payload_json=json.dumps({"eventId": "event-004", "alertId": "alert-004", "title": "Test", "severity": "high", "dedupeKey": "alert-004:raised:db-channels"}, ensure_ascii=True),
                next_attempt_at=now.replace(tzinfo=None),
                created_at=now.replace(tzinfo=None),
                updated_at=now.replace(tzinfo=None),
            )
        )
        session.commit()

    def fake_send_webhook(payload, channel):
        raise worker.AlertDeliveryTransientError("timeout")

    monkeypatch.setattr(worker, "_send_webhook", fake_send_webhook)

    result = worker.process_pending_alert_delivery_events(session_factory=session_factory, now=now)

    with session_factory() as session:
        event = session.get(AlertDeliveryEvent, "event-004")
        attempt = session.scalar(select(AlertDeliveryAttempt).where(AlertDeliveryAttempt.event_id == "event-004"))

    assert result == {"processed": 1, "delivered": 0, "failed": 0}
    assert event is not None
    assert event.delivery_state == "pending"
    assert event.next_attempt_at is not None
    assert event.next_attempt_at >= now.replace(tzinfo=None) + timedelta(seconds=30)
    assert attempt is not None
    assert attempt.attempt_state == "failed"