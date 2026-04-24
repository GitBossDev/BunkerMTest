# SQLite Persistence Phases

> Context document for persistent broker statistics, client activity history and audit features.
> This file is intended to remain in the project root as the execution checklist for the next implementation stages.

Last update: 2026-04-13
Status: Phase 4 implemented

---

## Goals

- Persist broker historical metrics beyond app restarts or crashes.
- Keep a reliable audit trail of client activity for up to 30 days.
- Use the existing SQLite backend database at `/nextjs/data/bunkerm.db`.
- Avoid storing dashboard-only transient state in memory when it is relevant for reports or incident review.

---

## Design Principles

- Store raw operational events append-only where useful.
- Derive UI summaries from persisted raw data or from daily rollups.
- Keep bucketed broker metrics small and query-friendly.
- Distinguish configuration state from observed activity.
- Prefer one shared SQLite database over sidecar files.
- Retain raw client activity for 30 days maximum unless a future reporting feature requires longer retention.

---

## Phase 1 - Persistent Broker History

Objective: move broker metric history from JSON files to SQLite so dashboard charts and operational reports survive application restarts.

### Scope

- Persist 3-minute broker metric ticks in SQLite.
- Persist runtime state for max concurrent tracking.
- Persist daily broker rollups for reporting.
- Keep API contracts stable for existing dashboard consumers.
- Maintain temporary compatibility with legacy JSON historical files only as bootstrap input.

### Tables

#### `broker_metric_ticks`

- One row per persisted broker tick.
- Source: broker `$SYS` snapshot plus monitor-derived latency and client counters.

Fields:

- `id`
- `ts` unique UTC timestamp
- `bytes_received_rate`
- `bytes_sent_rate`
- `messages_received_delta`
- `messages_sent_delta`
- `connected_clients`
- `disconnected_clients`
- `active_sessions`
- `max_concurrent`
- `total_subscriptions`
- `retained_messages`
- `messages_inflight`
- `latency_ms`
- `cpu_pct` nullable
- `memory_bytes` nullable
- `memory_pct` nullable

#### `broker_runtime_state`

- Single-row state used for operational continuity.

Fields:

- `id=1`
- `last_tick_ts`
- `last_broker_uptime`
- `current_max_concurrent`
- `lifetime_max_concurrent`
- `last_messages_received_total`
- `last_messages_sent_total`

#### `broker_daily_summary`

- One row per UTC day.

Fields:

- `day` unique UTC date
- `peak_connected_clients`
- `peak_active_sessions`
- `peak_max_concurrent`
- `total_messages_received`
- `total_messages_sent`
- `bytes_received_rate_sum`
- `bytes_sent_rate_sum`
- `latency_samples`
- `latency_sum`

### Checklist

- [x] Define phase-1 schema in backend models.
- [x] Create SQLite storage service for broker history.
- [x] Bootstrap legacy JSON ticks into SQLite when the new tables are empty.
- [x] Switch monitor byte/message period queries to SQLite.
- [x] Persist max concurrent and daily broker rollups in SQLite.
- [x] Replace remaining legacy JSON-backed counters still not migrated.
- [x] Expose daily rollup API for reporting.
- [x] Add cleanup/retention job for raw ticks older than policy.

### Notes

- Topic topology and top subscribed topics are intentionally not part of Phase 1. They need per-topic bucket tables and belong to Phase 2.
- Existing dashboard payloads stay stable during the migration.

---

## Phase 2 - Topic History and Queryable Topology

Objective: persist topic-level history so `Topic Topology` and `Top Subscribed Topics` can be queried by window instead of only since process start.

### Proposed Tables

#### `topic_registry`

- `id`
- `topic` unique
- `first_seen_at`
- `last_seen_at`
- `kind`

#### `topic_publish_buckets`

- `bucket_start`
- `bucket_minutes`
- `topic_id`
- `publish_count`
- `bytes_sum`

#### `topic_subscribe_buckets`

- `bucket_start`
- `bucket_minutes`
- `topic_id`
- `subscribe_count`

### Checklist

