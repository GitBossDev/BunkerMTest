'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { ChevronDown, RefreshCw, ArrowDown } from 'lucide-react'
import { toast } from 'sonner'
import { monitorApi } from '@/lib/api'
import { exportLogs, type ExportFormat } from '@/lib/export-logs'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

interface LogLine {
  raw: string
  timestamp?: string
  level?: string
  message?: string
}

function parseLine(line: string): LogLine {
  // Try to parse: "1234567890: Notice: message"
  const match = line.match(/^(\d+):\s+(Notice|Warning|Error|Info|Debug):\s+(.+)$/i)
  if (match) {
    const ts = new Date(parseInt(match[1]) * 1000).toLocaleTimeString()
    return { raw: line, timestamp: ts, level: match[2], message: match[3] }
  }
  return { raw: line }
}

function getLevelVariant(level?: string): 'default' | 'destructive' | 'warning' | 'secondary' {
  switch (level?.toLowerCase()) {
    case 'error': return 'destructive'
    case 'warning': return 'warning'
    case 'notice':
    case 'info': return 'secondary'
    default: return 'default'
  }
}

export default function BrokerLogsPage() {
  const [logs, setLogs] = useState<LogLine[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [autoScroll, setAutoScroll] = useState(true)
  const [fetchError, setFetchError] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  const fetchLogs = useCallback(async (silent = false) => {
    if (!silent) setIsLoading(true)
    try {
      const data = await monitorApi.getBrokerLogs()
      const lines = (data.logs || []).map(parseLine)
      setLogs(lines)
      setFetchError(null)
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Unknown error'
      setFetchError(msg)
      if (!silent) toast.error('Failed to fetch broker logs')
    } finally {
      if (!silent) setIsLoading(false)
    }
  }, [])

  // Initial load
  useEffect(() => {
    fetchLogs()
  }, [fetchLogs])

  // Auto-refresh every 30 seconds — retries silently even after an error
  useEffect(() => {
    const id = setInterval(() => fetchLogs(true), 30_000)
    return () => clearInterval(id)
  }, [fetchLogs])

  useEffect(() => {
    if (autoScroll) bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs, autoScroll])

  const downloadLogs = (format: ExportFormat) => {
    if (format === 'txt') {
      exportLogs(
        logs,
        'txt',
        [{ header: 'Log', value: l => l.raw }],
        'broker-logs'
      )
    } else {
      exportLogs(
        logs,
        'csv',
        [
          { header: 'Timestamp', value: l => l.timestamp ?? '' },
          { header: 'Level',     value: l => l.level ?? '' },
          { header: 'Message',   value: l => l.message ?? l.raw },
        ],
        'broker-logs'
      )
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Broker Logs</h1>
          <p className="text-muted-foreground text-sm">Mosquitto broker log output</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => setAutoScroll(!autoScroll)}>
            <ArrowDown className={`h-4 w-4 ${autoScroll ? 'text-primary' : ''}`} />
            Auto-scroll {autoScroll ? 'On' : 'Off'}
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm" disabled={logs.length === 0}>
                Export
                <ChevronDown className="h-3 w-3 ml-1" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => downloadLogs('csv')}>CSV</DropdownMenuItem>
              <DropdownMenuItem onClick={() => downloadLogs('txt')}>TXT</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <Button variant="outline" size="sm" onClick={() => fetchLogs()} disabled={isLoading}>
            <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </div>
      </div>

      {fetchError && (
        <div className="flex items-center gap-3 rounded-md border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          <RefreshCw className="h-4 w-4 shrink-0" />
          <span className="flex-1">
            Could not reach the broker observability service. Retrying automatically every 30 s.
            <span className="ml-1 opacity-70">({fetchError})</span>
          </span>
          <Button variant="ghost" size="sm" className="h-6 text-xs" onClick={() => fetchLogs()}>
            Retry now
          </Button>
        </div>
      )}

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            Log Output
            <Badge variant="secondary">{logs.length} lines</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <ScrollArea className="h-[calc(100vh-280px)] w-full">
            <div className="font-mono text-xs space-y-0.5 p-2 bg-muted/50 rounded-md min-h-[200px]">
              {logs.length === 0 ? (
                <div className="text-muted-foreground text-center py-8">
                  {isLoading ? 'Loading logs...' : 'No logs available'}
                </div>
              ) : (
                logs.map((log, i) => (
                  <div key={i} className="flex items-start gap-2 py-0.5 hover:bg-muted/80 px-1 rounded">
                    {log.timestamp && (
                      <span className="text-muted-foreground shrink-0">{log.timestamp}</span>
                    )}
                    {log.level && (
                      <Badge variant={getLevelVariant(log.level)} className="text-[10px] py-0 px-1 shrink-0">
                        {log.level}
                      </Badge>
                    )}
                    <span className="break-all">{log.message || log.raw}</span>
                  </div>
                ))
              )}
              <div ref={bottomRef} />
            </div>
          </ScrollArea>
        </CardContent>
      </Card>
    </div>
  )
}
