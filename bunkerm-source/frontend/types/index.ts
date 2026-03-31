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
  // New fields from $SYS broker topics
  clients_total?: number
  clients_maximum?: number
  broker_version?: string
  broker_uptime?: string
  messages_received_raw?: number
  messages_sent_raw?: number
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

export type StatsPeriod = '15m' | '30m' | '1h' | '12h' | '1d' | '7d' | '30d'

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
