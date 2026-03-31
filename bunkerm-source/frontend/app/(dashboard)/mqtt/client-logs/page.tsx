'use client'

import React, { useCallback, useEffect, useState } from 'react'
import { Radio, RefreshCw, Send, ShieldAlert, Wifi, WifiOff } from 'lucide-react'
import { toast } from 'sonner'
import { clientlogsApi } from '@/lib/api'
import { formatAbsoluteTime } from '@/lib/timeUtils'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
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

function EventBadge({ event }: { event: MQTTEvent }) {
  switch (event.event_type) {
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
      return <Badge variant="secondary" className="text-xs">{event.event_type}</Badge>
  }
}

const EVENT_TYPES = [
  'Client Connection',
  'Client Disconnection',
  'Auth Failure',
  'Subscribe',
  'Publish',
] as const

export default function ClientLogsPage() {
  const [events, setEvents] = useState<MQTTEvent[]>([])
  const [search, setSearch] = useState('')
  const [activeTypes, setActiveTypes] = useState<Set<string>>(new Set(EVENT_TYPES))
  const [isLoading, setIsLoading] = useState(false)

  const fetchEvents = useCallback(async () => {
    setIsLoading(true)
    try {
      const data = await clientlogsApi.getEvents()
      setEvents((data.events ?? []) as MQTTEvent[])
    } catch {
      toast.error('Failed to fetch client events')
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchEvents()
    const interval = setInterval(fetchEvents, 10_000)
    return () => clearInterval(interval)
  }, [fetchEvents])

  function toggleType(type: string) {
    setActiveTypes((prev) => {
      const next = new Set(prev)
      if (next.has(type)) {
        // Keep at least one active
        if (next.size > 1) next.delete(type)
      } else {
        next.add(type)
      }
      return next
    })
  }

  const filtered = events.filter((e) => {
    if (!activeTypes.has(e.event_type)) return false
    if (!search) return true
    const q = search.toLowerCase()
    return (
      e.username?.toLowerCase().includes(q) ||
      e.client_id?.toLowerCase().includes(q) ||
      e.event_type?.toLowerCase().includes(q) ||
      e.ip_address?.toLowerCase().includes(q) ||
      e.topic?.toLowerCase().includes(q)
    )
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Client Logs</h1>
          <p className="text-muted-foreground text-sm">MQTT client events: connections, subscriptions, publishes and auth failures</p>
        </div>
        <Button variant="outline" size="sm" onClick={fetchEvents} disabled={isLoading}>
          <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      <div className="flex items-center gap-3">
        <Input
          placeholder="Filter by username, client ID, IP, topic..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-sm"
        />
        <Badge variant="secondary">{filtered.length} event{filtered.length !== 1 ? 's' : ''}</Badge>
      </div>

      {/* Event type filter chips */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-muted-foreground mr-1">Filter:</span>
        {EVENT_TYPES.map((type) => {
          const active = activeTypes.has(type)
          const chipMeta: Record<string, { icon: React.ReactNode; color: string }> = {
            'Client Connection':    { icon: <Wifi className="h-3 w-3" />,        color: 'text-green-600 border-green-300 bg-green-50 dark:bg-green-950/30' },
            'Client Disconnection': { icon: <WifiOff className="h-3 w-3" />,     color: 'text-red-600 border-red-300 bg-red-50 dark:bg-red-950/30' },
            'Auth Failure':         { icon: <ShieldAlert className="h-3 w-3" />, color: 'text-red-700 border-red-400 bg-red-100 dark:bg-red-950/40' },
            'Subscribe':            { icon: <Radio className="h-3 w-3" />,       color: 'text-blue-600 border-blue-300 bg-blue-50 dark:bg-blue-950/30' },
            'Publish':              { icon: <Send className="h-3 w-3" />,        color: 'text-orange-600 border-orange-300 bg-orange-50 dark:bg-orange-950/30' },
          }
          const meta = chipMeta[type]
          return (
            <button
              key={type}
              onClick={() => toggleType(type)}
              className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border transition-all ${
                active
                  ? meta.color
                  : 'text-muted-foreground border-border bg-background opacity-40 hover:opacity-70'
              }`}
            >
              {meta.icon}
              {type}
            </button>
          )
        })}
        {activeTypes.size < EVENT_TYPES.length && (
          <button
            onClick={() => setActiveTypes(new Set(EVENT_TYPES))}
            className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
          >
            Show all
          </button>
        )}
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">MQTT Events</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="rounded-md border-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Timestamp</TableHead>
                  <TableHead>Event</TableHead>
                  <TableHead>Username</TableHead>
                  <TableHead>Client ID</TableHead>
                  <TableHead>Topic</TableHead>
                  <TableHead>IP Address</TableHead>
                  <TableHead>Protocol</TableHead>
                  <TableHead>Details</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={8} className="text-center py-8 text-muted-foreground">
                      {isLoading ? 'Loading events...' : 'No events found.'}
                    </TableCell>
                  </TableRow>
                ) : (
                  filtered.map((event) => (
                    <TableRow key={event.id}>
                      <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                        {formatAbsoluteTime(event.timestamp)}
                      </TableCell>
                      <TableCell>
                        <EventBadge event={event} />
                      </TableCell>
                      <TableCell className="font-medium">{event.username || '—'}</TableCell>
                      <TableCell className="font-mono text-xs">{event.client_id || '—'}</TableCell>
                      <TableCell className="font-mono text-xs text-muted-foreground">
                        {event.topic ?? '—'}
                      </TableCell>
                      <TableCell className="text-xs">{event.ip_address}:{event.port}</TableCell>
                      <TableCell className="text-xs">{event.protocol_level}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">{event.details}</TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
