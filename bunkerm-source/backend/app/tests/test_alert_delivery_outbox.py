import json

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from core.database import Base
from models.orm import AlertDeliveryEvent
from services.alert_delivery_outbox import enqueue_alert_delivery_event


def _build_session_factory():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def test_enqueue_alert_delivery_event_persists_canonical_outbox(monkeypatch):
    session_factory = _build_session_factory()
    monkeypatch.setenv("ALERT_NOTIFY_ENABLED", "true")
    monkeypatch.setenv("ALERT_NOTIFY_EMAIL_ENABLED", "true")
    monkeypatch.setenv("ALERT_NOTIFY_EMAIL_TO", "ops@example.com")

    event_id = enqueue_alert_delivery_event(
        {
            "id": "alert-001",
            "type": "broker_down",
            "severity": "critical",
            "title": "Broker Unreachable",
            "description": "Broker has not responded for 5 polls.",
            "impact": "All MQTT clients lose connectivity.",
            "timestamp": "2026-04-20T06:30:00Z",
            "status": "active",
        },
        session_factory=session_factory,
    )

    with session_factory() as session:
        row = session.scalar(select(AlertDeliveryEvent).where(AlertDeliveryEvent.event_id == event_id))

    assert row is not None
    assert row.alert_id == "alert-001"
    assert row.transition == "raised"
    assert row.delivery_state == "pending"
    assert row.channel_policy_id == "env-email-inline"
    assert row.channel_count == 1

    payload = json.loads(row.payload_json)
    assert payload["eventId"] == event_id
    assert payload["alertId"] == "alert-001"
    assert payload["transition"] == "raised"
    assert payload["routing"]["channelPolicyId"] == "env-email-inline"
    assert payload["routing"]["channelCount"] == 1


def test_enqueue_alert_delivery_event_is_idempotent_by_dedupe_key(monkeypatch):
    session_factory = _build_session_factory()
    monkeypatch.setenv("ALERT_NOTIFY_ENABLED", "true")
    monkeypatch.setenv("ALERT_NOTIFY_EMAIL_ENABLED", "true")
    monkeypatch.setenv("ALERT_NOTIFY_EMAIL_TO", "ops@example.com")

    alert = {
        "id": "alert-002",
        "type": "auth_failure",
        "severity": "high",
        "title": "Authentication Failures",
        "description": "Repeated authentication failures detected.",
        "impact": "Possible brute-force attempt.",
        "timestamp": "2026-04-20T06:31:00Z",
        "status": "active",
    }

    first_event_id = enqueue_alert_delivery_event(alert, session_factory=session_factory)
    second_event_id = enqueue_alert_delivery_event(alert, session_factory=session_factory)

    with session_factory() as session:
        rows = session.scalars(select(AlertDeliveryEvent)).all()

    assert first_event_id == second_event_id
    assert len(rows) == 1