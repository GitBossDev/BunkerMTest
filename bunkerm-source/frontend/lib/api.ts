import { generateNonce } from './utils'
import type { MqttClient, Role, Group, MqttTopic } from '@/types'

// The Python dynsec API's list endpoints return the raw mosquitto_ctrl stdout
// as a plain string (e.g. {"clients": "name1\nname2\n..."}).
// These helpers parse that into properly typed arrays.
function parseNameList(raw: unknown): string[] {
  if (Array.isArray(raw)) return raw.map(String).filter(Boolean)
  if (typeof raw !== 'string' || !raw.trim()) return []
  return raw
    .split('\n')
    .map((l) => l.trim())
    .filter((l) => l && !l.includes(':') && !l.startsWith('-'))
}

function parseClients(res: unknown): MqttClient[] {
  const raw = (res as Record<string, unknown>)?.clients ?? res
  if (Array.isArray(raw)) {
    if (raw.length === 0) return []
    // New paginated format: array of objects with a username field
    if (typeof raw[0] === 'object' && raw[0] !== null) {
      return (raw as Array<{ username: string }>)
        .map((c) => ({ username: c.username }))
        .filter((c) => c.username)
    }
    // Legacy string-array format
    return (raw as string[]).filter(Boolean).map((username) => ({ username }))
  }
  return parseNameList(raw).map((username) => ({ username }))
}

function parseRoles(res: unknown): Role[] {
  const raw = (res as Record<string, unknown>)?.roles ?? res
  return parseNameList(raw).map((rolename) => ({ rolename }))
}

function parseGroups(res: unknown): Group[] {
  const raw = (res as Record<string, unknown>)?.groups ?? res
  return parseNameList(raw).map((groupname) => ({ groupname }))
}

// All API calls go through the Next.js server-side proxy at /api/proxy/<service>.
// The proxy injects the X-API-Key header from the server environment — the key
// is never exposed to the browser.
const DYNSEC_API_URL     = '/api/proxy/dynsec'
const MONITOR_API_URL    = '/api/proxy/monitor'
const AWS_BRIDGE_API_URL = '/api/proxy/aws-bridge'
const AZURE_BRIDGE_API_URL = '/api/proxy/azure-bridge'
const CONFIG_API_URL     = '/api/proxy/config'
const CLIENTLOGS_API_URL = '/api/proxy/clientlogs'

function buildUrl(base: string, path: string): string {
  const nonce = generateNonce()
  const timestamp = Date.now()
  const url = `${base}${path}`
  const separator = url.includes('?') ? '&' : '?'
  return `${url}${separator}nonce=${nonce}&timestamp=${timestamp}`
}

function getHeaders(extra?: Record<string, string>): HeadersInit {
  return {
    'Content-Type': 'application/json',
    ...extra,
  }
}

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...options,
    headers: {
      ...getHeaders(),
      ...(options?.headers as Record<string, string> || {}),
    },
  })

  if (!response.ok) {
    const error = await response.text()
    throw new Error(error || `HTTP ${response.status}`)
  }

  const text = await response.text()
  if (!text) return {} as T
  return JSON.parse(text) as T
}

// ─── DynSec API ─────────────────────────────────────────────────────────────

