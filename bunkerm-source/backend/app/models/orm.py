"""
Modelos ORM SQLAlchemy para el backend unificado.
Reemplazan el almacenamiento JSON de data_storage.py (datos históricos)
y alert_config.json (configuración de alertas).
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class AlertConfigEntry(Base):
    """
    Par clave-valor para almacenar la configuración de alertas del monitor.
    Reemplaza alert_config.json en /nextjs/data/.
    """
    __tablename__ = "alert_config"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value_json: Mapped[str] = mapped_column(Text, nullable=False)


class AlertDeliveryChannel(Base):
    """Delivery channel configuration for external technical alerts."""
    __tablename__ = "alert_delivery_channel"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    channel_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    secret_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)
    last_delivery_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class AlertDeliveryEvent(Base):
    """Canonical alert delivery outbox event persisted before delivery attempts."""
    __tablename__ = "alert_delivery_event"

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    alert_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    dedupe_key: Mapped[str] = mapped_column(String(256), nullable=False, unique=True, index=True)
    transition: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    delivery_state: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    channel_policy_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    channel_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class AlertDeliveryAttempt(Base):
    """Per-channel delivery attempt audit for an outbox event."""
    __tablename__ = "alert_delivery_attempt"
    __table_args__ = (
        UniqueConstraint(
            "event_id",
            "channel_id",
            "attempt_number",
            name="uq_alert_delivery_attempt_event_channel_attempt",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("alert_delivery_event.event_id"),
        nullable=False,
        index=True,
    )
    channel_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("alert_delivery_channel.id"),
        nullable=False,
        index=True,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    attempt_state: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    provider_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    error_class: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class BrokerBaseline(Base):
    """
    Guarda los valores absolutos acumulados del broker en el arranque
    para poder calcular deltas en el primer tick.
    Solo hay una fila con id=1.
    """
    __tablename__ = "broker_baseline"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    msg_received_base: Mapped[int] = mapped_column(Integer, default=0)
    msg_sent_base: Mapped[int] = mapped_column(Integer, default=0)
    bytes_received_base: Mapped[int] = mapped_column(Integer, default=0)
    bytes_sent_base: Mapped[int] = mapped_column(Integer, default=0)
    load_1min: Mapped[float] = mapped_column(Float, default=0.0)
    load_5min: Mapped[float] = mapped_column(Float, default=0.0)
    load_15min: Mapped[float] = mapped_column(Float, default=0.0)


class BrokerMetricTick(Base):
    """Persiste cada tick de métricas del broker para reportes históricos y análisis de tendencias."""
    __tablename__ = "broker_metric_ticks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, nullable=False, unique=True, index=True)
    bytes_received_rate: Mapped[float] = mapped_column(Float, default=0.0)
    bytes_sent_rate: Mapped[float] = mapped_column(Float, default=0.0)
    messages_received_delta: Mapped[int] = mapped_column(Integer, default=0)
    messages_sent_delta: Mapped[int] = mapped_column(Integer, default=0)
    connected_clients: Mapped[int] = mapped_column(Integer, default=0)
    disconnected_clients: Mapped[int] = mapped_column(Integer, default=0)
    active_sessions: Mapped[int] = mapped_column(Integer, default=0)
    max_concurrent: Mapped[int] = mapped_column(Integer, default=0)
    total_subscriptions: Mapped[int] = mapped_column(Integer, default=0)
    retained_messages: Mapped[int] = mapped_column(Integer, default=0)
    messages_inflight: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[float] = mapped_column(Float, default=-1.0)
    cpu_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    memory_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    memory_pct: Mapped[float | None] = mapped_column(Float, nullable=True)


class BrokerRuntimeState(Base):
    """Single-row operational state for continuity across app restarts."""
    __tablename__ = "broker_runtime_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    last_tick_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_broker_uptime: Mapped[str | None] = mapped_column(String(128), nullable=True)
    current_max_concurrent: Mapped[int] = mapped_column(Integer, default=0)
    lifetime_max_concurrent: Mapped[int] = mapped_column(Integer, default=0)
    last_messages_received_total: Mapped[int] = mapped_column(Integer, default=0)
    last_messages_sent_total: Mapped[int] = mapped_column(Integer, default=0)


class BrokerDailySummary(Base):
    """Daily broker rollup for reports and longer-term queries."""
    __tablename__ = "broker_daily_summary"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    peak_connected_clients: Mapped[int] = mapped_column(Integer, default=0)
    peak_active_sessions: Mapped[int] = mapped_column(Integer, default=0)
    peak_max_concurrent: Mapped[int] = mapped_column(Integer, default=0)
    total_messages_received: Mapped[int] = mapped_column(Integer, default=0)
    total_messages_sent: Mapped[int] = mapped_column(Integer, default=0)
    bytes_received_rate_sum: Mapped[float] = mapped_column(Float, default=0.0)
    bytes_sent_rate_sum: Mapped[float] = mapped_column(Float, default=0.0)
    latency_samples: Mapped[int] = mapped_column(Integer, default=0)
    latency_sum: Mapped[float] = mapped_column(Float, default=0.0)


class TopicRegistry(Base):
    """Catalog of topics observed by the broker for persistent topology queries."""
    __tablename__ = "topic_registry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topic: Mapped[str] = mapped_column(String(512), nullable=False, unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(32), default="user")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class TopicPublishBucket(Base):
    """Bucketed publish activity per topic for time-window topology reporting."""
    __tablename__ = "topic_publish_buckets"
    __table_args__ = (
        UniqueConstraint("bucket_start", "bucket_minutes", "topic_id", name="uq_topic_publish_bucket"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bucket_start: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    bucket_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    topic_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    publish_count: Mapped[int] = mapped_column(Integer, default=0)
    bytes_sum: Mapped[int] = mapped_column(Integer, default=0)


class TopicSubscribeBucket(Base):
    """Bucketed subscribe activity per topic for time-window subscription reporting."""
    __tablename__ = "topic_subscribe_buckets"
    __table_args__ = (
        UniqueConstraint("bucket_start", "bucket_minutes", "topic_id", name="uq_topic_subscribe_bucket"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bucket_start: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    bucket_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    topic_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    subscribe_count: Mapped[int] = mapped_column(Integer, default=0)


class TopicMessageEvent(Base):
    """Append-only payload history per topic for MQTT Explorer detail view."""
    __tablename__ = "topic_message_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topic_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    event_ts: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    payload_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    payload_bytes: Mapped[int] = mapped_column(Integer, default=0)
    qos: Mapped[int] = mapped_column(Integer, default=0)
    retained: Mapped[bool] = mapped_column(Boolean, default=False)


class ClientRegistry(Base):
    """Persistent catalog of MQTT clients synchronized from DynSec."""
    __tablename__ = "client_registry"

    username: Mapped[str] = mapped_column(String(128), primary_key=True)
    textname: Mapped[str | None] = mapped_column(String(256), nullable=True)
    disabled: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_dynsec_sync_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class ClientSessionEvent(Base):
    """Append-only session and auth event history for MQTT clients."""
    __tablename__ = "client_session_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    client_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    event_ts: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    disconnect_kind: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    protocol_level: Mapped[str | None] = mapped_column(String(64), nullable=True)
    clean_session: Mapped[bool | None] = mapped_column(nullable=True)
    keep_alive: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ClientTopicEvent(Base):
    """Append-only publish/subscribe topic event history for MQTT clients."""
    __tablename__ = "client_topic_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    client_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    event_ts: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    topic: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    qos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retained: Mapped[bool | None] = mapped_column(nullable=True)


class ClientSubscriptionState(Base):
    """Observed subscription state by client and topic."""
    __tablename__ = "client_subscription_state"
    __table_args__ = (
        UniqueConstraint("username", "topic", name="uq_client_subscription_state"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    topic: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    qos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True)
    source: Mapped[str] = mapped_column(String(64), default="clientlogs")


class ClientPublishState(Base):
    """Observed publish topic state by client and topic (one record per username/topic)."""
    __tablename__ = "client_publish_state"
    __table_args__ = (
        UniqueConstraint("username", "topic", name="uq_client_publish_state"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    topic: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True)
    source: Mapped[str] = mapped_column(String(64), default="clientlogs")


class ClientDailySummary(Base):
    """Daily audit summary by username for quick reporting."""
    __tablename__ = "client_daily_summary"
    __table_args__ = (
        UniqueConstraint("username", "day", name="uq_client_daily_summary"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    day: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    connects: Mapped[int] = mapped_column(Integer, default=0)
    disconnects_graceful: Mapped[int] = mapped_column(Integer, default=0)
    disconnects_ungraceful: Mapped[int] = mapped_column(Integer, default=0)
    auth_failures: Mapped[int] = mapped_column(Integer, default=0)
    publishes: Mapped[int] = mapped_column(Integer, default=0)
    subscribes: Mapped[int] = mapped_column(Integer, default=0)
    distinct_publish_topics: Mapped[int] = mapped_column(Integer, default=0)
    distinct_subscribe_topics: Mapped[int] = mapped_column(Integer, default=0)


class ClientDailyDistinctTopic(Base):
    """Distinct topics seen per user/day and event type for reporting summaries."""
    __tablename__ = "client_daily_distinct_topics"

    username: Mapped[str] = mapped_column(String(128), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(32), primary_key=True)
    topic: Mapped[str] = mapped_column(String(512), primary_key=True)


class BrokerDesiredState(Base):
    """Estado deseado/aplicado/observado para cortes transicionales del control-plane."""
    __tablename__ = "broker_desired_state"

    scope: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    desired_payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    applied_payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    observed_payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    reconcile_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    drift_detected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    desired_updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    reconciled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class BrokerDesiredStateAudit(Base):
    """Append-only audit trail for desired-state change requests in the control-plane."""
    __tablename__ = "broker_desired_state_audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    event_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    desired_payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    applied_payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    observed_payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    reconcile_status: Mapped[str] = mapped_column(String(32), nullable=False)
    drift_detected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)


class BrokerReconcileSecret(Base):
    """Encrypted ephemeral handoff material for broker-facing reconciliation flows."""
    __tablename__ = "broker_reconcile_secret"

    secret_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    encrypted_payload: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class ClientMQTTEvent(Base):
    """Append-only unified event log for all MQTT client events (connections, publishes, subscribes, auth failures)."""
    __tablename__ = "client_mqtt_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True)
    event_ts: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    client_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    protocol_level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    clean_session: Mapped[bool | None] = mapped_column(nullable=True)
    keep_alive: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    details: Mapped[str] = mapped_column(Text, nullable=False)
    topic: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    qos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retained: Mapped[bool | None] = mapped_column(nullable=True)
    disconnect_kind: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class BhmUser(Base):
    """Panel user record stored in the `identity` schema.

    This model backs the `identity.bhm_users` table used by the
    `bhm-identity` service and the unified backend seeding logic.
    """
    __tablename__ = "bhm_users"
    __table_args__ = {"schema": "identity"}

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str] = mapped_column(String(128), nullable=False)
    last_name: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="user")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    # created_at/updated_at are managed by callers; keep fields explicit
