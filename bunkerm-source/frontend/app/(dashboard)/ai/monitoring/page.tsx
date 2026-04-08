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
  ChevronDown,
  ShieldAlert,
  SlidersHorizontal,
  Save,
  Loader2,
} from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
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
import { exportLogs, type ExportFormat } from '@/lib/export-logs'
import { formatRelativeTime } from '@/lib/timeUtils'
import type { BrokerAlert, BrokerAlertSeverity } from '@/types'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

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

// ─── Export helper ────────────────────────────────────────────────────────────

function downloadAlerts(data: BrokerAlert[], format: ExportFormat) {
  exportLogs(
    data,
    format,
    [
      { header: 'Timestamp',   value: a => a.timestamp },
      { header: 'Type',        value: a => a.type },
      { header: 'Severity',    value: a => a.severity },
      { header: 'Title',       value: a => a.title },
      { header: 'Status',      value: a => a.status },
      { header: 'Description', value: a => a.description },
      { header: 'Impact',      value: a => a.impact ?? '' },
      { header: 'Resolved At', value: a => (a as unknown as Record<string, unknown>)['resolved_at'] ?? '' },
    ],
    'bunkerm-alerts'
  )
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

  // ── Alert thresholds config ───────────────────────────────────────────────

  type AlertCfg = {
    broker_down_grace_polls: number; client_capacity_pct: number; client_max_default: number;
    reconnect_loop_count: number; reconnect_loop_window_s: number;
    auth_fail_count: number; auth_fail_window_s: number; cooldown_minutes: number;
  }
  const [alertCfg, setAlertCfg] = useState<AlertCfg | null>(null)
  const [cfgDraft, setCfgDraft] = useState<AlertCfg | null>(null)
  const [cfgLoading, setCfgLoading] = useState(true)
  const [cfgSaving, setCfgSaving] = useState(false)

  // ── Fetch active alerts ───────────────────────────────────────────────────

  const fetchAlertConfig = useCallback(async () => {
    try {
      const cfg = await monitorApi.getAlertConfig()
      setAlertCfg(cfg)
      setCfgDraft(cfg)
    } catch {
      // silently ignore — thresholds section will show loading state
    } finally {
      setCfgLoading(false)
    }
  }, [])

  const handleSaveConfig = async () => {
    if (!cfgDraft) return
    setCfgSaving(true)
    try {
      await monitorApi.saveAlertConfig(cfgDraft)
      setAlertCfg(cfgDraft)
      toast.success('Alert thresholds saved')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to save thresholds')
    } finally {
      setCfgSaving(false)
    }
  }

  const cfgField = (key: keyof AlertCfg, label: string, unit?: string, hint?: string) => (
    <div className="flex flex-col gap-1">
      <Label htmlFor={key} className="text-xs font-medium">{label}</Label>
      <div className="flex items-center gap-1.5">
        <Input
          id={key}
          type="number"
          min={1}
          className="h-8 w-28 text-sm"
          value={cfgDraft?.[key] ?? ''}
          onChange={(e) => setCfgDraft((d) => d ? { ...d, [key]: Number(e.target.value) } : d)}
        />
        {unit && <span className="text-xs text-muted-foreground">{unit}</span>}
      </div>
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  )

  const cfgIsDirty = JSON.stringify(alertCfg) !== JSON.stringify(cfgDraft)

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
    fetchAlertConfig()
    const interval = setInterval(() => {
      fetchAlerts()
      fetchHistory()
    }, 30_000)
    return () => clearInterval(interval)
  }, [fetchAlerts, fetchHistory, fetchAlertConfig])

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

      {/* ── Alert thresholds ─────────────────────────────────────────────── */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base font-semibold flex items-center gap-2">
              <SlidersHorizontal className="h-4 w-4 text-muted-foreground" />
              Alert Thresholds
            </CardTitle>
            <Button
              size="sm"
              onClick={handleSaveConfig}
              disabled={!cfgIsDirty || cfgSaving || cfgLoading}
            >
              {cfgSaving
                ? <><Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />Saving…</>
                : <><Save className="h-3.5 w-3.5 mr-1.5" />Save</>}
            </Button>
          </div>
          <CardDescription className="text-xs">
            Thresholds persist across restarts and take effect within 30 s. Env-var values are used as defaults until saved here.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {cfgLoading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground py-4">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading…
            </div>
          ) : (
            <div className="space-y-5">
              {/* Broker down */}
              <div>
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">Broker Down</p>
                <div className="grid grid-cols-2 gap-x-8 gap-y-3 sm:grid-cols-3">
                  {cfgField('broker_down_grace_polls', 'Grace polls', 'polls',
                    'Consecutive missed $SYS polls before triggering the Broker Down alert.')}
                </div>
              </div>
              <Separator />
              {/* Capacity */}
              <div>
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">Connection Capacity</p>
                <div className="grid grid-cols-2 gap-x-8 gap-y-3 sm:grid-cols-3">
                  {cfgField('client_capacity_pct', 'Capacity threshold', '%',
                    'Alert when connected clients reach this % of max_connections.')}
                  {cfgField('client_max_default', 'Max clients (fallback)', 'clients',
                    'Used when max_connections is unlimited (-1) in mosquitto.conf.')}
                </div>
              </div>
              <Separator />
              {/* Reconnect loop */}
              <div>
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">Reconnect Loop</p>
                <div className="grid grid-cols-2 gap-x-8 gap-y-3 sm:grid-cols-3">
                  {cfgField('reconnect_loop_count', 'Reconnects', 'times',
                    'Number of reconnects from the same client within the window.')}
                  {cfgField('reconnect_loop_window_s', 'Window', 'seconds',
                    'Sliding time window to count reconnect events.')}
                </div>
              </div>
              <Separator />
              {/* Auth failures */}
              <div>
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">Auth Failures</p>
                <div className="grid grid-cols-2 gap-x-8 gap-y-3 sm:grid-cols-3">
                  {cfgField('auth_fail_count', 'Failures', 'attempts',
                    'Failed authentication attempts within the window before alerting.')}
                  {cfgField('auth_fail_window_s', 'Window', 'seconds',
                    'Sliding time window to count auth failures.')}
                </div>
              </div>
              <Separator />
              {/* Cooldown */}
              <div>
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">General</p>
                <div className="grid grid-cols-2 gap-x-8 gap-y-3 sm:grid-cols-3">
                  {cfgField('cooldown_minutes', 'Alert cooldown', 'minutes',
                    'Minimum time before the same alert type can fire again after being acknowledged.')}
                </div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

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
              {/* Export */}
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-8 text-xs"
                    disabled={filteredHistory.length === 0}
                  >
                    Export
                    <ChevronDown className="h-3 w-3 ml-1" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onClick={() => downloadAlerts(filteredHistory, 'csv')}>CSV</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => downloadAlerts(filteredHistory, 'txt')}>TXT</DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
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
