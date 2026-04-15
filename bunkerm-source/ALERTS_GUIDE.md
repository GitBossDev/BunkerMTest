# BunkerM Alerts Guide

BunkerM includes a built-in alert system focused exclusively on **broker health and connectivity**. Alerts are surfaced in the **Alerts** section of the dashboard and via the bell icon (🔔) in the header.

Data interpretation and anomaly detection (unusual sensor values, trend changes, etc.) are intentionally outside the scope of this module — those concerns are handled by an external analytics application.

---

## How Alerts Appear

There are two entry points:

1. **Bell icon (🔔) in the header** — shows a badge with the count of active unacknowledged alerts. Click it to open the quick panel.
2. **Alerts page** (`/ai/monitoring`) — full view with two sections:
   - **Active Alerts** — alerts currently in effect, with an Acknowledge button per alert.
   - **Alert History** — the last 200 alert events (raised, acknowledged, or auto-cleared), filterable by severity and type, with CSV export.

**Role visibility:**

| Section | admin | user |
|---|---|---|
| Active alerts | ✅ visible | ❌ hidden |
| Alert history | ✅ visible | ❌ hidden |

---

## External Notifications (Email)

Besides dashboard notifications, BunkerM can now send external notifications when a new alert becomes active. This is useful when no operator is currently viewing the UI.

- Trigger moment: only when an alert is first raised with status `active`.
- Repeated polls do not resend the same alert while it stays active.
- Delivery is asynchronous (non-blocking) and does not stop alert evaluation if a provider fails.

### 1) Global switch

```env
ALERT_NOTIFY_ENABLED=true
```

### 2) Email via SMTP

```env
ALERT_NOTIFY_EMAIL_ENABLED=true
ALERT_NOTIFY_EMAIL_TO=ops@example.com,oncall@example.com
ALERT_NOTIFY_EMAIL_FROM=alerts@bunkerm.local
ALERT_NOTIFY_SMTP_HOST=smtp.example.com
ALERT_NOTIFY_SMTP_PORT=587
ALERT_NOTIFY_SMTP_USERNAME=alerts-user
ALERT_NOTIFY_SMTP_PASSWORD=replace_me
ALERT_NOTIFY_SMTP_STARTTLS=true
ALERT_NOTIFY_SMTP_SSL=false
```

After setting variables, redeploy BunkerM backend.

### Testing Email Delivery

To validate delivery safely before using production SMTP:

1. Point SMTP to a sandbox server (for example MailHog/Mailpit/smtp4dev).
2. Trigger one alert condition (for example set `ALERT_CLIENT_CAPACITY_PCT=1` temporarily so capacity alert fires quickly).
3. Verify these backend logs appear:
  - `Alert email sent to N recipient(s)`
  - No `Failed to send alert email notification` errors
4. Check the sandbox inbox and confirm subject format: `[BunkerM][SEVERITY] <title>`.
5. Restore normal thresholds after the test.

---

## Alert Types

The monitor service evaluates alert conditions every ~30 seconds (each stats poll). All alerts are stored in memory — they are reset when the monitor service restarts.

| Alert | Title | Severity | Trigger | Default threshold | Env variable(s) |
|---|---|---|---|---|---|
| `broker_down` | Broker Unreachable | 🔴 critical | No `$SYS` data for N consecutive polls | 3 polls | `ALERT_BROKER_DOWN_GRACE_POLLS` |
| `client_capacity` | Client Capacity Warning | 🟠 high | Connected clients ≥ X% of `max_connections` | 80% | `ALERT_CLIENT_CAPACITY_PCT`, `ALERT_CLIENT_MAX_DEFAULT` |
| `reconnect_loop` | Client Reconnect Loop | 🟠 high | One client connects N times in a time window | 5 times / 60 s | `ALERT_RECONNECT_LOOP_COUNT`, `ALERT_RECONNECT_LOOP_WINDOW_S` |
| `auth_failure` | Authentication Failures | 🟠 high | Mosquitto auth failures exceed threshold in window | 5 failures / 60 s | `ALERT_AUTH_FAIL_COUNT`, `ALERT_AUTH_FAIL_WINDOW_S` |
| `device_silent` | Device Silent | 🟠 high | A watched topic has not published within its configured interval | per-rule in `silent_watchlist.json` | `ALERT_WATCHLIST_PATH` |

