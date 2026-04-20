import json
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import routers.notifications as notifications_router
from core.database import Base
from models.orm import AlertDeliveryAttempt, AlertDeliveryChannel, AlertDeliveryEvent


def _build_session_factory(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'notifications.db').as_posix()}", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


async def test_notifications_channels_expose_env_fallback_redacted(client, tmp_path, monkeypatch):
    session_factory = _build_session_factory(tmp_path)
    monkeypatch.setattr(notifications_router.notifications_service, "_get_session_factory", lambda: session_factory)
    monkeypatch.setenv("ALERT_NOTIFY_ENABLED", "true")
    monkeypatch.setenv("ALERT_NOTIFY_EMAIL_ENABLED", "true")
    monkeypatch.setenv("ALERT_NOTIFY_EMAIL_TO", "ops@example.com,alerts@example.com")
    monkeypatch.setenv("ALERT_NOTIFY_EMAIL_FROM", "bhm@example.com")
    monkeypatch.setenv("ALERT_NOTIFY_SMTP_PASSWORD", "super-secret")

    resp = await client.get("/api/v1/notifications/channels")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total"] == 1
    channel = payload["channels"][0]
    assert channel["channelKey"] == "env-email-inline"
    assert channel["managedBy"] == "environment"
    assert channel["hasSecret"] is True
    assert channel["config"]["recipientCount"] == 2
    assert channel["config"]["from"] == "bhm@example.com"
    assert channel["retryPolicySummary"]["maxAttempts"] == 5


async def test_notifications_endpoints_require_auth(raw_client):
    channels_resp = await raw_client.get("/api/v1/notifications/channels")
    events_resp = await raw_client.get("/api/v1/notifications/events")
    attempts_resp = await raw_client.get("/api/v1/notifications/attempts")

    assert channels_resp.status_code in (401, 403)
    assert events_resp.status_code in (401, 403)
    assert attempts_resp.status_code in (401, 403)


