'use client'

import { useCallback, useEffect, useState } from 'react'
import { RefreshCw, Wifi, WifiOff, Ban, Search, Power, PowerOff, ChevronLeft, ChevronRight, Timer, MoreHorizontal } from 'lucide-react'
import { toast } from 'sonner'
import { dynsecApi, clientlogsApi, monitorApi } from '@/lib/api'
import { formatAbsoluteTime } from '@/lib/timeUtils'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import type { MQTTEvent } from '@/types'

const PAGE_SIZE = 50

type ClientStatus = 'connected' | 'disabled' | 'offline'

interface ClientRow {
  username: string
  status: ClientStatus
  ip_address?: string
  port?: number
  protocol_level?: string
  keep_alive?: number
  connectedAt?: string
}

/** Returns a compact list of page numbers + '...' separators for ellipsis pagination. */
function buildPageNumbers(current: number, total: number): (number | '...')[] {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1)
  const pages: (number | '...')[] = [1]
  if (current > 3) pages.push('...')
  for (let p = Math.max(2, current - 1); p <= Math.min(total - 1, current + 1); p++) pages.push(p)
  if (current < total - 2) pages.push('...')
  pages.push(total)
  return pages
}

export default function ConnectedClientsPage() {
  const ADMIN_USERNAME = 'admin'
  const [allUsernames, setAllUsernames] = useState<string[]>([])
  // username → MQTTEvent for currently connected clients (deduplicated by username)
  const [connectedMap, setConnectedMap] = useState<Map<string, MQTTEvent>>(new Map())
  // username → last known connection info (for offline display)
  const [lastConnectionInfo, setLastConnectionInfo] = useState<Record<string, { ip_address: string; port: number; timestamp: string }>>({})
  // username → disabled status from API + local overrides
  const [disabledState, setDisabledState] = useState<Record<string, boolean>>({})
  const [isLoading, setIsLoading] = useState(false)
  const [isInitialLoading, setIsInitialLoading] = useState(true)
  const [actionUsername, setActionUsername] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [statusFilter, setStatusFilter] = useState<'all' | 'connected' | 'offline' | 'disabled'>('all')
  const [brokerLatencyMs, setBrokerLatencyMs] = useState<number | null>(null)

  // Full load: fetch all clients + disabled state from a single JSON read (no N+1)
  const loadFull = useCallback(async () => {
    setIsLoading(true)
    try {
      const res = await dynsecApi.getClientsDisabledMap()
      setAllUsernames(res.usernames)
      setDisabledState(res.map)
    } catch {
      toast.error('Failed to load clients')
    } finally {
      setIsLoading(false)
    }
  }, [])

  // Light poll: only update connected clients (no N+1 detail fetches)
  const fetchConnected = useCallback(async () => {
    try {
      const [data, healthData] = await Promise.allSettled([
        clientlogsApi.getConnectedClients(),
        monitorApi.getHealthStats(),
      ])
      if (data.status === 'fulfilled') {
        // Deduplicate by username — keep first entry per username
        const map = new Map<string, MQTTEvent>()
        for (const ev of (data.value.clients ?? []) as MQTTEvent[]) {
          if (ev.username && !map.has(ev.username)) {
            map.set(ev.username, ev)
          }
        }
        setConnectedMap(map)
      }
      if (healthData.status === 'fulfilled') {
        const ms = (healthData.value as { latency_ms?: number }).latency_ms
        if (typeof ms === 'number' && ms >= 0) setBrokerLatencyMs(ms)
      }
      // Fetch last connection info for offline client IPs
      try {
        const lastConn = await clientlogsApi.getLastConnection()
        setLastConnectionInfo(lastConn.info ?? {})
      } catch {
        // non-critical
      }
    } catch {
      // Silently fail on poll errors
    }
  }, [])

  // Initial load + start 5s poll
  useEffect(() => {
    const init = async () => {
      await loadFull()
      await fetchConnected()
      setIsInitialLoading(false)
    }
    init()
    const interval = setInterval(fetchConnected, 5000)
    return () => clearInterval(interval)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleRefresh = async () => {
    await loadFull()
    await fetchConnected()
  }

  const handleDisable = async (username: string) => {
    setActionUsername(username)
    try {
      await dynsecApi.disableClient(username)
      setDisabledState((prev) => ({ ...prev, [username]: true }))
      toast.success(`Client "${username}" disabled`)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : `Failed to disable "${username}"`)
    } finally {
      setActionUsername(null)
    }
  }

  const handleEnable = async (username: string) => {
    setActionUsername(username)
    try {
      await dynsecApi.enableClient(username)
      setDisabledState((prev) => ({ ...prev, [username]: false }))
      toast.success(`Client "${username}" enabled`)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : `Failed to enable "${username}"`)
    } finally {
      setActionUsername(null)
    }
  }

  // Compute display rows by merging ACL list + live connection data + disabled state
  const rows: ClientRow[] = allUsernames.map((username) => {
    const isDisabled = disabledState[username] ?? false
    const connInfo = connectedMap.get(username)
    const lastConn = lastConnectionInfo[username]

    let status: ClientStatus = 'offline'
    if (isDisabled) status = 'disabled'
    else if (connInfo) status = 'connected'

    return {
      username,
      status,
      ip_address: connInfo?.ip_address ?? (status !== 'connected' ? lastConn?.ip_address : undefined),
      port: connInfo?.port ?? (status !== 'connected' ? lastConn?.port : undefined),
      protocol_level: connInfo?.protocol_level,
      keep_alive: connInfo?.keep_alive,
      connectedAt: connInfo?.timestamp,
    }
  })

  const filtered = rows.filter((r) => {
    if (search && !r.username.toLowerCase().includes(search.toLowerCase())) return false
    if (statusFilter !== 'all' && r.status !== statusFilter) return false
    return true
  })

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const safePage = Math.min(page, totalPages)
  const paginated = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE)

  const connectedCount = rows.filter((r) => r.status === 'connected').length
  const disabledCount = rows.filter((r) => r.status === 'disabled').length

  if (isInitialLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="flex flex-col items-center gap-3 text-muted-foreground">
          <RefreshCw className="h-6 w-6 animate-spin" />
          <p className="text-sm">Loading clients...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Connected Clients</h1>
          <p className="text-muted-foreground text-sm">
            All MQTT clients — live connection status updates every 5s
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="success" className="gap-1">
            <Wifi className="h-3 w-3" />
            {connectedCount} online
          </Badge>
          {disabledCount > 0 && (
            <Badge variant="destructive" className="gap-1">
              <Ban className="h-3 w-3" />
              {disabledCount} disabled
            </Badge>
          )}
          {brokerLatencyMs !== null && (
            <Badge variant="secondary" className="gap-1" title="Broker round-trip latency (monitor ping)">
              <Timer className="h-3 w-3" />
              RTT {brokerLatencyMs} ms
            </Badge>
          )}
          <Button variant="outline" size="sm" onClick={handleRefresh} disabled={isLoading}>
            <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search clients..."
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1) }}
            className="pl-9 w-64"
          />
        </div>
        {(['all', 'connected', 'offline', 'disabled'] as const).map((s) => (
          <Button
            key={s}
            variant={statusFilter === s ? 'default' : 'outline'}
            size="sm"
            onClick={() => { setStatusFilter(s); setPage(1) }}
            className="capitalize"
          >
            {s === 'all' ? `All (${rows.length})` :
             s === 'connected' ? `Online (${connectedCount})` :
             s === 'offline' ? `Offline (${rows.filter(r => r.status === 'offline').length})` :
             `Disabled (${disabledCount})`}
          </Button>
        ))}
      </div>

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Username</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>IP Address</TableHead>
              <TableHead>Protocol</TableHead>
              <TableHead>Keep-Alive</TableHead>
              <TableHead>Connected At</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} className="text-center py-8 text-muted-foreground">
                  {isLoading ? 'Loading...' : search ? 'No clients match your search.' : 'No clients found.'}
                </TableCell>
              </TableRow>
            ) : (
              paginated.map((row) => (
                <TableRow key={row.username}>
                  <TableCell className="font-medium">{row.username}</TableCell>

                  <TableCell>
                    {row.status === 'connected' && (
                      <Badge variant="success" className="gap-1">
                        <Wifi className="h-3 w-3" />
                        Connected
                      </Badge>
                    )}
                    {row.status === 'disabled' && (
                      <Badge variant="destructive" className="gap-1">
                        <Ban className="h-3 w-3" />
                        Disabled
                      </Badge>
                    )}
                    {row.status === 'offline' && (
                      <Badge variant="secondary" className="gap-1">
                        <WifiOff className="h-3 w-3" />
                        Offline
                      </Badge>
                    )}
                  </TableCell>

                  <TableCell className="text-sm text-muted-foreground">
                    {row.ip_address ? (
                      <span>
                        {`${row.ip_address}:${row.port}`}
                        {row.status !== 'connected' && (
                          <span className="ml-1 text-xs text-muted-foreground/60">(last seen)</span>
                        )}
                      </span>
                    ) : '—'}
                  </TableCell>

                  <TableCell>
                    {row.protocol_level ? (
                      <Badge variant="outline" className="text-xs">{row.protocol_level}</Badge>
                    ) : '—'}
                  </TableCell>

                  <TableCell className="text-sm text-muted-foreground">
                    {row.keep_alive != null ? `${row.keep_alive}s` : '—'}
                  </TableCell>

                  <TableCell className="text-xs text-muted-foreground">
                    {row.connectedAt ? formatAbsoluteTime(row.connectedAt) : '—'}
                  </TableCell>

                  <TableCell>
                    <div className="flex items-center justify-end">
                      {row.username !== ADMIN_USERNAME && (
                        row.status === 'disabled' ? (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleEnable(row.username)}
                            disabled={actionUsername === row.username}
                            className="text-green-600 hover:text-green-600 hover:bg-green-50 gap-1"
                          >
                            <Power className="h-3.5 w-3.5" />
                            Enable
                          </Button>
                        ) : (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleDisable(row.username)}
                            disabled={actionUsername === row.username}
                            className="text-destructive hover:text-destructive hover:bg-destructive/10 gap-1"
                          >
                            <PowerOff className="h-3.5 w-3.5" />
                            Disable
                          </Button>
                        )
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>{filtered.length} of {rows.length} client{rows.length !== 1 ? 's' : ''}</span>
        {totalPages > 1 && (
          <div className="flex items-center gap-1">
            <Button variant="ghost" size="sm" className="h-7 px-2" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={safePage <= 1}>
              <ChevronLeft className="h-3.5 w-3.5" />
            </Button>
            {buildPageNumbers(safePage, totalPages).map((p, i) =>
              p === '...' ? (
                <span key={`ellipsis-${i}`} className="flex items-center justify-center h-7 w-7 text-muted-foreground">
                  <MoreHorizontal className="h-3.5 w-3.5" />
                </span>
              ) : (
                <Button
                  key={p}
                  variant={p === safePage ? 'secondary' : 'ghost'}
                  size="sm"
                  className="h-7 w-7 p-0 text-xs"
                  onClick={() => setPage(p as number)}
                >
                  {p}
                </Button>
              )
            )}
            <Button variant="ghost" size="sm" className="h-7 px-2" onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={safePage >= totalPages}>
              <ChevronRight className="h-3.5 w-3.5" />
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}
