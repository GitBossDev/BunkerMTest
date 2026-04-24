# MQTT Publish Event Capture and Storage Analysis

## Overview
MQTT publish events are captured and stored through **two independent paths**:
1. **Log-based path**: Parsing Mosquitto debug logs
2. **Broker-observed path**: Direct MQTT subscription monitoring

Both paths ultimately call `persist_mqtt_event()` to store events in the database.

---

## 1. Publish Event Detection & Creation

### Path 1: Log-Based Detection (Primary)
**Location**: [services/clientlogs_service.py](services/clientlogs_service.py#L421-L456)

**Method**: `MQTTMonitor.parse_publish_log()`

**Regex Pattern Matched**:
```
<timestamp>: Received PUBLISH from <client_id> (d<d>, q<qos>, r<retained>, m<msgid>, '<topic>', ... (<bytes> bytes))
```

**Example Log Line**:
```
1713456789: Received PUBLISH from greenhouse-publisher-1 (d0, q1, r0, m42, 'plant/tank1/level', ... (10 bytes))
```

**Code Section** (lines 421-456):
```python
def parse_publish_log(self, log_line: str) -> Optional[MQTTEvent]:
    pattern = (
        _TS_CAPTURE
        + r": Received PUBLISH from (\S+)"
        r" \(d\d, q(\d), r\d, m\d+, '([^']+)', \.\.\. \((\d+) bytes\)\)"
    )
    m = re.match(pattern, log_line)
    if not m:
        return None
    ts, client_id, qos_str, topic, size_str = m.groups()
    # ... event creation and filtering (see section 4)
    return MQTTEvent(
        id=str(uuid.uuid4()),
        timestamp=_ts_to_iso(ts),
        event_type="Publish",
        client_id=client_id,
        details=f"Published to {topic} ({size_str} B, QoS {qos_str})",
        status="info",
        protocol_level=protocol_level,
        clean_session=clean,
        keep_alive=keep_alive,
        username=username,
        ip_address=ip,
        port=port,
        topic=topic,
        qos=int(qos_str),
        payload_bytes=int(size_str),
    )
```

### Path 2: Broker-Observed Detection (Secondary)
**Location**: [clientlogs/main.py](clientlogs/main.py#L706-L745)

**Method**: `monitor_mqtt_publishes()` thread → `_on_message()` callback

**MQTT Subscription**: Subscribes to `#` (all topics) as the admin user

**Code Section** (lines 706-745):
```python
def _on_message(client, userdata, message):
    # Skip internal broker topics ($SYS/...) and platform-internal topics
    if any(message.topic.startswith(p) for p in _INTERNAL_TOPIC_PREFIXES):
        return

    now_ts = time.time()
    key = message.topic
    if now_ts - mqtt_monitor._last_publish_ts.get(key, 0) < _PUBLISH_DEDUP_SECONDS:
        return
    mqtt_monitor._last_publish_ts[key] = now_ts

    event = MQTTEvent(
        id=str(uuid.uuid4()),
        timestamp=datetime.now(tz=timezone.utc).isoformat(),
        event_type="Publish",
        client_id="(broker-observed)",
        details=f"Published to {message.topic} ({len(message.payload)} B, QoS {message.qos})",
        status="info",
        protocol_level="MQTT v3.1.1",
        clean_session=True,
        keep_alive=0,
        username="(broker-observed)",
        ip_address="",
        port=0,
        topic=message.topic,
        qos=message.qos,
    )
    mqtt_monitor.events.append(event)
    try:
        _persist_mqtt_event_from_service(event)
    except Exception as exc:
        print(f"Failed to persist event to database: {exc}")
```

**Key Difference**: Broker-observed events do NOT capture `payload_bytes` or `retained` flag (see Issue #1 below).

---

## 2. persist_mqtt_event() Call Chain

### Call Locations

**Location 1**: [clientlogs_service.py](clientlogs_service.py#L496-L505)
```python
# In process_line() method - Log-based path
event = self.parse_publish_log(line)
if event is not None:
    if not replay:
        client_activity_storage.record_event(event)
    if not replay:
        self.events.append(event)
        persist_mqtt_event(event)  # ← CALLED HERE
    return
```

**Location 2**: [clientlogs/main.py](clientlogs/main.py#L734)
```python
# In _on_message() callback - Broker-observed path
mqtt_monitor.events.append(event)
try:
    _persist_mqtt_event_from_service(event)  # ← CALLED HERE (alias for persist_mqtt_event)
except Exception as exc:
    print(f"Failed to persist event to database: {exc}")
```

### Function Definition
**Location**: [services/clientlogs_service.py](services/clientlogs_service.py#L132-L153)

```python
def persist_mqtt_event(event: MQTTEvent) -> None:
    """Guarda un evento MQTT en la base de datos (async-safe)."""
    try:
        session_factory = _get_db_session_factory()
        with session_scope(session_factory) as session:
            db_event = ClientMQTTEvent(
                event_id=event.id,
                timestamp=datetime.fromisoformat(event.timestamp.replace('Z', '+00:00')) if isinstance(event.timestamp, str) else event.timestamp,
                event_type=event.event_type,
                client_id=event.client_id,
                username=event.username,
                ip_address=event.ip_address,
                port=event.port,
                protocol_level=event.protocol_level,
                clean_session=event.clean_session,
                keep_alive=event.keep_alive,
                status=event.status,
                details=event.details,
                topic=event.topic,
                qos=event.qos,
                payload_bytes=event.payload_bytes,
                retained=event.retained,
                disconnect_kind=event.disconnect_kind,
                reason_code=event.reason_code,
            )
            session.add(db_event)
            session.commit()
    except Exception as exc:
        logger.warning("Failed to persist MQTT event to database: %s", exc)
```

---

## 3. Publish Event Structure

### MQTTEvent Model
**Location**: [clientlogs/main.py](clientlogs/main.py#L73-L86) and [services/clientlogs_service.py](services/clientlogs_service.py#L91-L113)

```python
class MQTTEvent(BaseModel):
    id: str                                    # UUID - unique event identifier
    timestamp: str                             # ISO 8601 UTC timestamp
    event_type: str                           # Always "Publish" for publish events
    client_id: str                            # Publisher's client ID (or "(broker-observed)" for Path 2)
    details: str                              # Human-readable description
    status: str                               # Always "info" for publish events
    protocol_level: str                       # MQTT version (e.g., "MQTT v3.1.1")
    clean_session: bool                       # Clean session flag from connection
    keep_alive: int                           # Keep-alive timeout from connection
    username: str                             # Publisher's username (or "(broker-observed)")
    ip_address: str                           # Publisher's IP address (empty for broker-observed)
    port: int                                 # Publisher's port (0 for broker-observed)
    
    # Publish-specific fields
    topic: Optional[str]                      # The topic published to
    qos: Optional[int]                        # Quality of Service (0, 1, or 2)
    payload_bytes: Optional[int]              # Size of payload in bytes
    retained: Optional[bool]                  # Retained flag (NULL for broker-observed events!)
    
    # Other event types
    disconnect_kind: Optional[str]            # NULL for publish events
    reason_code: Optional[str]                # NULL for publish events
```

### Database Persistence Model
**Location**: [models/orm.py](models/orm.py#L379-L405)

```python
class ClientMQTTEvent(Base):
    """Append-only unified event log for all MQTT client events"""
    __tablename__ = "client_mqtt_events"

    id: Mapped[int]                           # Auto-increment PK
    event_id: Mapped[str]                     # UUID from MQTTEvent.id (UNIQUE)
    timestamp: Mapped[datetime]               # Indexed
    event_type: Mapped[str]                   # Indexed ("Publish")
    client_id: Mapped[str]                    # Indexed
    username: Mapped[str | None]              # Indexed
    ip_address: Mapped[str | None]
    port: Mapped[int | None]
    protocol_level: Mapped[str | None]
    clean_session: Mapped[bool | None]
    keep_alive: Mapped[int | None]
    status: Mapped[str]
    details: Mapped[Text]
    
    # Publish-specific
    topic: Mapped[str | None]                 # Indexed
    qos: Mapped[int | None]
    payload_bytes: Mapped[int | None]         # ← CAN BE NULL
    retained: Mapped[bool | None]             # ← CAN BE NULL
    
    # Other event types
    disconnect_kind: Mapped[str | None]
    reason_code: Mapped[str | None]
    created_at: Mapped[datetime]
```

---

## 4. Filtering & Conditions Preventing Event Persistence

### 4.1 Log-Based Path Filters

**Filter 1: Internal Topic Prefixes** (Line 433)
```python
if any(topic.startswith(p) for p in _INTERNAL_TOPIC_PREFIXES):
    return None
```
**Impact**: Events for topics starting with `$` or `bunkerm/monitor/` are **DROPPED** before event creation
- `$SYS/*` (Mosquitto system topics)
- `bunkerm/monitor/*` (Platform internal monitoring)

**Filter 2: Admin User Detection** (Line 435)
```python
username, protocol_level, ip, port, clean, keep_alive = self._get_client_info(client_id)
if self._is_admin(username):
    return None
```
**Impact**: Publish events from admin users are **DROPPED** before event creation
- Username matches `MOSQUITTO_ADMIN_USERNAME` environment variable (default: "admin")

**Filter 3: Publish Deduplication by Topic** (Lines 437-440)
```python
key = topic
now_ts = event_ts
if key in self._last_publish_ts and now_ts - self._last_publish_ts[key] < _PUBLISH_DEDUP_SECONDS:
    return None
self._last_publish_ts[key] = now_ts
```
**Impact**: Only one publish event per unique topic is persisted per **60-second window**
- Duplicates are **DROPPED** silently
- Deduplication window: `_PUBLISH_DEDUP_SECONDS = 60`
- Key: Topic name (not client_id + topic)

**Filter 4: Replay Mode Flag** (Line 502-507)
```python
if not replay:
    client_activity_storage.record_event(event)
if not replay:
    self.events.append(event)
    persist_mqtt_event(event)  # ← Only called if not replay
```
**Impact**: During startup replay of historical logs, publish events are **NOT PERSISTED** to database
- Allows fresh history on service restart
- Only connection state is rebuilt during replay
- Live publish events are persisted normally after replay completes

**Filter 5: Log Line Pattern Mismatch** (Lines 425-428)
```python
pattern = (
    _TS_CAPTURE
    + r": Received PUBLISH from (\S+)"
    r" \(d\d, q(\d), r\d, m\d+, '([^']+)', \.\.\. \((\d+) bytes\)\)"
)
m = re.match(pattern, log_line)
if not m:
    return None
```
**Impact**: Log lines that don't match this exact pattern are **SKIPPED**
- Wrong format or truncated lines are ignored
- Missing payload size information results in no match

### 4.2 Broker-Observed Path Filters

**Filter 1: Internal Topic Prefixes** (Lines 720-722)
```python
if any(message.topic.startswith(p) for p in _INTERNAL_TOPIC_PREFIXES):
    return
```
**Impact**: Events for `$*` and `bunkerm/monitor/*` are **DROPPED**

**Filter 2: Publish Deduplication by Topic** (Lines 724-727)
```python
now_ts = time.time()
key = message.topic
if now_ts - mqtt_monitor._last_publish_ts.get(key, 0) < _PUBLISH_DEDUP_SECONDS:
    return
mqtt_monitor._last_publish_ts[key] = now_ts
```
**Impact**: Only one publish event per topic per **60-second window** (shared deduplication state with log-based path)

**Filter 3: Exception Handling** (Lines 746-748)
```python
try:
    _persist_mqtt_event_from_service(event)
except Exception as exc:
    print(f"Failed to persist event to database: {exc}")
```
**Impact**: Database errors are caught and logged to stdout, not re-raised
- Event may be added to `mqtt_monitor.events` but fail to persist to database silently

### 4.3 Activity Storage Recording Filters
**Location**: [clientlogs/sqlalchemy_activity_storage.py](clientlogs/sqlalchemy_activity_storage.py#L151)

```python
if event_type in ("Subscribe", "Publish") and getattr(event, "topic", None):
    session.add(
        ClientTopicEvent(
            username=username,
            client_id=client_id,
            event_ts=event_ts,
            event_type=event_type.lower(),
            topic=getattr(event, "topic", ""),
            qos=getattr(event, "qos", None),
            payload_bytes=getattr(event, "payload_bytes", None),
```

**Filter**: Publish events are only recorded to activity storage if they have a non-empty `topic` field

---

## 5. Known Issues & Limitations

### Issue #1: Retained Flag Not Captured in Broker-Observed Events
**Severity**: MEDIUM

**Description**: The broker-observed path (_on_message callback) does NOT extract or set the `retained` flag.

**Current Code** (lines 718-729):
```python
event = MQTTEvent(
    # ...
    qos=message.qos,
    # retained field is missing! defaults to None
)
```

**Impact**: 
- `payload_bytes` is NULL in database for broker-observed events (uses `len(message.payload)` in details only)
- `retained` is NULL in database for broker-observed events (not extracted from paho mqtt message object)
- Log-based events DO capture these fields correctly

**Available in paho mqtt message object**: 
```python
message.retain  # The retained flag value
```

**Fix**: Should add `retained=message.retain,` to the MQTTEvent creation

### Issue #2: Retained Flag Not Extracted from Mosquitto Log Pattern
**Severity**: MEDIUM

**Description**: The regex pattern matches `r\d` (retained flag in log) but doesn't capture it.

**Current Pattern** (line 424):
```python
r" \(d\d, q(\d), r\d, m\d+, '([^']+)', \.\.\. \((\d+) bytes\)\)"
#              ↑        ↑ - not captured
```

**Log Example**:
```
1713456789: Received PUBLISH from client1 (d0, q1, r0, m42, 'topic', ... (10 bytes))
                                                    ↑↑ - r0 = retained=false
```

**Fix**: Change pattern to capture retained flag: `r(\d)` instead of `r\d`

### Issue #3: Payload Bytes Calculation Difference
**Severity**: LOW

**Description**: 
- **Log-based**: Exact byte count from Mosquitto log (`size_str`)
- **Broker-observed**: Calculated from Python bytes length (`len(message.payload)`)

These may differ if encoding or compression is involved.

### Issue #4: Lost Publisher Identity in Broker-Observed Path
**Severity**: MEDIUM

**Description**: Broker-observed events cannot identify the actual publisher:
- `client_id = "(broker-observed"` - generic marker, not real publisher
- `username = "(broker-observed)"` - generic marker
- `ip_address = ""` - empty
- `port = 0` - placeholder

**Impact**: Cannot track which client published what through this path

**Root Cause**: MQTT subscribers don't receive publisher metadata per MQTT spec
- Log-based path works because Mosquitto logs include client_id
- Only viable fix: Use ACL logs or other broker instrumentation

---

## 6. Summary Table

| Aspect | Log-Based Path | Broker-Observed Path |
|--------|-----------------|----------------------|
| **Detection** | Mosquitto debug logs | MQTT subscription (#) |
| **Publisher ID** | ✅ Real client_id | ❌ "(broker-observed)" |
| **Username** | ✅ Real username | ❌ "(broker-observed)" |
| **Topic** | ✅ Captured | ✅ Captured |
| **QoS** | ✅ Captured | ✅ Captured |
| **Payload Bytes** | ✅ From Mosquitto | ⚠️ Calculated (may differ) |
| **Retained Flag** | ❌ Not extracted* | ❌ Not extracted* |
| **IP Address** | ✅ Captured | ❌ Empty |
| **Port** | ✅ Captured | ❌ 0 |
| **Admin Filtered** | ✅ Excluded | ❓ Included (subscribed as admin) |
| **Deduplication** | ✅ 60-sec per topic | ✅ 60-sec per topic (shared state) |
| **Replay Mode** | ❌ Skipped during startup | ❌ N/A |
| **persist_mqtt_event()** | ✅ Called (line 505) | ✅ Called (line 734) |

\* = Missing implementation, stored as NULL in database

---

## 7. Call Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    MQTT Publish Events                          │
└─────────────────────────────────────────────────────────────────┘

     PATH 1: LOG-BASED (Primary)              PATH 2: BROKER-OBSERVED (Secondary)
     
     ┌──────────────────────────────┐         ┌──────────────────────────────┐
     │ Mosquitto Debug Log          │         │ MQTT Subscription (#)        │
     │ "...: Received PUBLISH from" │         │ Subscribe as admin user      │
     └──────────────┬───────────────┘         └──────────────┬───────────────┘
                    │                                        │
                    ▼                                        ▼
     ┌──────────────────────────────┐         ┌──────────────────────────────┐
     │ monitor_mosquitto_logs()     │         │ monitor_mqtt_publishes()     │
     │ (Thread: tail -f log file)   │         │ (Thread: paho mqtt loop)     │
     │ Line by line processing      │         │ _on_message callback         │
     └──────────────┬───────────────┘         └──────────────┬───────────────┘
                    │                                        │
                    ▼                                        ▼
     ┌──────────────────────────────┐         ┌──────────────────────────────┐
     │ MQTTMonitor.process_line()   │         │ Create MQTTEvent            │
     │ - Skip internal log lines    │         │ - client_id="(broker-...)"  │
     │ - Call parse_publish_log()   │         │ - username="(broker-...)"   │
     │   (if not recognized as other)        │ - payload_bytes=len(payload)│
     └──────────────┬───────────────┘         │ - NO retained flag          │
                    │                         └──────────────┬───────────────┘
                    ▼                                        │
     ┌──────────────────────────────┐                       │
     │ parse_publish_log()          │                       │
     │ - Regex match log pattern    │                       │
     │ - Extract: ts, client, qos,  │                       │
     │   topic, payload_bytes       │                       │
     │ - Filter: internal topics    │                       │
     │ - Filter: admin users        │                       │
     │ - Filter: dedup (60s/topic)  │                       │
     │ - Create MQTTEvent           │                       │
     │   - retained = NULL (BUG!)   │                       │
     └──────────────┬───────────────┘                       │
                    │                                        │
                    ▼                                        ▼
     ┌──────────────────────────────┐         ┌──────────────────────────────┐
     │ Filter: replay mode?         │         │ Filter: replay mode?         │
     │ if not replay: continue      │         │ N/A (only live)              │
     │ if replay: return            │         │                              │
     └──────────────┬───────────────┘         └──────────────┬───────────────┘
                    │                                        │
                    ▼                                        ▼
     ┌──────────────────────────────┐         ┌──────────────────────────────┐
     │ client_activity_storage      │◄────────┤ mqtt_monitor.events.append() │
     │ .record_event()              │         │                              │
     └──────────────┬───────────────┘         └──────────────┬───────────────┘
                    │                                        │
                    ▼                                        ▼
     ┌──────────────────────────────────────────────────────────────────────┐
     │          persist_mqtt_event(event)  [BOTH PATHS]                    │
     │                                                                      │
     │  - Extract MQTTEvent fields                                          │
     │  - Create ClientMQTTEvent ORM object                                │
     │  - session.add() + commit()                                          │
     │                                                                      │
     │  Stores to: client_mqtt_events table in ControlPlane database      │
     │  Fields: id, event_id, timestamp, event_type, client_id,           │
     │          username, ip_address, port, protocol_level,               │
     │          clean_session, keep_alive, status, details,               │
     │          topic, qos, payload_bytes, retained, created_at           │
     └──────────────┬───────────────────────────────────────────────────────┘
                    │
                    ▼
     ┌──────────────────────────────────────────────────────────────────────┐
     │                  Database: ClientMQTTEvent                           │
     │                                                                      │
     │  event_type = "Publish"                                             │
     │  topic = captured topic name                                        │
     │  qos = 0|1|2                                                        │
     │  payload_bytes = size (or NULL if broker-observed)                  │
     │  retained = bool|NULL (NULL if not extracted)                       │
     │  client_id = real_id (or "(broker-observed)")                      │
     │  username = real_user (or "(broker-observed)")                      │
     │  ip_address = source_ip (or "" if broker-observed)                  │
     └──────────────────────────────────────────────────────────────────────┘
```

---

## 8. Verification Queries

To verify publish event storage:

```sql
-- Count publish events by path
SELECT 
    CASE 
        WHEN username = '(broker-observed)' THEN 'Broker-Observed'
        ELSE 'Log-Based'
    END as path,
    COUNT(*) as event_count,
    COUNT(DISTINCT topic) as distinct_topics,
    COUNT(DISTINCT client_id) as distinct_publishers
FROM client_mqtt_events
WHERE event_type = 'Publish'
GROUP BY path;

-- Check for NULL retained flags
SELECT 
    COUNT(*) as publish_events,
    SUM(CASE WHEN retained IS NULL THEN 1 ELSE 0 END) as null_retained_count,
    ROUND(100.0 * SUM(CASE WHEN retained IS NULL THEN 1 ELSE 0 END) / COUNT(*), 2) as null_percentage
FROM client_mqtt_events
WHERE event_type = 'Publish';

-- Check for NULL payload_bytes
SELECT 
    COUNT(*) as publish_events,
    SUM(CASE WHEN payload_bytes IS NULL THEN 1 ELSE 0 END) as null_payload_count,
    ROUND(100.0 * SUM(CASE WHEN payload_bytes IS NULL THEN 1 ELSE 0 END) / COUNT(*), 2) as null_percentage
FROM client_mqtt_events
WHERE event_type = 'Publish';

-- Latest publish events with all fields
SELECT 
    event_id, timestamp, client_id, username, topic, qos, 
    payload_bytes, retained, ip_address, port
FROM client_mqtt_events
WHERE event_type = 'Publish'
ORDER BY timestamp DESC
LIMIT 20;
```