async def test_notifications_endpoints_list_channels_events_and_attempts(client, tmp_path, monkeypatch):
    session_factory = _build_session_factory(tmp_path)
    monkeypatch.setattr(notifications_router.notifications_service, "_get_session_factory", lambda: session_factory)

    create_resp = await client.post(
        "/api/v1/notifications/channels",
        json={
            "channelKey": "ops-webhook",
            "channelType": "webhook",
            "displayName": "Ops Webhook",
            "enabled": True,
            "config": {
                "url": "https://ops.example/webhook",
                "timeout_seconds": 10,
                "headers": {"X-Tenant": "bhm"},
            },
            "secretRef": "env:OPS_WEBHOOK_SECRET",
        },
    )

    assert create_resp.status_code == 200
    channel = create_resp.json()
    assert channel["channelType"] == "webhook"
    assert channel["hasSecret"] is True
    assert channel["config"]["url"] == "https://ops.example/webhook"
    assert channel["config"]["headerNames"] == ["X-Tenant"]
    assert channel["secretRef"] is None

    now = datetime(2026, 4, 20, 9, 0, 0, tzinfo=timezone.utc).replace(tzinfo=None)
    with session_factory() as session:
        session.add(
            AlertDeliveryEvent(
                event_id="event-100",
                alert_id="alert-100",
                dedupe_key="alert-100:raised:db-channels",
                transition="raised",
                status="active",
                delivery_state="partially_delivered",
                channel_policy_id="db-channels",
                channel_count=1,
                payload_json=json.dumps(
                    {
                        "eventId": "event-100",
                        "alertId": "alert-100",
                        "dedupeKey": "alert-100:raised:db-channels",
                        "transition": "raised",
                        "status": "active",
                        "type": "broker_down",
                        "severity": "critical",
                        "title": "Broker Unreachable",
                        "description": "Broker stopped responding",
                        "impact": "Clients cannot connect",
                        "source": {"service": "bhm-api", "component": "monitor.alert-engine", "broker": "bhm-broker"},
                        "timestamps": {"observedAt": "2026-04-20T09:00:00Z", "raisedAt": "2026-04-20T09:00:00Z", "resolvedAt": None},
                        "links": {"monitor": "/api/v1/monitor/alerts/broker", "alert": "/api/v1/monitor/alerts/broker/alert-100"},
                        "routing": {"channelPolicyId": "db-channels", "channelCount": 1},
                    },
                    ensure_ascii=True,
                    sort_keys=True,
                ),
                next_attempt_at=now,
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            AlertDeliveryAttempt(
                event_id="event-100",
                channel_id=channel["id"],
                attempt_number=1,
                attempt_state="failed",
                scheduled_at=now,
                started_at=now,
                finished_at=now,
                provider_status_code=500,
                provider_message_id=None,
                error_class="AlertDeliveryTransientError",
                error_detail="http_500",
                response_payload_json=None,
                created_at=now,
            )
        )
        session.commit()

    events_resp = await client.get("/api/v1/notifications/events", params={"delivery_state": "partially_delivered"})
    attempts_resp = await client.get("/api/v1/notifications/attempts", params={"event_id": "event-100"})

    assert events_resp.status_code == 200
    assert attempts_resp.status_code == 200

    events_payload = events_resp.json()
    attempts_payload = attempts_resp.json()

    assert events_payload["total"] == 1
    assert events_payload["events"][0]["eventId"] == "event-100"
    assert events_payload["events"][0]["type"] == "broker_down"
    assert events_payload["events"][0]["routing"]["channelCount"] == 1

    assert attempts_payload["total"] == 1
    assert attempts_payload["attempts"][0]["channelKey"] == "ops-webhook"
    assert attempts_payload["attempts"][0]["attemptState"] == "failed"
    assert attempts_payload["attempts"][0]["providerStatusCode"] == 500


async def test_notifications_exports_support_csv_and_json(client, tmp_path, monkeypatch):
    session_factory = _build_session_factory(tmp_path)
    monkeypatch.setattr(notifications_router.notifications_service, "_get_session_factory", lambda: session_factory)

    with session_factory() as session:
        channel = AlertDeliveryChannel(
            channel_key="ops-email",
            channel_type="email",
            display_name="Ops Email",
            enabled=True,
            config_json=json.dumps({"recipients": ["ops@example.com"], "from": "bhm@example.com"}, ensure_ascii=True),
            secret_ref="env:SMTP_PASSWORD",
            last_delivery_status="sent",
            last_attempt_at=datetime(2026, 4, 20, 10, 0, 0, tzinfo=timezone.utc).replace(tzinfo=None),
            created_at=datetime(2026, 4, 20, 9, 59, 0, tzinfo=timezone.utc).replace(tzinfo=None),
            updated_at=datetime(2026, 4, 20, 10, 0, 0, tzinfo=timezone.utc).replace(tzinfo=None),
        )
        session.add(channel)
        session.flush()
        now = datetime(2026, 4, 20, 10, 0, 0, tzinfo=timezone.utc).replace(tzinfo=None)
        session.add(
            AlertDeliveryEvent(
                event_id="event-200",
                alert_id="alert-200",
                dedupe_key="alert-200:raised:db-channels",
                transition="raised",
                status="active",
                delivery_state="delivered",
                channel_policy_id="db-channels",
                channel_count=1,
                payload_json=json.dumps(
                    {
                        "eventId": "event-200",
                        "alertId": "alert-200",
                        "type": "auth_failure",
                        "severity": "high",
                        "title": "Auth Failures",
                        "description": "Repeated auth failures",
                        "impact": "Potential brute-force attempt",
                        "routing": {"channelPolicyId": "db-channels", "channelCount": 1},
                        "timestamps": {"observedAt": "2026-04-20T10:00:00Z", "raisedAt": "2026-04-20T10:00:00Z", "resolvedAt": None},
                    },
                    ensure_ascii=True,
                    sort_keys=True,
                ),
                next_attempt_at=None,
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            AlertDeliveryAttempt(
                event_id="event-200",
                channel_id=channel.id,
                attempt_number=1,
                attempt_state="sent",
                scheduled_at=now,
                started_at=now,
                finished_at=now,
                provider_status_code=202,
                provider_message_id="msg-200",
                error_class=None,
                error_detail=None,
                response_payload_json=json.dumps({"status": "accepted"}, ensure_ascii=True),
                created_at=now,
            )
        )
        session.commit()

    events_export = await client.get("/api/v1/notifications/export/events", params={"export_format": "csv"})
    attempts_export = await client.get("/api/v1/notifications/export/attempts", params={"event_id": "event-200", "export_format": "json"})

    assert events_export.status_code == 200
    assert events_export.headers["content-type"].startswith("text/csv")
    assert "eventId,alertId,dedupeKey" in events_export.text
    assert "event-200,alert-200" in events_export.text

    assert attempts_export.status_code == 200
    assert attempts_export.headers["content-type"].startswith("application/json")
    attempts_payload = attempts_export.json()
    assert attempts_payload["total"] == 1
    assert attempts_payload["attempts"][0]["providerMessageId"] == "msg-200"