### Changing Thresholds

Thresholds for the first four alert types are environment variables in `docker-compose.yml`. To override, add them to a `.env` file next to `docker-compose.yml`:

```env
ALERT_BROKER_DOWN_GRACE_POLLS=5
ALERT_CLIENT_CAPACITY_PCT=90
ALERT_RECONNECT_LOOP_COUNT=10
ALERT_AUTH_FAIL_COUNT=3
```

Then redeploy: `.\deploy.bat patch-backend`

---

## Acknowledge Cooldown

When you acknowledge an alert, it is removed from Active Alerts and a **cooldown period** begins. The same alert type will not re-fire during the cooldown, even if the condition is still true. This prevents the alert from immediately reappearing after you dismiss it.

Default cooldown: **15 minutes**

To change it, set `ALERT_COOLDOWN_MINUTES` in your `.env` file:

```env
ALERT_COOLDOWN_MINUTES=30
```

---

## Alert History

Every alert event — whether raised, acknowledged by a user, or automatically cleared by the system — is appended to an in-memory history (maximum 200 records). The history survives stats-poll cycles but is reset when the monitor service restarts.

| Status | Meaning |
|---|---|
| `active` | Alert is currently in effect |
| `acknowledged` | An operator dismissed the alert; cooldown is running |
| `cleared` | The condition resolved itself (e.g. broker came back online) |

The history can be downloaded as a CSV from the Alerts page.

---

## Device Silent Alert

This alert detects topics that have gone silent — i.e., have not published a message within an expected time window. It is designed for **any industry or deployment**: you define which topics to monitor and at what interval.

### How it works

The monitor service tracks the **timestamp of the last received message per topic** (regardless of whether the device is currently connected). When a topic exceeds its configured silence threshold, an alert is raised. When messages resume, the alert is automatically cleared.

**Connection state is deliberately not used.** A low-power device that connects → publishes → disconnects in a few seconds would appear "disconnected" most of the time — yet it is working correctly. The only reliable signal is the last message timestamp.

### Configuring the watchlist

Edit the file at:

```
backend/app/monitor/silent_watchlist.json
```

(This maps to `/app/monitor/silent_watchlist.json` inside the container.)

The file contains a JSON array of rules. Each rule has:

| Field | Required | Description |
|---|---|---|
| `pattern` | ✅ | MQTT topic pattern. Supports `+` (single level wildcard) and `#` (multi-level wildcard, must be last) |
| `max_silence_secs` | ✅ | Number of seconds without a message before the alert fires |
| `label` | optional | Human-readable name shown in the alert description |

**Example:**

```json
[
  {
    "pattern": "sensors/+/temperature",
    "max_silence_secs": 600,
    "label": "Temperature sensors"
  },
  {
    "pattern": "devices/+/heartbeat",
    "max_silence_secs": 300,
    "label": "Device heartbeats"
  },
  {
    "pattern": "factory/line1/#",
    "max_silence_secs": 120,
    "label": "Production line 1"
  }
]
```

A copy of this example is saved at `backend/app/monitor/silent_watchlist.example.json`.

**MQTT wildcard semantics:**

| Wildcard | Matches | Example pattern | Matches | Does NOT match |
|---|---|---|---|---|
| `+` | Exactly one topic level (no `/`) | `sensors/+/temp` | `sensors/room1/temp` | `sensors/room1/zone2/temp` |
| `#` | Zero or more topic levels, placed at the end | `factory/#` | `factory/line1`, `factory/line1/motor` | `other/factory/line1` |

One rule using `+` covers all devices of the same type without needing per-device configuration.

### Limitations