export const dynsecApi = {
  // Clients
  getClients: () => request(buildUrl(DYNSEC_API_URL, '/clients')).then(parseClients),
  getClient: (username: string) => request(buildUrl(DYNSEC_API_URL, `/clients/${username}`)),

  // Paginated client list with full details — reads dynamic-security.json server-side (Alt A+B).
  // Returns { clients, total, page, limit, pages } — no N+1 subprocess calls.
  getClientsPaginated: (params?: { page?: number; limit?: number; search?: string }) => {
    const p = new URLSearchParams()
    if (params?.page !== undefined) p.set('page', String(params.page))
    if (params?.limit !== undefined) p.set('limit', String(params.limit))
    if (params?.search) p.set('search', params.search)
    const qs = p.toString()
    const path = qs ? `/clients?${qs}` : '/clients'
    return request<{
      clients: { username: string; disabled: boolean; roles: string[]; groups: string[] }[]
      total: number
      page: number
      limit: number
      pages: number
    }>(buildUrl(DYNSEC_API_URL, path))
  },

  // Disabled-state map for all clients (single JSON read — for Connected Clients page).
  getClientsDisabledMap: () =>
    request<{ map: Record<string, boolean>; usernames: string[] }>(
      buildUrl(DYNSEC_API_URL, '/clients/disabled-map')
    ),
  createClient: (data: { username: string; password: string }) =>
    request(buildUrl(DYNSEC_API_URL, '/clients'), {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  deleteClient: (username: string) =>
    request(buildUrl(DYNSEC_API_URL, `/clients/${username}`), { method: 'DELETE' }),

  enableClient: (username: string) =>
    request(buildUrl(DYNSEC_API_URL, `/clients/${username}/enable`), { method: 'PUT' }),
  disableClient: (username: string) =>
    request(buildUrl(DYNSEC_API_URL, `/clients/${username}/disable`), { method: 'PUT' }),

  // Client roles
  addClientRole: (username: string, rolename: string) =>
    request(buildUrl(DYNSEC_API_URL, `/clients/${username}/roles`), {
      method: 'POST',
      body: JSON.stringify({ role_name: rolename }),
    }),
  removeClientRole: (username: string, rolename: string) =>
    request(buildUrl(DYNSEC_API_URL, `/clients/${username}/roles/${rolename}`), {
      method: 'DELETE',
    }),

  // Client groups
  addClientToGroup: (groupname: string, username: string, priority?: number) =>
    request(buildUrl(DYNSEC_API_URL, `/groups/${groupname}/clients`), {
      method: 'POST',
      body: JSON.stringify({ username, ...(priority !== undefined && { priority }) }),
    }),
  removeClientFromGroup: (groupname: string, username: string) =>
    request(buildUrl(DYNSEC_API_URL, `/groups/${groupname}/clients/${username}`), {
      method: 'DELETE',
    }),

  // Roles
  getRoles: () => request(buildUrl(DYNSEC_API_URL, '/roles')).then(parseRoles),
  getRole: (rolename: string) => request(buildUrl(DYNSEC_API_URL, `/roles/${rolename}`)),
  createRole: (data: { name: string }) =>
    request(buildUrl(DYNSEC_API_URL, '/roles'), {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  deleteRole: (rolename: string) =>
    request(buildUrl(DYNSEC_API_URL, `/roles/${rolename}`), { method: 'DELETE' }),

  // Role ACLs
  addRoleACL: (rolename: string, acl: { topic: string; aclType: string; permission: string }) =>
    request(buildUrl(DYNSEC_API_URL, `/roles/${rolename}/acls`), {
      method: 'POST',
      body: JSON.stringify(acl),
    }),
  removeRoleACL: (rolename: string, aclType: string, topic: string) => {
    const encoded = encodeURIComponent(topic)
    return request(
      buildUrl(DYNSEC_API_URL, `/roles/${rolename}/acls`) + `&acl_type=${aclType}&topic=${encoded}`,
      { method: 'DELETE' }
    )
  },
  testRoleACL: (rolename: string, aclType: string, topic: string) =>
    request<{
      allowed: boolean
      reason: 'role_acl' | 'default_acl'
      matchedRule: { topic: string; aclType: string; allow: boolean; priority: number } | null
      defaultKey?: string
    }>(buildUrl(DYNSEC_API_URL, `/roles/${rolename}/acls/test`), {
      method: 'POST',
      body: JSON.stringify({ aclType, topic }),
    }),

  // Groups
  getGroups: () => request(buildUrl(DYNSEC_API_URL, '/groups')).then(parseGroups),
  getGroup: (groupname: string) => request(buildUrl(DYNSEC_API_URL, `/groups/${groupname}`)),
  createGroup: (data: { name: string }) =>
    request(buildUrl(DYNSEC_API_URL, '/groups'), {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  deleteGroup: (groupname: string) =>
    request(buildUrl(DYNSEC_API_URL, `/groups/${groupname}`), { method: 'DELETE' }),

  // Group roles
  addGroupRole: (groupname: string, rolename: string) =>
    request(buildUrl(DYNSEC_API_URL, `/groups/${groupname}/roles`), {
      method: 'POST',
      body: JSON.stringify({ role_name: rolename }),
    }),
  removeGroupRole: (groupname: string, rolename: string) =>
    request(buildUrl(DYNSEC_API_URL, `/groups/${groupname}/roles/${rolename}`), {
      method: 'DELETE',
    }),

  // Default ACL Access
  getDefaultACL: () =>
    request<{ publishClientSend: boolean; publishClientReceive: boolean; subscribe: boolean; unsubscribe: boolean }>(
      buildUrl(DYNSEC_API_URL, '/default-acl')
    ),
  setDefaultACL: (config: { publishClientSend: boolean; publishClientReceive: boolean; subscribe: boolean; unsubscribe: boolean }) =>
    request(buildUrl(DYNSEC_API_URL, '/default-acl'), {
      method: 'PUT',
      body: JSON.stringify(config),
    }),

  // Password import
  importPassword: (formData: FormData) =>
    fetch(`/api/proxy/dynsec/import-password-file?nonce=${generateNonce()}&t=${Date.now()}`, {
      method: 'POST',
      body: formData,
    }),
}

// ─── Monitor API ─────────────────────────────────────────────────────────────

export const monitorApi = {
  getStats: () => request(buildUrl(MONITOR_API_URL, '/stats')),
  getBytesForPeriod: (period: string) => request(buildUrl(MONITOR_API_URL, `/stats/bytes?period=${period}`)),
  getMessagesForPeriod: (period: string) => request(buildUrl(MONITOR_API_URL, `/stats/messages?period=${period}`)),
  getTopologyStats: (limit = 15) => request(buildUrl(MONITOR_API_URL, `/stats/topology?limit=${limit}`)),
  getHealthStats: () => request(buildUrl(MONITOR_API_URL, '/stats/health')),
  getQosStats:    () => request(buildUrl(MONITOR_API_URL, '/stats/qos')),
  getResourceStats: () => request<{ mosquitto_cpu_pct: number | null; mosquitto_rss_bytes: number | null; mosquitto_vms_bytes: number | null }>(buildUrl(MONITOR_API_URL, '/stats/resources')),
  getTopics: () => request<{ topics: MqttTopic[] }>(buildUrl(MONITOR_API_URL, '/topics')),
  publishMessage: (data: { topic: string; payload: string; qos?: number; retain?: boolean }) =>
    request(buildUrl(MONITOR_API_URL, '/publish'), {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // Broker alerts (generated by the monitor service AlertEngine)
  getBrokerAlerts: () =>
    request<{ alerts: import('@/types').BrokerAlert[] }>(buildUrl(MONITOR_API_URL, '/alerts/broker')),
  getAlertHistory: () =>
    request<{ history: import('@/types').BrokerAlert[]; total: number }>(buildUrl(MONITOR_API_URL, '/alerts/broker/history')),
  acknowledgeAlert: (id: string) =>
    request(buildUrl(MONITOR_API_URL, `/alerts/broker/${encodeURIComponent(id)}/acknowledge`), { method: 'POST' }),

  getAlertConfig: () =>
    request<{
      broker_down_grace_polls: number; client_capacity_pct: number; client_max_default: number;
      reconnect_loop_count: number; reconnect_loop_window_s: number;
      auth_fail_count: number; auth_fail_window_s: number; cooldown_minutes: number;
    }>(buildUrl(MONITOR_API_URL, '/alerts/config')),
  saveAlertConfig: (cfg: {
    broker_down_grace_polls: number; client_capacity_pct: number; client_max_default: number;
    reconnect_loop_count: number; reconnect_loop_window_s: number;
    auth_fail_count: number; auth_fail_window_s: number; cooldown_minutes: number;
  }) =>
    request<{ status: string }>(buildUrl(MONITOR_API_URL, '/alerts/config'), {
      method: 'PUT',
      body: JSON.stringify(cfg),
    }),

  // Logs — routed through Next.js proxy so the API key is injected server-side
  getBrokerLogs: () => request<{ logs: string[] }>(buildUrl(CONFIG_API_URL, '/broker')),
  getClientLogs: () => request<{ logs: string[] }>(buildUrl(CLIENTLOGS_API_URL, '/events')),
}

// ─── Config API ──────────────────────────────────────────────────────────────

export const configApi = {
  getMosquittoConfig: () =>
    request<{ config: Record<string, unknown>; listeners: unknown[] }>(
      `/api/proxy/config/mosquitto-config?nonce=${generateNonce()}&t=${Date.now()}`
    ),
  saveMosquittoConfig: (configData: unknown) =>
    request<{ success: boolean; message?: string }>(`/api/proxy/config/mosquitto-config?nonce=${generateNonce()}&t=${Date.now()}`, {
      method: 'POST',
      body: JSON.stringify(configData),
    }),
  resetMosquittoConfig: () =>
    request(`/api/proxy/config/reset-mosquitto-config?nonce=${generateNonce()}&t=${Date.now()}`, {
      method: 'POST',
    }),
  restartMosquitto: () =>
    request<{ success: boolean; message: string }>(`/api/proxy/config/restart-mosquitto?nonce=${generateNonce()}&t=${Date.now()}`, {
      method: 'POST',
    }),

  getDynSecJson: () =>
    request(`/api/proxy/config/dynsec-json?nonce=${generateNonce()}&t=${Date.now()}`),
  importDynSecJson: (formData: FormData) =>
    fetch(`/api/proxy/config/import-dynsec-json?nonce=${generateNonce()}&t=${Date.now()}`, {
      method: 'POST',
      body: formData,
    }),
  importAcl: (data: unknown) =>
    request<{ success: boolean; message: string; stats?: { clients: number; groups: number; roles: number } }>(
      `/api/proxy/config/import-acl?nonce=${generateNonce()}&t=${Date.now()}`,
      { method: 'POST', body: JSON.stringify(data) }
    ),
  exportDynSecJson: () =>
    fetch(`/api/proxy/config/export-dynsec-json?nonce=${generateNonce()}&t=${Date.now()}`, {
      headers: { Accept: 'application/json' },
    }),
  resetDynSecJson: () =>
    request(`/api/proxy/config/reset-dynsec-json?nonce=${generateNonce()}&t=${Date.now()}`, {
      method: 'POST',
    }),
}

// ─── AWS Bridge API ──────────────────────────────────────────────────────────

export const awsApi = {
  getConfig: () => request(buildUrl(AWS_BRIDGE_API_URL, '/config')),
  saveConfig: (formData: FormData) =>
    fetch(buildUrl(AWS_BRIDGE_API_URL, '/config'), {
      method: 'POST',
      body: formData,
    }),
}

// ─── Azure Bridge API ────────────────────────────────────────────────────────

export const azureApi = {
  getConfig: () => request(buildUrl(AZURE_BRIDGE_API_URL, '/config')),
  saveConfig: (data: unknown) =>
    request(buildUrl(AZURE_BRIDGE_API_URL, '/config'), {
      method: 'POST',
      body: JSON.stringify(data),
    }),
}

// ─── Client Logs API ─────────────────────────────────────────────────────────

export const clientlogsApi = {
  getEvents: () => request<{ events: unknown[] }>(buildUrl(CLIENTLOGS_API_URL, '/events')),
  getConnectedClients: () => request<{ clients: unknown[] }>(buildUrl(CLIENTLOGS_API_URL, '/connected-clients')),
  getLastConnection: () => request<{ info: Record<string, { ip_address: string; port: number; timestamp: string }> }>(buildUrl(CLIENTLOGS_API_URL, '/last-connection')),
  getTopSubscribed: (limit = 15) => request<{ top_subscribed: { topic: string; count: number }[]; total_distinct_subscribed: number }>(buildUrl(CLIENTLOGS_API_URL, `/top-subscribed?limit=${limit}`)),
  enableClient: (username: string) =>
    request(buildUrl(CLIENTLOGS_API_URL, `/enable/${encodeURIComponent(username)}`), { method: 'POST' }),
  disableClient: (username: string) =>
    request(buildUrl(CLIENTLOGS_API_URL, `/disable/${encodeURIComponent(username)}`), { method: 'POST' }),
}

// ─── Smart Anomaly Detection API ─────────────────────────────────────────────

import type { AiAlert, AiAnomaly, AiMetrics } from '@/types'

const AI_API_URL = '/api/proxy/ai'

export const aiApi = {
  getAlerts: (params?: { severity?: string; acknowledged?: boolean; limit?: number }) => {
    const qs = new URLSearchParams()
    if (params?.severity) qs.set('severity', params.severity)
    if (params?.acknowledged !== undefined) qs.set('acknowledged', String(params.acknowledged))
    if (params?.limit !== undefined) qs.set('limit', String(params.limit))
    const query = qs.toString() ? `?${qs}` : ''
    return request<{ alerts: AiAlert[] }>(buildUrl(AI_API_URL, `/alerts${query}`))
  },
  acknowledgeAlert: (id: string) =>
    request(buildUrl(AI_API_URL, `/alerts/${id}/acknowledge`), { method: 'POST' }),

  getAnomalies: (params?: { entity_id?: string; anomaly_type?: string; limit?: number }) => {
    const qs = new URLSearchParams()
    if (params?.entity_id) qs.set('entity_id', params.entity_id)
    if (params?.anomaly_type) qs.set('anomaly_type', params.anomaly_type)
    if (params?.limit !== undefined) qs.set('limit', String(params.limit))
    const query = qs.toString() ? `?${qs}` : ''
    return request<{ anomalies: AiAnomaly[] }>(buildUrl(AI_API_URL, `/anomalies${query}`))
  },

  getEntities: (entity_type = 'topic') =>
    request<{ entity_type: string; entities: string[] }>(
      buildUrl(AI_API_URL, `/metrics/entities?entity_type=${encodeURIComponent(entity_type)}`)
    ),
  getMetrics: (entity_id: string, window: '1h' | '24h' = '1h', entity_type = 'topic') =>
    request<AiMetrics>(
      buildUrl(AI_API_URL, `/metrics?entity_type=${encodeURIComponent(entity_type)}&entity_id=${encodeURIComponent(entity_id)}&window=${window}`)
    ),

  getHealth: () =>
    request<{ status: string; tier: string }>(buildUrl(AI_API_URL, '/health')),
}
