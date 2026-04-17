// Auth types
export type UserRole = 'admin' | 'user'

export interface User {
  id: string
  email: string
  firstName: string
  lastName: string
  role: UserRole
  createdAt: string
}

export interface UserWithHash extends User {
  passwordHash: string
}

export interface AuthState {
  user: User | null
  isLoading: boolean
}

// MQTT Client types
export interface MqttClient {
  username: string
  disabled?: boolean
  roles?: ClientRole[]
  groups?: ClientGroup[]
}

export interface ClientRole {
  rolename: string
}

export interface ClientGroup {
  groupname: string
  priority?: number
}

// Role types
export interface Role {
  rolename: string
  acls?: ACL[]
  aclCount?: number
}

export interface ACL {
  aclType: string
  topic: string
  priority?: number
  permission: string  // "allow" | "deny"
}

// Group types
export interface Group {
  groupname: string
  roles?: ClientRole[]
  clients?: ClientWithPriority[]
  roleCount?: number
  clientCount?: number
}

export interface RoleSummary {
  rolename: string
  aclCount: number
}

export interface GroupSummary {
  groupname: string
  roleCount: number
  clientCount: number
}

export interface ClientWithPriority {
  username: string
  priority?: number
}

// Monitor/Dashboard types — mirrors the Python monitor API response
export interface MonitorStats {
  total_connected_clients: number
  total_messages_received: string   // formatted string e.g. "1.2K"
  total_subscriptions: number
  retained_messages: number
  messages_history: number[]
  published_history: number[]
  bytes_stats: {
    timestamps: string[]
    bytes_received: number[]
    bytes_sent: number[]
  }
  daily_message_stats: {
    dates: string[]
    counts: number[]
  }
  mqtt_connected?: boolean
  connection_error?: string
  // Extended client info
  clients_total?: number
  clients_maximum?: number
  clients_disconnected?: number
  clients_expired?: number
  subscribed_clients?: number
  publisher_clients?: number
  // Broker info
  broker_version?: string
  broker_uptime?: string
  // Raw message counts
  messages_received_raw?: number
  messages_sent_raw?: number
  // Load rates
  load_msg_rx_1min?: number
  load_msg_tx_1min?: number
  load_bytes_rx_1min?: number
  load_bytes_tx_1min?: number
  load_connections_1min?: number
  // QoS
  messages_inflight?: number
  messages_stored?: number
  messages_store_bytes?: number
  // Latency
  latency_ms?: number
  // Configured connection limit (for gauge scale)
  client_max_connections?: number
  last_broker_sample_at?: string
}

export interface ClientActivitySummary {
  subscribed_clients: number
  publisher_clients: number
  window_seconds: number
}

export interface PeriodBytesData {
  timestamps: string[]
  bytes_received: number[]
  bytes_sent: number[]
}

export interface PeriodMessageData {
  timestamps: string[]
  msg_received: number[]
  msg_sent: number[]
}

export type StatsPeriod = '15m' | '30m' | '1h' | '12h' | '1d' | '7d'

export interface TopicEntry {
  topic: string
  value: string
  count: number
  retained: boolean
  qos: number
  timestamp: string
}

export interface TopologyStats {
  top_topics: TopicEntry[]
  total_distinct_topics: number
  clients_disconnected: number
  clients_expired: number
}

export interface ChartDataPoint {
  time: string
  bytesSent: number
  bytesReceived: number
}

export interface MessageDataPoint {
  date: string
  count: number
}

// Bridge types
export interface AwsBridgeConfig {
  enabled: boolean
  host: string
  port: number
  clientId: string
  topic: string
  caFile?: string
  certFile?: string
  keyFile?: string
}

export interface AzureBridgeConfig {
  enabled: boolean
  connectionString: string
  topic: string
  hubName?: string
}

// API Response types
export interface ApiResponse<T = unknown> {
  data?: T
  error?: string
  message?: string
}

// Frontend API contract types required at build time.
// Keep these tracked so the app compiles even if generated OpenAPI types are absent.
export interface ClientCreate {
  username: string
  password: string
  textname?: string | null
}

export interface ClientSummary {
  username: string
  disabled: boolean
  roles: string[]
  groups: string[]
}

export interface ClientListResponse {
  clients: ClientSummary[]
  total: number
  page: number
  limit: number
  pages: number
}

export interface AwsBridgeCreate {
  endpoint: string
  port?: number
  client_id?: string
  topics: string[]
  cert_file?: string
  key_file?: string
  ca_file?: string
}

export interface AzureBridgeCreate {
  hub_name: string
  device_id: string
  sas_token: string
  topics: string[]
  api_version?: string
}

export interface ListenerConfig {
  port: number
  protocol?: string
  bind_address?: string
}

export interface TlsListenerConfig {
  port: number
  cafile?: string
  certfile?: string
  keyfile?: string
}

export interface MosquittoConfigResponse {
  config: Record<string, unknown>
  listeners: ListenerConfig[]
  max_inflight_messages?: number | null
  max_queued_messages?: number | null
  tls?: TlsListenerConfig | null
}