| Limitation | Detail |
|---|---|
| **Requires at least one message to have been received** | If a topic has never published since the monitor service started, no alert is raised (the system cannot distinguish "device silent" from "topic never existed"). |
| **In-memory only** | The last-seen timestamps are held in RAM. A service restart resets them — the clock only starts counting from the first message received after startup. |
| **Interval must be known** | The system cannot automatically learn the expected publication interval. The operator must configure `max_silence_secs` based on knowledge of the device or system design. |
| **Topic structure must be consistent** | Wildcards only work if devices publish to predictable topic paths (e.g. `sensors/{id}/temperature`). Devices that publish to arbitrary topics cannot be grouped into a single rule. |

### Choosing the right `max_silence_secs`

| Device type | Recommendation |
|---|---|
| Periodic sensor (every N seconds) | `max_silence_secs = N × 2` — allows one missed cycle before alerting |
| Periodic sensor (every N minutes) | `max_silence_secs = N × 2 × 60` |
| Event-driven (door sensor, alarm) | Use heartbeat/keepalive topic if available; otherwise set a generous window (e.g. 24–48 h as a "still alive" signal) |
| Command-response devices | Not suitable for this alert — use `reconnect_loop` or `auth_failure` to detect connectivity problems instead |

---

## Architecture Overview

```
Mosquitto (broker)
  ├── $SYS/# topics (broker metrics, rates, client counts)
  └── User topics (last-seen tracked by TopicStore)
         │
         ▼
Monitor Service (port 1001)   ← backend/app/monitor/main.py
  ├── MQTTStats — collects $SYS metrics
  ├── TopicStore — tracks last message per user topic
  ├── AlertEngine — evaluates conditions on every stats poll
  │     ├── broker_down
  │     ├── client_capacity
  │     ├── reconnect_loop   (triggered by clientlogs log parsing)
  │     ├── auth_failure     (triggered by clientlogs log parsing)
  │     └── device_silent    (driven by TopicStore + silent_watchlist.json)
  └── API endpoints
        GET  /api/v1/alerts/broker
        GET  /api/v1/alerts/broker/history
        POST /api/v1/alerts/broker/{id}/acknowledge

Next.js Frontend (port 3000 / 2000 via nginx)
  ├── monitorApi.getBrokerAlerts()    — active alerts
  ├── monitorApi.getAlertHistory()    — history (last 200)
  ├── monitorApi.acknowledgeAlert()   — acknowledge + start cooldown
  └── Alerts page (/ai/monitoring)
```

---

## Disabling Specific Alerts

To effectively disable an alert you don't need, set its threshold to an unreachable value:

```env
# Disable client capacity alert
ALERT_CLIENT_CAPACITY_PCT=101

# Disable auth failure alert
ALERT_AUTH_FAIL_COUNT=999999

# Disable reconnect loop alert
ALERT_RECONNECT_LOOP_COUNT=999999
```

To disable device silent alerts, leave `silent_watchlist.json` as an empty array `[]`.

---

## Troubleshooting

**Bell icon shows no alerts even though the broker is down**  
→ The broker_down alert fires only after `ALERT_BROKER_DOWN_GRACE_POLLS` consecutive missed polls. The first failure is intentionally ignored to avoid false positives during restarts.

**Device silent alert never fires even though the device stopped publishing**  
→ Check that the topic pattern in `silent_watchlist.json` matches the actual topics using the MQTT Explorer. The pattern is an exact match with wildcards — a pattern like `sensors/+/temp` will NOT match `sensors/greenhouse/temperature`.

**Device silent alert fires immediately after the monitor service restarts**  
→ Expected. The last-seen timestamps are in memory. After a restart, the clock starts from zero for each topic. The alert will auto-clear once the first message is received from that topic.

**Alert disappeared and then reappeared before the cooldown expired**  
→ If the alert condition resolves itself (e.g. broker comes back online, device publishes again), the alert is auto-cleared regardless of cooldown. Cooldown only applies to re-raising an alert after a user acknowledgement.

**Cannot see the Alerts page**  
→ The Alerts page is only visible to users with the `admin` role. Log in with an admin account.
