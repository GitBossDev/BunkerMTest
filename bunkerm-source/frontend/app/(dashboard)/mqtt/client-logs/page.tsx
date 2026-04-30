'use client'

// ── REDESIGNED CLIENT LOGS PAGE ───────────────────────────────────────────────
// Shows a paginated client list (50/page) with last interaction per client.
// Clicking a row opens a detail modal (session events, subscriptions, publish topics).
// Export button lives inside the modal, not on the main page.

import React, { useCallback, useEffect, useState } from 'react'
import {
  Ban, ChevronDown, ChevronLeft, ChevronRight, FileText, MoreHorizontal,
  Radio, RefreshCw, Search, Send, ShieldAlert, Wifi, WifiOff,
} from 'lucide-react'
import { toast } from 'sonner'
import { clientlogsApi } from '@/lib/api'
import { exportLogs, type ExportFormat } from '@/lib/export-logs'
import { formatAbsoluteTime } from '@/lib/timeUtils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import type {
  ClientActivityResponse,
  ClientListLogResponse,
  ClientLogRow,
} from '@/types'

const PAGE_SIZE = 50

// ── helpers ──────────────────────────────────────────────────────────────────

function buildPageNumbers(current: number, total: number): (number | '...')[] {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1)
  const pages: (number | '...')[] = [1]
  if (current > 3) pages.push('...')
  for (let p = Math.max(2, current - 1); p <= Math.min(total - 1, current + 1); p++) pages.push(p)
  if (current < total - 2) pages.push('...')
  pages.push(total)
  return pages
}

function EventTypeBadge({ type }: { type: string | null }) {
  if (!type) return <span className="text-muted-foreground">—</span>
  switch (type) {
    case 'Client Connection':
      return (
        <div className="flex items-center gap-1.5">
          <Wifi className="h-3.5 w-3.5 text-green-500" />
          <Badge variant="success" className="text-xs">Connection</Badge>
        </div>
      )
    case 'Client Disconnection':
      return (
        <div className="flex items-center gap-1.5">
          <WifiOff className="h-3.5 w-3.5 text-destructive" />
          <Badge variant="destructive" className="text-xs">Disconnection</Badge>
        </div>
      )
    case 'Auth Failure':
      return (
        <div className="flex items-center gap-1.5">
          <ShieldAlert className="h-3.5 w-3.5 text-destructive" />
          <Badge variant="destructive" className="text-xs">Auth Failure</Badge>
        </div>
      )
    case 'Subscribe':
      return (
        <div className="flex items-center gap-1.5">
          <Radio className="h-3.5 w-3.5 text-blue-500" />
          <Badge variant="secondary" className="text-xs text-blue-600">Subscribe</Badge>
        </div>
      )
    case 'Publish':
      return (
        <div className="flex items-center gap-1.5">
          <Send className="h-3.5 w-3.5 text-orange-500" />
          <Badge variant="outline" className="text-xs text-orange-600">Publish</Badge>
        </div>
      )
    default:
      return <Badge variant="secondary" className="text-xs">{type}</Badge>
  }
}

// ── Client Detail Modal ───────────────────────────────────────────────────────

interface ClientDetailModalProps {
  username: string | null
  open: boolean
  onOpenChange: (v: boolean) => void
}

