'use client'

import { useEffect, useState, useCallback } from 'react'
import {
  RefreshCw,
  BellRing,
  CheckCheck,
  AlertTriangle,
  Zap,
  Info,
  History,
  Download,
  ShieldAlert,
} from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { monitorApi } from '@/lib/api'
import { formatRelativeTime } from '@/lib/timeUtils'
import type { BrokerAlert, BrokerAlertSeverity } from '@/types'

// ─── Severity config ──────────────────────────────────────────────────────────

const SEVERITY_CONFIG: Record<BrokerAlertSeverity, { label: string; className: string; icon: React.ElementType }> = {
  critical: { label: 'Critical', className: 'bg-red-100 text-red-800 border-red-200 dark:bg-red-900/30 dark:text-red-400', icon: Zap },
  high:     { label: 'High',     className: 'bg-orange-100 text-orange-800 border-orange-200 dark:bg-orange-900/30 dark:text-orange-400', icon: AlertTriangle },
  medium:   { label: 'Medium',   className: 'bg-yellow-100 text-yellow-800 border-yellow-200 dark:bg-yellow-900/30 dark:text-yellow-400', icon: AlertTriangle },
  low:      { label: 'Low',      className: 'bg-blue-100 text-blue-800 border-blue-200 dark:bg-blue-900/30 dark:text-blue-400', icon: Info },
}

const STATUS_CONFIG = {
  active:       { label: 'Active',       className: 'bg-red-100 text-red-700 border-red-200' },
  acknowledged: { label: 'Acknowledged', className: 'bg-gray-100 text-gray-600 border-gray-200' },
  cleared:      { label: 'Cleared',      className: 'bg-green-100 text-green-700 border-green-200' },
}

const TYPE_LABELS: Record<string, string> = {
  broker_down:      'Broker Down',
  client_capacity:  'Connection Capacity',
  reconnect_loop:   'Reconnect Loop',
  auth_failure:     'Auth Failure',
}

// ─── Download helpers ─────────────────────────────────────────────────────────