// MQTT Event (from clientlogs service)
export interface MQTTEvent {
  id: string
  timestamp: string
  event_type: string
  client_id: string
  details: string
  status: string
  protocol_level: string
  clean_session: boolean
  keep_alive: number
  username: string
  ip_address: string
  port: number
  topic?: string   // Subscribe and Publish events
  qos?: number     // Subscribe and Publish events
}

export interface BrokerDailyReportItem {
  day: string
  peak_connected_clients: number
  peak_active_sessions: number
  peak_max_concurrent: number
  total_messages_received: number
  total_messages_sent: number
  bytes_received_rate_sum: number
  bytes_sent_rate_sum: number
  latency_samples: number
  avg_latency_ms: number | null
}

export interface BrokerDailyReportResponse {
  period: { kind: 'daily'; days: number }
  items: BrokerDailyReportItem[]
  totals: {
    days: number
    total_messages_received: number
    total_messages_sent: number
    peak_connected_clients: number
    peak_active_sessions: number
    peak_max_concurrent: number
    bytes_received_rate_sum: number
    bytes_sent_rate_sum: number
    avg_latency_ms: number | null
  }
}

export interface BrokerWeeklyReportItem {
  week_start: string
  week_end: string
  days_covered: number
  peak_connected_clients: number
  peak_active_sessions: number
  peak_max_concurrent: number
  total_messages_received: number
  total_messages_sent: number
  bytes_received_rate_sum: number
  bytes_sent_rate_sum: number
  avg_latency_ms: number | null
}

export interface BrokerWeeklyReportResponse {
  period: { kind: 'weekly'; weeks: number }
  items: BrokerWeeklyReportItem[]
  totals: {
    weeks: number
    total_messages_received: number
    total_messages_sent: number
    peak_connected_clients: number
    peak_active_sessions: number
    peak_max_concurrent: number
  }
}

export interface ClientRegistryEntry {
  username: string
  textname?: string | null
  disabled: boolean
  created_at: string
  deleted_at?: string | null
  last_dynsec_sync_at: string
}

export interface ClientTimelineEvent {
  event_ts: string
  event_type: string
  client_id: string
  ip_address?: string | null
  port?: number | null
  protocol_level?: string | null
  clean_session?: boolean | null
  keep_alive?: number | null
  disconnect_kind?: string | null
  reason_code?: string | null
  topic?: string | null
  qos?: number | null
  payload_bytes?: number | null
  retained?: boolean | null
}

export interface ClientTimelineResponse {
  client: ClientRegistryEntry | null
  filters: {
    days: number
    limit: number
    event_types: string[]
  }
  timeline: ClientTimelineEvent[]
}

export interface ClientIncident {
  incident_type: 'ungraceful_disconnect' | 'auth_failure' | 'reconnect_loop'
  username: string
  client_id: string
  event_ts: string
  details: {
    disconnect_kind?: string | null
    reason_code?: string | null
    ip_address?: string | null
    port?: number | null
    attempts?: number
    start_ts?: string
    end_ts?: string
  }
}

export interface ClientIncidentsResponse {
  filters: {
    days: number
    limit: number
    username?: string | null
    incident_types: string[]
    reconnect_window_minutes: number
    reconnect_threshold: number
  }
  incidents: ClientIncident[]
  total: number
}

export interface RetentionStatusResponse {
  retention_days: {
    broker_raw: number
    broker_daily: number
    client: number
    topic: number
  }
  rows_past_retention: Record<string, number>
  total_rows_past_retention: number
}

export interface RetentionPurgeResponse {
  status: string
  deleted_rows: number
  before: RetentionStatusResponse
  after: RetentionStatusResponse
}

// MQTT Explorer types
export interface MqttTopic {
  topic: string
  value: string
  timestamp: string
  count: number
  retained: boolean
  qos: number
}

// Log types
export interface LogEntry {
  timestamp: string
  level?: string
  message: string
  raw: string
}

// ── Broker Alert types (monitor service) ────────────────────────────────────

export type BrokerAlertSeverity = 'low' | 'medium' | 'high' | 'critical'
export type BrokerAlertStatus = 'active' | 'acknowledged' | 'cleared'

export interface BrokerAlert {
  id: string
  type: string
  severity: BrokerAlertSeverity
  title: string
  impact: string
  description: string
  timestamp: string
  status: BrokerAlertStatus
  resolved_at?: string
}

// ── Smart Anomaly Detection types ────────────────────────────────────────────

export type AlertSeverity = 'low' | 'medium' | 'high' | 'critical'
export type AnomalyType = 'z_score' | 'ewma' | 'spike' | 'silence'

export interface AiAlert {
  id: string
  entity_type: string
  entity_id: string
  anomaly_type: AnomalyType
  severity: AlertSeverity
  description: string
  acknowledged: boolean
  created_at: string
}

export interface AiAnomaly {
  id: string
  entity_type: string
  entity_id: string
  anomaly_type: AnomalyType
  score: number
  details: Record<string, unknown>
  detected_at: string
}

export interface MetricField {
  mean: number | null
  std: number | null
  count: number
  computed_at: string | null
}

export interface AiMetrics {
  entity_type: string
  entity_id: string
  window: string
  fields: Record<string, MetricField>
}