- [x] Add topic catalog and bucket tables.
- [x] Persist publish buckets from observed broker traffic.
- [x] Persist subscribe buckets from clientlogs parser.
- [x] Redefine dashboard topic charts as time-window queries.
- [x] Add retention and aggregation strategy.

### Phase 2 Progress Notes

- Publish and subscribe history now persist into SQLite via topic buckets.
- `Topic Topology` and `Top Subscribed Topics` can read from SQLite with a period window instead of process-only memory.
- Startup replay still hydrates in-memory views only; historical backfill from old broker logs is not implemented yet.

---

## Phase 3 - Client Activity History

Objective: persist per-client operational history for up to 30 days.

### Proposed Tables

#### `client_registry`

- `username` primary key
- `textname`
- `disabled`
- `created_at`
- `deleted_at` nullable
- `last_dynsec_sync_at`

#### `client_session_events`

- `id`
- `username`
- `client_id`
- `event_ts`
- `event_type`
- `disconnect_kind`
- `reason_code`
- `ip_address`
- `port`
- `protocol_level`
- `clean_session`
- `keep_alive`

#### `client_topic_events`

- `id`
- `username`
- `client_id`
- `event_ts`
- `event_type`
- `topic`
- `qos`
- `payload_bytes` nullable
- `retained` nullable

#### `client_subscription_state`

- `username`
- `topic`
- `qos`
- `first_seen_at`
- `last_seen_at`
- `is_active`
- `source`

#### `client_daily_summary`

- `username`
- `day`
- `connects`
- `disconnects_graceful`
- `disconnects_ungraceful`
- `auth_failures`
- `publishes`
- `subscribes`
- `distinct_publish_topics`
- `distinct_subscribe_topics`

### Checklist

- [x] Synchronize `client_registry` with DynSec create/update/delete flows.
- [ ] Add periodic reconciliation against `dynamic-security.json` changes outside the API.
- [x] Persist connect/disconnect/auth-failure events.
- [x] Classify disconnections as graceful vs ungraceful when possible.
- [x] Persist subscribe/publish topic events.
- [x] Add 30-day retention for raw client events.
- [x] Add client detail views and filtered audit endpoints.

### Notes

- Do not precreate per-client event structures at client creation time.
- Create or update only the registry entry on DynSec changes.
- Persist activity only when events are actually observed.

### Phase 3 Progress Notes

- Client activity is now persisted in SQLite tables for registry, session events, topic events, observed subscriptions and daily summaries.
- DynSec create/enable/disable/delete operations synchronize the persistent client registry.
- A new audit endpoint is available at `/api/v1/clientlogs/activity/{username}`.
- Periodic full reconciliation against external `dynamic-security.json` changes is still pending.

---

## Phase 4 - Audit and Reporting

Objective: expose queryable incident and compliance views over persisted broker and client history.

### Deliverables

- [x] Daily and weekly broker reports.
- [x] Per-client activity timeline.
- [x] Filters for ungraceful disconnects, auth failures and reconnect loops.
- [x] Export endpoints for CSV or JSON.
- [x] Data retention and purge tooling.

### Phase 4 Progress Notes

- Reporting API available under `/api/v1/reports` with daily and weekly broker rollups.
- Per-client merged timeline is available at `/api/v1/reports/clients/{username}/timeline`.
- Incident queries support ungraceful disconnects, auth failures and reconnect-loop detection.
- CSV and JSON exports are available for broker reports and client activity timelines.
- Retention status and manual purge tooling are available under `/api/v1/reports/retention/*`.

---

## Operational Questions

- Admin/internal clients are excluded from workload counters unless explicitly required by UI semantics.
- Graceful and ungraceful disconnects should both be stored; UI can filter ungraceful by default.
- Topic permissions from DynSec and observed topic activity must remain separate concepts.

---

## Implementation Notes

- Phase 1 can be executed without Alembic if new tables are additive.
- If later refactors require altering existing tables, introduce explicit migrations.
- For Windows inspection tools, prefer opening the SQLite file directly instead of parsing JSON runtime files.