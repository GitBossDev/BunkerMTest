'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  AlertTriangle,
  BarChart3,
  CalendarDays,
  ChevronDown,
  Download,
  FileClock,
  RefreshCw,
  ShieldAlert,
  Trash2,
} from 'lucide-react'
import { toast } from 'sonner'
import { dynsecApi, reportsApi } from '@/lib/api'
import { formatAbsoluteTime } from '@/lib/timeUtils'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import type {
  BrokerDailyReportResponse,
  BrokerWeeklyReportResponse,
  ClientIncident,
  ClientIncidentsResponse,
  ClientSummary,
  ClientTimelineResponse,
  RetentionStatusResponse,
} from '@/types'

const TIMELINE_TYPES = ['Client Connection', 'Client Disconnection', 'Auth Failure', 'Publish', 'Subscribe'] as const
const INCIDENT_TYPES = ['ungraceful_disconnect', 'auth_failure', 'reconnect_loop'] as const

function downloadFromResponse(response: Response) {
  return response.blob().then((blob) => {
    const disposition = response.headers.get('content-disposition') ?? ''
    const match = disposition.match(/filename="?([^";]+)"?/) 
    const filename = match?.[1] ?? 'report-export'
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = filename
    anchor.click()
    URL.revokeObjectURL(url)
  })
}

function formatNumber(value: number | null | undefined) {
  if (value == null) return '—'
  return new Intl.NumberFormat().format(value)
}

function formatDecimal(value: number | null | undefined, digits = 2) {
  if (value == null) return '—'
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: digits }).format(value)
}

function incidentLabel(type: ClientIncident['incident_type']) {
  if (type === 'ungraceful_disconnect') return 'Ungraceful Disconnect'
  if (type === 'auth_failure') return 'Auth Failure'
  return 'Reconnect Loop'
}

function timelineBadgeTone(eventType: string) {
  switch (eventType) {
    case 'Client Connection':
      return 'bg-emerald-50 text-emerald-700 border-emerald-200'
    case 'Client Disconnection':
      return 'bg-rose-50 text-rose-700 border-rose-200'
    case 'Auth Failure':
      return 'bg-rose-100 text-rose-800 border-rose-300'
    case 'Publish':
      return 'bg-amber-50 text-amber-700 border-amber-200'
    case 'Subscribe':
      return 'bg-sky-50 text-sky-700 border-sky-200'
    default:
      return 'bg-muted text-muted-foreground border-border'
  }
}