function downloadCsv(data: BrokerAlert[], filename: string) {
  const cols = ['timestamp', 'type', 'severity', 'title', 'status', 'description', 'impact', 'resolved_at']
  const header = cols.join(',')
  const rows = data.map((a) =>
    cols.map((c) => {
      const v = (a as Record<string, unknown>)[c] ?? ''
      return `"${String(v).replace(/"/g, '""')}"`
    }).join(',')
  )
  const blob = new Blob([header + '\n' + rows.join('\n')], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = filename; a.click()
  URL.revokeObjectURL(url)
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function MonitoringPage() {
  // Active alerts
  const [alerts, setAlerts] = useState<BrokerAlert[]>([])
  const [alertsLoading, setAlertsLoading] = useState(true)
  const [alertsRefreshing, setAlertsRefreshing] = useState(false)
  const [acknowledging, setAcknowledging] = useState<Set<string>>(new Set())

  // History
  const [history, setHistory] = useState<BrokerAlert[]>([])
  const [historyLoading, setHistoryLoading] = useState(true)
  const [severityFilter, setSeverityFilter] = useState<string>('all')
  const [typeFilter, setTypeFilter] = useState<string>('all')

  // ── Fetch active alerts ───────────────────────────────────────────────────

  const fetchAlerts = useCallback(async (showRefreshIndicator = false) => {
    if (showRefreshIndicator) setAlertsRefreshing(true)
    try {
      const res = await monitorApi.getBrokerAlerts()
      setAlerts(res.alerts)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to load alerts')
    } finally {
      setAlertsLoading(false)
      setAlertsRefreshing(false)
    }
  }, [])

  // ── Fetch history ─────────────────────────────────────────────────────────

  const fetchHistory = useCallback(async () => {
    try {
      const res = await monitorApi.getAlertHistory()
      setHistory(res.history)
    } catch {
      // silently ignore — history is best-effort
    } finally {
      setHistoryLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchAlerts(true)
    fetchHistory()
    const interval = setInterval(() => {
      fetchAlerts()
      fetchHistory()
    }, 30_000)
    return () => clearInterval(interval)
  }, [fetchAlerts, fetchHistory])

  // ── Acknowledge ───────────────────────────────────────────────────────────

  const handleAcknowledge = async (alert: BrokerAlert) => {
    setAcknowledging((prev) => new Set(prev).add(alert.id))
    try {
      await monitorApi.acknowledgeAlert(alert.id)
      toast.success('Alert acknowledged')
      await Promise.all([fetchAlerts(), fetchHistory()])
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to acknowledge alert')
    } finally {
      setAcknowledging((prev) => { const n = new Set(prev); n.delete(alert.id); return n })
    }
  }

  // ── Filtered history ──────────────────────────────────────────────────────

  const filteredHistory = history.filter((h) => {
    if (severityFilter !== 'all' && h.severity !== severityFilter) return false
    if (typeFilter !== 'all' && h.type !== typeFilter) return false
    return true
  })

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <ShieldAlert className="h-6 w-6" />
            Alerts
          </h1>
          <p className="text-muted-foreground text-sm mt-1">
            Broker management alerts — capacity, connectivity, auth and reconnect issues. Refreshes every 30s.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => { fetchAlerts(true); fetchHistory() }}
          disabled={alertsRefreshing}
        >
          <RefreshCw className={`h-4 w-4 mr-2 ${alertsRefreshing ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      {/* ── Active alerts ────────────────────────────────────────────────── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <BellRing className="h-4 w-4 text-orange-500" />
            Active Alerts
            {alerts.length > 0 && (
              <Badge variant="destructive" className="ml-1 h-5 px-1.5 text-xs">
                {alerts.length}
              </Badge>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {alertsLoading ? (
            <div className="flex items-center justify-center py-12 text-muted-foreground">
              <div className="flex flex-col items-center gap-3">
                <RefreshCw className="h-5 w-5 animate-spin" />
                <p className="text-sm">Loading alerts...</p>
              </div>
            </div>
          ) : alerts.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
              <BellRing className="h-9 w-9 mb-3 opacity-25" />
              <p className="text-sm font-medium">No active alerts</p>
              <p className="text-xs mt-1">Alerts appear when a broker condition exceeds its threshold.</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-28 pl-4">Severity</TableHead>
                  <TableHead className="w-40">Type</TableHead>
                  <TableHead>Description</TableHead>
                  <TableHead className="w-full">Impact</TableHead>
                  <TableHead className="w-28 text-right">Since</TableHead>
                  <TableHead className="w-32 text-right pr-4">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {alerts.map((alert) => {
                  const cfg = SEVERITY_CONFIG[alert.severity] ?? SEVERITY_CONFIG.high
                  const SeverityIcon = cfg.icon
                  return (
                    <TableRow key={alert.id}>
                      <TableCell className="pl-4">
                        <Badge className={`${cfg.className} border flex items-center gap-1 w-fit`}>
                          <SeverityIcon className="h-3 w-3" />
                          {cfg.label}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-sm font-medium">
                        {TYPE_LABELS[alert.type] ?? alert.type}
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground max-w-xs" title={alert.description}>
                        {alert.description}
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {alert.impact}
                      </TableCell>
                      <TableCell className="text-right text-xs text-muted-foreground whitespace-nowrap">
                        {formatRelativeTime(alert.timestamp)}
                      </TableCell>
                      <TableCell className="text-right pr-4">
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-7 text-xs"
                          disabled={acknowledging.has(alert.id)}
                          onClick={() => handleAcknowledge(alert)}
                        >
                          <CheckCheck className="h-3 w-3 mr-1" />
                          {acknowledging.has(alert.id) ? 'Saving…' : 'Acknowledge'}
                        </Button>
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* ── Alert history ─────────────────────────────────────────────────── */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <CardTitle className="text-base font-semibold flex items-center gap-2">
              <History className="h-4 w-4 text-muted-foreground" />
              Alert History
              {history.length > 0 && (
                <span className="text-xs text-muted-foreground font-normal">
                  {history.length} / 200 records
                </span>
              )}
            </CardTitle>
            <div className="flex items-center gap-2 flex-wrap">
              {/* Filters */}
              <Select value={severityFilter} onValueChange={setSeverityFilter}>
                <SelectTrigger className="h-8 w-36 text-xs">
                  <SelectValue placeholder="Severity" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Severities</SelectItem>
                  <SelectItem value="critical">Critical</SelectItem>
                  <SelectItem value="high">High</SelectItem>
                  <SelectItem value="medium">Medium</SelectItem>
                  <SelectItem value="low">Low</SelectItem>
                </SelectContent>
              </Select>
              <Select value={typeFilter} onValueChange={setTypeFilter}>
                <SelectTrigger className="h-8 w-44 text-xs">
                  <SelectValue placeholder="Alert type" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Types</SelectItem>
                  <SelectItem value="broker_down">Broker Down</SelectItem>
                  <SelectItem value="client_capacity">Connection Capacity</SelectItem>
                  <SelectItem value="reconnect_loop">Reconnect Loop</SelectItem>
                  <SelectItem value="auth_failure">Auth Failure</SelectItem>
                </SelectContent>
              </Select>
              {/* Download */}
              <Button
                variant="outline"
                size="sm"
                className="h-8 text-xs"
                disabled={filteredHistory.length === 0}
                onClick={() => downloadCsv(filteredHistory, `bunkerm-alerts-${new Date().toISOString().slice(0, 10)}.csv`)}
              >
                <Download className="h-3.5 w-3.5 mr-1.5" />
                Export CSV
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {historyLoading ? (
            <div className="flex items-center justify-center py-10 text-muted-foreground">
              <RefreshCw className="h-4 w-4 animate-spin mr-2" />
              <p className="text-sm">Loading history...</p>
            </div>
          ) : filteredHistory.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
              <History className="h-9 w-9 mb-3 opacity-25" />
              <p className="text-sm font-medium">No history yet</p>
              <p className="text-xs mt-1">Events are recorded as alerts are raised, acknowledged or cleared.</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-28 pl-4">Severity</TableHead>
                  <TableHead className="w-40">Type</TableHead>
                  <TableHead className="w-28">Status</TableHead>
                  <TableHead>Description</TableHead>
                  <TableHead className="w-32 text-right">Triggered</TableHead>
                  <TableHead className="w-32 text-right pr-4">Resolved</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredHistory.map((h, idx) => {
                  const cfg = SEVERITY_CONFIG[h.severity] ?? SEVERITY_CONFIG.high
                  const SeverityIcon = cfg.icon
                  const statusCfg = STATUS_CONFIG[h.status] ?? STATUS_CONFIG.cleared
                  return (
                    <TableRow key={`${h.id}-${idx}`} className="text-sm">
                      <TableCell className="pl-4">
                        <Badge className={`${cfg.className} border flex items-center gap-1 w-fit`}>
                          <SeverityIcon className="h-3 w-3" />
                          {cfg.label}
                        </Badge>
                      </TableCell>
                      <TableCell className="font-medium">
                        {TYPE_LABELS[h.type] ?? h.type}
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className={`${statusCfg.className} border text-xs`}>
                          {statusCfg.label}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-muted-foreground max-w-sm truncate" title={h.description}>
                        {h.description}
                      </TableCell>
                      <TableCell className="text-right text-xs text-muted-foreground whitespace-nowrap">
                        {new Date(h.timestamp).toLocaleString()}
                      </TableCell>
                      <TableCell className="text-right text-xs text-muted-foreground whitespace-nowrap pr-4">
                        {h.resolved_at ? new Date(h.resolved_at).toLocaleString() : '—'}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