function ClientDetailModal({ username, open, onOpenChange }: ClientDetailModalProps) {
  const [activity, setActivity] = useState<ClientActivityResponse | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!open || !username) {
      setActivity(null)
      return
    }
    setLoading(true)
    clientlogsApi.getActivity(username)
      .then(setActivity)
      .catch(() => toast.error(`Failed to load activity for "${username}"`))
      .finally(() => setLoading(false))
  }, [open, username])

  const exportActivity = (format: ExportFormat) => {
    if (!activity) return
    const rows = [
      ...activity.session_events.map(e => ({
        event_ts: e.event_ts,
        event_type: e.event_type,
        client_id: e.client_id,
        ip_address: e.ip_address ?? '',
        port: String(e.port ?? ''),
        detail: e.disconnect_kind ?? e.reason_code ?? '',
        topic: '',
      })),
      ...activity.topic_events.map(e => ({
        event_ts: e.event_ts,
        event_type: e.event_type,
        client_id: e.client_id,
        ip_address: '',
        port: '',
        detail: '',
        topic: e.topic ?? '',
      })),
    ].sort((a, b) => b.event_ts.localeCompare(a.event_ts))

    exportLogs(
      rows,
      format,
      [
        { header: 'Timestamp', value: r => r.event_ts },
        { header: 'Event', value: r => r.event_type },
        { header: 'Client ID', value: r => r.client_id },
        { header: 'IP Address', value: r => r.port ? `${r.ip_address}:${r.port}` : r.ip_address },
        { header: 'Topic', value: r => r.topic },
        { header: 'Detail', value: r => r.detail },
      ],
      `client-activity-${username}`
    )
  }

  const client = activity?.client

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[760px] max-h-[85vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>
            Activity
            {username && (
              <span className="ml-2 text-sm font-normal text-muted-foreground">
                — {username}
              </span>
            )}
          </DialogTitle>
        </DialogHeader>

        {loading ? (
          <div className="flex items-center justify-center py-12 text-muted-foreground">
            <RefreshCw className="h-5 w-5 animate-spin mr-2" />
            Loading...
          </div>
        ) : activity ? (
          <ScrollArea className="flex-1 overflow-auto pr-1">
            <div className="space-y-5 pb-2">
              {/* Client info */}
              {client && (client.disabled || client.textname) && (
                <div className="flex flex-wrap gap-2 items-center">
                  {client.disabled && (
                    <Badge variant="destructive" className="gap-1">
                      <Ban className="h-3 w-3" />
                      Disabled
                    </Badge>
                  )}
                  {client.textname && (
                    <span className="text-sm text-muted-foreground">
                      Display name: <span className="text-foreground">{client.textname}</span>
                    </span>
                  )}
                </div>
              )}

              {/* Session events */}
              <div className="space-y-2">
                <Label className="text-sm font-medium">
                  Session Events
                  <span className="ml-1.5 text-muted-foreground font-normal">
                    ({activity.session_events.length})
                  </span>
                </Label>
                {activity.session_events.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No session events recorded.</p>
                ) : (
                  <div className="rounded-md border text-sm">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead className="h-8 text-xs">Timestamp</TableHead>
                          <TableHead className="h-8 text-xs">Event</TableHead>
                          <TableHead className="h-8 text-xs">Client ID</TableHead>
                          <TableHead className="h-8 text-xs">IP Address</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {activity.session_events.map((ev) => (
                          <TableRow key={ev.id}>
                            <TableCell className="text-xs text-muted-foreground whitespace-nowrap py-1.5">
                              {formatAbsoluteTime(ev.event_ts)}
                            </TableCell>
                            <TableCell className="py-1.5">
                              <EventTypeBadge type={ev.event_type} />
                            </TableCell>
                            <TableCell className="font-mono text-xs py-1.5">{ev.client_id}</TableCell>
                            <TableCell className="text-xs text-muted-foreground py-1.5">
                              {ev.ip_address ? `${ev.ip_address}:${ev.port}` : '—'}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                )}
              </div>

              {/* Topic events (subscribe + publish unified) */}
              <div className="space-y-2">
                <Label className="text-sm font-medium">
                  Topic Events
                  <span className="ml-1.5 text-muted-foreground font-normal">
                    ({activity.topic_events.length})
                  </span>
                </Label>
                {activity.topic_events.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No topic events recorded.</p>
                ) : (
                  <div className="rounded-md border text-sm">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead className="h-8 text-xs">Timestamp</TableHead>
                          <TableHead className="h-8 text-xs">Type</TableHead>
                          <TableHead className="h-8 text-xs">Topic</TableHead>
                          <TableHead className="h-8 text-xs">QoS</TableHead>
                          <TableHead className="h-8 text-xs">Bytes</TableHead>
                          <TableHead className="h-8 text-xs">Retained</TableHead>
                          <TableHead className="h-8 text-xs">Client ID</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {activity.topic_events.map((ev) => (
                          <TableRow key={ev.id}>
                            <TableCell className="text-xs text-muted-foreground whitespace-nowrap py-1.5">
                              {formatAbsoluteTime(ev.event_ts)}
                            </TableCell>
                            <TableCell className="py-1.5">
                              <EventTypeBadge type={ev.event_type} />
                            </TableCell>
                            <TableCell className="font-mono text-xs py-1.5 max-w-[180px] truncate" title={ev.topic ?? undefined}>
                              {ev.topic ?? '—'}
                            </TableCell>
                            <TableCell className="text-xs text-muted-foreground py-1.5">
                              {ev.qos != null ? `QoS${ev.qos}` : '—'}
                            </TableCell>
                            <TableCell className="text-xs text-muted-foreground py-1.5">
                              {ev.payload_bytes != null ? `${ev.payload_bytes} B` : '—'}
                            </TableCell>
                            <TableCell className="text-xs text-muted-foreground py-1.5">
                              {ev.retained != null ? (ev.retained ? 'Yes' : 'No') : '—'}
                            </TableCell>
                            <TableCell className="font-mono text-xs text-muted-foreground py-1.5">{ev.client_id}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                )}
              </div>
            </div>
          </ScrollArea>
        ) : null}

        <DialogFooter className="gap-2 pt-2">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="outline"
                size="sm"
                disabled={!activity || (activity.session_events.length === 0 && activity.topic_events.length === 0)}
              >
                Export
                <ChevronDown className="h-3 w-3 ml-1" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => exportActivity('csv')}>CSV</DropdownMenuItem>
              <DropdownMenuItem onClick={() => exportActivity('txt')}>TXT</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function ClientLogsPage() {
  const [data, setData] = useState<ClientListLogResponse | null>(null)
  const [search, setSearch] = useState('')
  const [exactSearch, setExactSearch] = useState(false)
  const [page, setPage] = useState(1)
  const [isLoading, setIsLoading] = useState(false)

  const [selectedUsername, setSelectedUsername] = useState<string | null>(null)
  const [modalOpen, setModalOpen] = useState(false)

  const fetchClients = useCallback(async (currentPage: number, currentSearch: string, currentExact: boolean) => {
    setIsLoading(true)
    try {
      const res = await clientlogsApi.getClients({
        page: currentPage,
        limit: PAGE_SIZE,
        search: currentSearch || undefined,
        exact: currentExact || undefined,
      })
      setData(res)
    } catch {
      toast.error('Failed to fetch client list')
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchClients(page, search, exactSearch)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, search, exactSearch])

  const handleSearch = (value: string) => {
    setSearch(value)
    setPage(1)
  }

  const handleExactToggle = (checked: boolean) => {
    setExactSearch(checked)
    setPage(1)
  }

  const handleRowClick = (username: string) => {
    setSelectedUsername(username)
    setModalOpen(true)
  }

  const clients = data?.clients ?? []
  const total = data?.total ?? 0
  const totalPages = data?.pages ?? 1

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Client Logs</h1>
          <p className="text-muted-foreground text-sm">
            MQTT clients — use the View Logs button to inspect activity per client
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => fetchClients(page, search, exactSearch)}
          disabled={isLoading}
        >
          <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      {/* Search + exact toggle */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search clients..."
            value={search}
            onChange={(e) => handleSearch(e.target.value)}
            className="pl-9 w-64"
          />
        </div>
        <label className="flex items-center gap-1.5 text-sm text-muted-foreground cursor-pointer select-none">
          <input
            type="checkbox"
            checked={exactSearch}
            onChange={(e) => handleExactToggle(e.target.checked)}
            className="h-3.5 w-3.5 rounded border-muted accent-primary"
          />
          Exact
        </label>
        <Badge variant="secondary">{total} client{total !== 1 ? 's' : ''}</Badge>
      </div>

      {/* Table */}
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Username</TableHead>
              <TableHead>Last Activity</TableHead>
              <TableHead>Timestamp</TableHead>
              <TableHead>IP Address</TableHead>
              <TableHead>Client ID</TableHead>
              <TableHead className="w-[120px]"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {clients.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="text-center py-8 text-muted-foreground">
                  {isLoading ? 'Loading...' : search ? 'No clients match your search.' : 'No clients found.'}
                </TableCell>
              </TableRow>
            ) : (
              clients.map((row: ClientLogRow) => (
                <TableRow key={row.username} className="hover:bg-muted/50">
                  <TableCell className="font-medium">
                    <div className="flex items-center gap-2">
                      {row.username}
                      {row.disabled && (
                        <Badge variant="destructive" className="text-xs gap-1">
                          <Ban className="h-2.5 w-2.5" />
                          Disabled
                        </Badge>
                      )}
                    </div>
                  </TableCell>
                  <TableCell>
                    <EventTypeBadge type={row.last_event_type} />
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                    {row.last_event_ts ? formatAbsoluteTime(row.last_event_ts) : '—'}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {row.last_ip_address
                      ? `${row.last_ip_address}${row.last_port ? `:${row.last_port}` : ''}`
                      : '—'}
                  </TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">
                    {row.last_client_id ?? '—'}
                  </TableCell>
                  <TableCell>
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-7 text-xs gap-1.5"
                      onClick={() => handleRowClick(row.username)}
                    >
                      <FileText className="h-3.5 w-3.5" />
                      View Logs
                    </Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>
          {clients.length > 0
            ? `Showing ${(page - 1) * PAGE_SIZE + 1}–${Math.min(page * PAGE_SIZE, total)} of ${total}`
            : `${total} client${total !== 1 ? 's' : ''}`}
        </span>
        {totalPages > 1 && (
          <div className="flex items-center gap-1">
            <Button
              variant="ghost" size="sm" className="h-7 px-2"
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page <= 1}
            >
              <ChevronLeft className="h-3.5 w-3.5" />
            </Button>
            {buildPageNumbers(page, totalPages).map((p, i) =>
              p === '...' ? (
                <span key={`ellipsis-${i}`} className="flex items-center justify-center h-7 w-7 text-muted-foreground">
                  <MoreHorizontal className="h-3.5 w-3.5" />
                </span>
              ) : (
                <Button
                  key={p}
                  variant={p === page ? 'secondary' : 'ghost'}
                  size="sm"
                  className="h-7 w-7 p-0 text-xs"
                  onClick={() => setPage(p as number)}
                >
                  {p}
                </Button>
              )
            )}
            <Button
              variant="ghost" size="sm" className="h-7 px-2"
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
            >
              <ChevronRight className="h-3.5 w-3.5" />
            </Button>
          </div>
        )}
      </div>

      <ClientDetailModal
        username={selectedUsername}
        open={modalOpen}
        onOpenChange={setModalOpen}
      />
    </div>
  )
}