export default function ReportsPage() {
  const [activeTab, setActiveTab] = useState('broker')
  const [clients, setClients] = useState<ClientSummary[]>([])
  const [dailyDays, setDailyDays] = useState('30')
  const [weeklyWeeks, setWeeklyWeeks] = useState('8')
  const [timelineUsername, setTimelineUsername] = useState('')
  const [timelineDays, setTimelineDays] = useState('30')
  const [timelineLimit, setTimelineLimit] = useState('200')
  const [timelineTypes, setTimelineTypes] = useState<Set<string>>(new Set(TIMELINE_TYPES))
  const [incidentUsername, setIncidentUsername] = useState('')
  const [incidentDays, setIncidentDays] = useState('30')
  const [incidentLimit, setIncidentLimit] = useState('200')
  const [incidentReconnectWindow, setIncidentReconnectWindow] = useState('30')
  const [incidentReconnectThreshold, setIncidentReconnectThreshold] = useState('3')
  const [incidentTypes, setIncidentTypes] = useState<Set<string>>(new Set(INCIDENT_TYPES))
  const [dailyReport, setDailyReport] = useState<BrokerDailyReportResponse | null>(null)
  const [weeklyReport, setWeeklyReport] = useState<BrokerWeeklyReportResponse | null>(null)
  const [timelineReport, setTimelineReport] = useState<ClientTimelineResponse | null>(null)
  const [incidentsReport, setIncidentsReport] = useState<ClientIncidentsResponse | null>(null)
  const [retentionStatus, setRetentionStatus] = useState<RetentionStatusResponse | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [isExporting, setIsExporting] = useState(false)

  const canFetchTimeline = timelineUsername.trim().length > 0

  const fetchClients = useCallback(async () => {
    try {
      const data = await dynsecApi.getClientsPaginated({ page: 1, limit: 500 })
      setClients(data.clients ?? [])
      if (!timelineUsername && data.clients.length > 0) {
        setTimelineUsername(data.clients[0].username)
      }
    } catch {
      toast.error('Failed to load client catalog for reports')
    }
  }, [timelineUsername])

  const fetchAll = useCallback(async () => {
    setIsLoading(true)
    try {
      const [daily, weekly, retention] = await Promise.all([
        reportsApi.getBrokerDailyReport(Number(dailyDays)),
        reportsApi.getBrokerWeeklyReport(Number(weeklyWeeks)),
        reportsApi.getRetentionStatus(),
      ])
      setDailyReport(daily)
      setWeeklyReport(weekly)
      setRetentionStatus(retention)

      if (timelineUsername.trim()) {
        const timeline = await reportsApi.getClientTimeline({
          username: timelineUsername.trim(),
          days: Number(timelineDays),
          limit: Number(timelineLimit),
          eventTypes: Array.from(timelineTypes),
        })
        setTimelineReport(timeline)
      }

      const incidents = await reportsApi.getClientIncidents({
        days: Number(incidentDays),
        limit: Number(incidentLimit),
        username: incidentUsername.trim() || undefined,
        incidentTypes: Array.from(incidentTypes),
        reconnectWindowMinutes: Number(incidentReconnectWindow),
        reconnectThreshold: Number(incidentReconnectThreshold),
      })
      setIncidentsReport(incidents)
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unknown error'
      toast.error(`Failed to load reports: ${message}`)
    } finally {
      setIsLoading(false)
    }
  }, [dailyDays, weeklyWeeks, timelineUsername, timelineDays, timelineLimit, timelineTypes, incidentDays, incidentLimit, incidentUsername, incidentReconnectWindow, incidentReconnectThreshold, incidentTypes])

  useEffect(() => {
    fetchClients()
  }, [fetchClients])

  useEffect(() => {
    void fetchAll()
  }, [fetchAll])

  const retentionRows = useMemo(() => {
    return Object.entries(retentionStatus?.rows_past_retention ?? {})
      .sort((a, b) => b[1] - a[1])
  }, [retentionStatus])

  async function exportBroker(scope: 'daily' | 'weekly', format: 'csv' | 'json') {
    setIsExporting(true)
    try {
      const response = await reportsApi.exportBrokerReport({
        scope,
        days: Number(dailyDays),
        weeks: Number(weeklyWeeks),
        format,
      })
      await downloadFromResponse(response)
    } catch {
      toast.error('Failed to export broker report')
    } finally {
      setIsExporting(false)
    }
  }

  async function exportTimeline(format: 'csv' | 'json') {
    if (!timelineUsername.trim()) return
    setIsExporting(true)
    try {
      const response = await reportsApi.exportClientActivity({
        username: timelineUsername.trim(),
        days: Number(timelineDays),
        limit: Number(timelineLimit),
        format,
        eventTypes: Array.from(timelineTypes),
      })
      await downloadFromResponse(response)
    } catch {
      toast.error('Failed to export client activity')
    } finally {
      setIsExporting(false)
    }
  }

  async function purgeRetention() {
    try {
      const result = await reportsApi.purgeRetention()
      setRetentionStatus(result.after)
      toast.success(`Retention purge completed: ${result.deleted_rows} rows removed`)
    } catch {
      toast.error('Failed to purge retained historical data')
    }
  }

  function toggleTimelineType(type: string) {
    setTimelineTypes((prev) => {
      const next = new Set(prev)
      if (next.has(type)) {
        if (next.size > 1) next.delete(type)
      } else {
        next.add(type)
      }
      return next
    })
  }

  function toggleIncidentType(type: string) {
    setIncidentTypes((prev) => {
      const next = new Set(prev)
      if (next.has(type)) {
        if (next.size > 1) next.delete(type)
      } else {
        next.add(type)
      }
      return next
    })
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <h1 className="text-2xl font-bold">Reporting</h1>
          <p className="text-sm text-muted-foreground">
            Broker rollups, per-client audit timelines and incident review powered by the persisted SQLite history.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => void fetchAll()} disabled={isLoading}>
            <RefreshCw className={`mr-2 h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
          <Button variant="outline" size="sm" onClick={purgeRetention}>
            <Trash2 className="mr-2 h-4 w-4" />
            Purge Retention
          </Button>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard title="Daily message volume" value={formatNumber(dailyReport?.totals.total_messages_received)} hint="Received messages in the selected daily window" icon={<BarChart3 className="h-4 w-4" />} />
        <MetricCard title="Weekly peak concurrency" value={formatNumber(weeklyReport?.totals.peak_max_concurrent)} hint="Highest max concurrent observed across selected weeks" icon={<CalendarDays className="h-4 w-4" />} />
        <MetricCard title="Client incidents" value={formatNumber(incidentsReport?.total)} hint="Incident matches for the active filters" icon={<ShieldAlert className="h-4 w-4" />} />
        <MetricCard title="Rows past retention" value={formatNumber(retentionStatus?.total_rows_past_retention)} hint="Historical rows currently eligible for purge" icon={<FileClock className="h-4 w-4" />} />
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
        <TabsList>
          <TabsTrigger value="broker">Broker Reports</TabsTrigger>
          <TabsTrigger value="timeline">Client Timeline</TabsTrigger>
          <TabsTrigger value="incidents">Incident Review</TabsTrigger>
        </TabsList>

        <TabsContent value="broker" className="space-y-4">
          <Card>
            <CardHeader className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
              <div>
                <CardTitle>Broker Rollups</CardTitle>
                <CardDescription>Daily and weekly operational summaries from persisted broker history.</CardDescription>
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <div className="w-28">
                  <label className="mb-1 block text-xs text-muted-foreground">Days</label>
                  <Select value={dailyDays} onValueChange={setDailyDays}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="7">7</SelectItem>
                      <SelectItem value="14">14</SelectItem>
                      <SelectItem value="30">30</SelectItem>
                      <SelectItem value="90">90</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="w-28">
                  <label className="mb-1 block text-xs text-muted-foreground">Weeks</label>
                  <Select value={weeklyWeeks} onValueChange={setWeeklyWeeks}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="4">4</SelectItem>
                      <SelectItem value="8">8</SelectItem>
                      <SelectItem value="12">12</SelectItem>
                      <SelectItem value="24">24</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="outline" size="sm" disabled={isExporting}>
                      <Download className="mr-2 h-4 w-4" />
                      Export Broker
                      <ChevronDown className="ml-2 h-4 w-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem onClick={() => void exportBroker('daily', 'csv')}>Daily CSV</DropdownMenuItem>
                    <DropdownMenuItem onClick={() => void exportBroker('daily', 'json')}>Daily JSON</DropdownMenuItem>
                    <DropdownMenuItem onClick={() => void exportBroker('weekly', 'csv')}>Weekly CSV</DropdownMenuItem>
                    <DropdownMenuItem onClick={() => void exportBroker('weekly', 'json')}>Weekly JSON</DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="grid gap-4 lg:grid-cols-2">
                <DataTableCard title="Daily report" description="UTC day rollups for message volume, concurrency and latency.">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Day</TableHead>
                        <TableHead>RX</TableHead>
                        <TableHead>TX</TableHead>
                        <TableHead>Peak Clients</TableHead>
                        <TableHead>Avg Latency</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {dailyReport?.items.length ? dailyReport.items.map((item) => (
                        <TableRow key={item.day}>
                          <TableCell className="font-medium">{item.day}</TableCell>
                          <TableCell>{formatNumber(item.total_messages_received)}</TableCell>
                          <TableCell>{formatNumber(item.total_messages_sent)}</TableCell>
                          <TableCell>{formatNumber(item.peak_connected_clients)}</TableCell>
                          <TableCell>{formatDecimal(item.avg_latency_ms)}</TableCell>
                        </TableRow>
                      )) : <EmptyRow colSpan={5} label={isLoading ? 'Loading daily report...' : 'No daily report data available.'} />}
                    </TableBody>
                  </Table>
                </DataTableCard>

                <DataTableCard title="Weekly report" description="Weekly aggregation to spot longer-term volume and concurrency trends.">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Week</TableHead>
                        <TableHead>Days</TableHead>
                        <TableHead>RX</TableHead>
                        <TableHead>Peak Concurrent</TableHead>
                        <TableHead>Avg Latency</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {weeklyReport?.items.length ? weeklyReport.items.map((item) => (
                        <TableRow key={item.week_start}>
                          <TableCell className="font-medium">{item.week_start}</TableCell>
                          <TableCell>{formatNumber(item.days_covered)}</TableCell>
                          <TableCell>{formatNumber(item.total_messages_received)}</TableCell>
                          <TableCell>{formatNumber(item.peak_max_concurrent)}</TableCell>
                          <TableCell>{formatDecimal(item.avg_latency_ms)}</TableCell>
                        </TableRow>
                      )) : <EmptyRow colSpan={5} label={isLoading ? 'Loading weekly report...' : 'No weekly report data available.'} />}
                    </TableBody>
                  </Table>
                </DataTableCard>
              </div>

              <Card className="border-dashed shadow-none">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm">Retention overview</CardTitle>
                  <CardDescription>Visibility into rows already past policy before you purge them.</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                    <RetentionMini label="Broker raw" value={retentionStatus?.retention_days.broker_raw} />
                    <RetentionMini label="Broker daily" value={retentionStatus?.retention_days.broker_daily} />
                    <RetentionMini label="Client" value={retentionStatus?.retention_days.client} />
                    <RetentionMini label="Topic" value={retentionStatus?.retention_days.topic} />
                  </div>
                  <div className="mt-4 rounded-lg border">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Table</TableHead>
                          <TableHead>Rows past retention</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {retentionRows.length ? retentionRows.map(([tableName, count]) => (
                          <TableRow key={tableName}>
                            <TableCell className="font-mono text-xs">{tableName}</TableCell>
                            <TableCell>{formatNumber(count)}</TableCell>
                          </TableRow>
                        )) : <EmptyRow colSpan={2} label="No retention status available." />}
                      </TableBody>
                    </Table>
                  </div>
                </CardContent>
              </Card>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="timeline" className="space-y-4">
          <Card>
            <CardHeader className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
              <div>
                <CardTitle>Per-client timeline</CardTitle>
                <CardDescription>Connection, auth and topic activity merged into a single audit timeline.</CardDescription>
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <div className="min-w-56 flex-1">
                  <label className="mb-1 block text-xs text-muted-foreground">Client username</label>
                  <Select value={timelineUsername} onValueChange={setTimelineUsername}>
                    <SelectTrigger><SelectValue placeholder="Select a client" /></SelectTrigger>
                    <SelectContent>
                      {clients.map((client) => (
                        <SelectItem key={client.username} value={client.username}>{client.username}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="w-24">
                  <label className="mb-1 block text-xs text-muted-foreground">Days</label>
                  <Input value={timelineDays} onChange={(e) => setTimelineDays(e.target.value)} inputMode="numeric" />
                </div>
                <div className="w-24">
                  <label className="mb-1 block text-xs text-muted-foreground">Limit</label>
                  <Input value={timelineLimit} onChange={(e) => setTimelineLimit(e.target.value)} inputMode="numeric" />
                </div>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="outline" size="sm">
                      Filters
                      <ChevronDown className="ml-2 h-4 w-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    {TIMELINE_TYPES.map((type) => (
                      <DropdownMenuCheckboxItem
                        key={type}
                        checked={timelineTypes.has(type)}
                        onCheckedChange={() => toggleTimelineType(type)}
                      >
                        {type}
                      </DropdownMenuCheckboxItem>
                    ))}
                  </DropdownMenuContent>
                </DropdownMenu>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="outline" size="sm" disabled={!canFetchTimeline || isExporting}>
                      <Download className="mr-2 h-4 w-4" />
                      Export Timeline
                      <ChevronDown className="ml-2 h-4 w-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem onClick={() => void exportTimeline('csv')}>CSV</DropdownMenuItem>
                    <DropdownMenuItem onClick={() => void exportTimeline('json')}>JSON</DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-wrap gap-2">
                {TIMELINE_TYPES.map((type) => (
                  <button
                    key={type}
                    onClick={() => toggleTimelineType(type)}
                    className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${timelineTypes.has(type) ? 'border-primary/30 bg-primary/10 text-primary' : 'border-border text-muted-foreground'}`}
                  >
                    {type}
                  </button>
                ))}
              </div>

              <div className="grid gap-4 md:grid-cols-3">
                <MetricSubCard label="Client state" value={timelineReport?.client ? (timelineReport.client.disabled ? 'Disabled' : 'Active') : 'Unknown'} />
                <MetricSubCard label="Timeline events" value={formatNumber(timelineReport?.timeline.length)} />
                <MetricSubCard label="Last DynSec sync" value={timelineReport?.client ? formatAbsoluteTime(timelineReport.client.last_dynsec_sync_at) : '—'} />
              </div>

              <div className="rounded-lg border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Time</TableHead>
                      <TableHead>Event</TableHead>
                      <TableHead>Client ID</TableHead>
                      <TableHead>Topic / Reason</TableHead>
                      <TableHead>Transport</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {timelineReport?.timeline.length ? timelineReport.timeline.map((event, index) => (
                      <TableRow key={`${event.event_ts}-${event.client_id}-${index}`}>
                        <TableCell className="whitespace-nowrap text-xs text-muted-foreground">{formatAbsoluteTime(event.event_ts)}</TableCell>
                        <TableCell>
                          <Badge variant="outline" className={timelineBadgeTone(event.event_type)}>{event.event_type}</Badge>
                        </TableCell>
                        <TableCell className="font-mono text-xs">{event.client_id}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {event.topic ?? event.reason_code ?? event.disconnect_kind ?? '—'}
                        </TableCell>
                        <TableCell className="text-xs">
                          {event.ip_address ? `${event.ip_address}:${event.port ?? '—'}` : event.protocol_level ?? '—'}
                        </TableCell>
                      </TableRow>
                    )) : <EmptyRow colSpan={5} label={isLoading ? 'Loading timeline...' : 'Choose a client to inspect activity.'} />}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="incidents" className="space-y-4">
          <Card>
            <CardHeader className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
              <div>
                <CardTitle>Incident review</CardTitle>
                <CardDescription>Filter persisted client incidents for auth failures, reconnect loops and ungraceful disconnects.</CardDescription>
              </div>
              <div className="flex flex-wrap items-end gap-3">
                <div className="min-w-56">
                  <label className="mb-1 block text-xs text-muted-foreground">Username filter</label>
                  <Input value={incidentUsername} onChange={(e) => setIncidentUsername(e.target.value)} placeholder="Optional username" />
                </div>
                <div className="w-24">
                  <label className="mb-1 block text-xs text-muted-foreground">Days</label>
                  <Input value={incidentDays} onChange={(e) => setIncidentDays(e.target.value)} inputMode="numeric" />
                </div>
                <div className="w-24">
                  <label className="mb-1 block text-xs text-muted-foreground">Limit</label>
                  <Input value={incidentLimit} onChange={(e) => setIncidentLimit(e.target.value)} inputMode="numeric" />
                </div>
                <div className="w-24">
                  <label className="mb-1 block text-xs text-muted-foreground">Loop min</label>
                  <Input value={incidentReconnectWindow} onChange={(e) => setIncidentReconnectWindow(e.target.value)} inputMode="numeric" />
                </div>
                <div className="w-24">
                  <label className="mb-1 block text-xs text-muted-foreground">Loop count</label>
                  <Input value={incidentReconnectThreshold} onChange={(e) => setIncidentReconnectThreshold(e.target.value)} inputMode="numeric" />
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-wrap gap-2">
                {INCIDENT_TYPES.map((type) => (
                  <button
                    key={type}
                    onClick={() => toggleIncidentType(type)}
                    className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${incidentTypes.has(type) ? 'border-amber-300 bg-amber-50 text-amber-800' : 'border-border text-muted-foreground'}`}
                  >
                    {incidentLabel(type)}
                  </button>
                ))}
              </div>

              <div className="grid gap-4 md:grid-cols-3">
                <MetricSubCard label="Incidents found" value={formatNumber(incidentsReport?.total)} />
                <MetricSubCard label="Reconnect threshold" value={formatNumber(Number(incidentReconnectThreshold))} />
                <MetricSubCard label="Reconnect window" value={`${incidentReconnectWindow} min`} />
              </div>

              <div className="rounded-lg border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Time</TableHead>
                      <TableHead>Incident</TableHead>
                      <TableHead>Username</TableHead>
                      <TableHead>Client ID</TableHead>
                      <TableHead>Details</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {incidentsReport?.incidents.length ? incidentsReport.incidents.map((incident, index) => (
                      <TableRow key={`${incident.event_ts}-${incident.client_id}-${index}`}>
                        <TableCell className="whitespace-nowrap text-xs text-muted-foreground">{formatAbsoluteTime(incident.event_ts)}</TableCell>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            <AlertTriangle className="h-3.5 w-3.5 text-amber-600" />
                            <span className="text-sm font-medium">{incidentLabel(incident.incident_type)}</span>
                          </div>
                        </TableCell>
                        <TableCell>{incident.username}</TableCell>
                        <TableCell className="font-mono text-xs">{incident.client_id}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {renderIncidentDetails(incident)}
                        </TableCell>
                      </TableRow>
                    )) : <EmptyRow colSpan={5} label={isLoading ? 'Loading incidents...' : 'No incidents match the selected filters.'} />}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}

function MetricCard({ title, value, hint, icon }: { title: string; value: string; hint: string; icon: React.ReactNode }) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="text-sm font-medium text-muted-foreground">{title}</CardTitle>
          <div className="rounded-full bg-primary/10 p-2 text-primary">{icon}</div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-semibold tracking-tight">{value}</div>
        <p className="mt-1 text-xs text-muted-foreground">{hint}</p>
      </CardContent>
    </Card>
  )
}

function MetricSubCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border bg-muted/30 p-4">
      <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-2 text-lg font-semibold">{value}</p>
    </div>
  )
}

function DataTableCard({ title, description, children }: { title: string; description: string; children: React.ReactNode }) {
  return (
    <Card className="h-full">
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="rounded-lg border">{children}</div>
      </CardContent>
    </Card>
  )
}

function RetentionMini({ label, value }: { label: string; value?: number }) {
  return (
    <div className="rounded-lg border bg-background p-3">
      <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-1 text-lg font-semibold">{value ?? '—'} days</p>
    </div>
  )
}

function EmptyRow({ colSpan, label }: { colSpan: number; label: string }) {
  return (
    <TableRow>
      <TableCell colSpan={colSpan} className="py-8 text-center text-sm text-muted-foreground">{label}</TableCell>
    </TableRow>
  )
}

function renderIncidentDetails(incident: ClientIncident) {
  if (incident.incident_type === 'reconnect_loop') {
    return `${incident.details.attempts ?? 0} reconnects between ${formatAbsoluteTime(incident.details.start_ts ?? incident.event_ts)} and ${formatAbsoluteTime(incident.details.end_ts ?? incident.event_ts)}`
  }
  const pieces = [incident.details.reason_code, incident.details.disconnect_kind]
    .filter(Boolean)
    .join(' · ')
  const endpoint = incident.details.ip_address ? ` @ ${incident.details.ip_address}:${incident.details.port ?? '—'}` : ''
  return `${pieces || 'No extra detail'}${endpoint}`
}