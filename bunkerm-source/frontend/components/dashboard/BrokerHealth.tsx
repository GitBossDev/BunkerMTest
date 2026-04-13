'use client'

import { useEffect, useState } from 'react'
import { Activity } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { InfoTooltip, TipRow } from '@/components/ui/info-tooltip'
import { monitorApi } from '@/lib/api'
import type { MonitorStats } from '@/types'

interface BrokerHealthProps {
  stats: MonitorStats | null
  isOffline?: boolean
  snapshotLabel?: string
}

function formatBytes(bps: number): string {
  if (bps < 1024)       return `${bps.toFixed(1)} B/s`
  if (bps < 1024 * 1024) return `${(bps / 1024).toFixed(1)} KB/s`
  return `${(bps / (1024 * 1024)).toFixed(2)} MB/s`
}

function latencyColor(ms: number): string {
  if (ms < 0)   return 'text-muted-foreground'
  if (ms < 50)  return 'text-green-500'
  if (ms < 200) return 'text-yellow-500'
  return 'text-red-500'
}

function parseVersion(raw?: string): string {
  if (!raw) return '—'
  const match = raw.match(/(\d+\.\d+[\d.]*)/)
  return match ? match[1] : raw
}

function parseUptime(raw?: string): string {
  if (!raw) return '—'
  const match = raw.match(/^(\d+)\s*seconds?$/i)
  if (!match) return raw

  const seconds = parseInt(match[1], 10)
  if (seconds < 60) return `${seconds}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`
  return `${Math.floor(seconds / 86400)}d ${Math.floor((seconds % 86400) / 3600)}h`
}

function formatMemory(bytes: number | null): string {
  if (bytes === null || bytes === undefined) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

function clampPercent(value: number | null): number {
  if (value === null || Number.isNaN(value)) return 0
  return Math.max(0, Math.min(value, 100))
}

function formatUsageOverLimit(used: string, limit: string): string {
  if (used === '—') return '—'
  return `${used} / ${limit}`
}

export function BrokerHealth({ stats, isOffline = false, snapshotLabel }: BrokerHealthProps) {
  const rxByte = stats?.load_bytes_rx_1min ?? 0
  const txByte = stats?.load_bytes_tx_1min ?? 0
  const latency  = stats?.latency_ms ?? -1
  const connected = stats?.mqtt_connected ?? false
  const version = parseVersion(stats?.broker_version)
  const uptime = connected ? parseUptime(stats?.broker_uptime) : 'Offline'

  const [cpu, setCpu] = useState<number | null>(null)
  const [rss, setRss] = useState<number | null>(null)
  const [memoryLimit, setMemoryLimit] = useState<number | null>(null)
  const [memoryPct, setMemoryPct] = useState<number | null>(null)
  const [cpuLimitPct, setCpuLimitPct] = useState<number | null>(null)

  useEffect(() => {
    let mounted = true

    const fetchResources = async () => {
      try {
        const resourceStats = await monitorApi.getResourceStats()
        if (mounted) {
          setCpu(resourceStats.mosquitto_cpu_pct)
          setRss(resourceStats.mosquitto_rss_bytes)
          setMemoryLimit(resourceStats.mosquitto_memory_limit_bytes ?? null)
          setMemoryPct(resourceStats.mosquitto_memory_pct ?? null)
          setCpuLimitPct(resourceStats.mosquitto_cpu_limit_cores !== null && resourceStats.mosquitto_cpu_limit_cores !== undefined ? 100 : null)
        }
      } catch {
        if (mounted) {
          setCpu(null)
          setRss(null)
          setMemoryLimit(null)
          setMemoryPct(null)
          setCpuLimitPct(null)
        }
      }
    }

    fetchResources()
    const intervalId = setInterval(fetchResources, 10_000)
    return () => {
      mounted = false
      clearInterval(intervalId)
    }
  }, [])

  const latencyLabel = latency < 0 ? '—' : `${Math.round(latency)} ms`
  const cpuCombinedLabel = !connected
    ? '—'
    : cpu !== null
      ? (cpuLimitPct !== null ? `${cpu.toFixed(1)} % / 100%` : `${cpu.toFixed(1)} %`)
      : '—'
  const ramCombinedLabel = !connected
    ? '—'
    : rss !== null
      ? (memoryLimit !== null ? formatUsageOverLimit(formatMemory(rss), formatMemory(memoryLimit)) : formatMemory(rss))
      : '—'
  const cpuGaugeValue = clampPercent(connected ? cpu : null)
  const ramGaugeValue = clampPercent(connected ? memoryPct : null)

  return (
    <Card className="h-full">
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <div>
          <div className="flex items-center gap-2">
            <CardTitle className="text-sm font-medium">Broker Health</CardTitle>
            <span className="text-xs text-muted-foreground">Mosquitto {version}</span>
            <InfoTooltip content={
              <>
                <p className="font-semibold text-foreground mb-1">Broker Performance</p>
                <TipRow label="Version" text="Eclipse Mosquitto version reported by the broker." />
                <TipRow label="Uptime" text="How long the current Mosquitto process has been running." />
                <TipRow label="Broker CPU" text="Collected directly inside the Mosquitto container from cgroups, not from $SYS. If there is no explicit CPU limit, the percentage falls back to host capacity." />
                <TipRow label="Broker RAM" text="Collected directly from the Mosquitto container cgroup memory counters, not from $SYS. If no memory limit exists, the dashboard shows current usage only." />
                <TipRow label="Latency" text="Round-trip time: the monitor publishes a ping to the broker and measures the response time. Green &lt;50ms · Yellow &lt;200ms · Red &gt;200ms." />
                <TipRow label="Bytes RX/TX" text="Current byte rate received and sent by the broker, reported by Mosquitto over the last minute." />
              </>
            } />
          </div>
          {isOffline && (
            <p className="text-xs text-amber-700 mt-1">Live rates paused. Last broker sample: {snapshotLabel ?? 'before disconnection'}.</p>
          )}
        </div>
        <div className="p-2 rounded-lg bg-emerald-500/10">
          <Activity className="h-4 w-4 text-emerald-500" />
        </div>
      </CardHeader>
      <CardContent className="h-full">
        <div className="grid grid-cols-2 gap-x-6 gap-y-4">
          <Metric label="Uptime"       value={uptime}                         accent="text-foreground" />
          <Metric label="Latency"      value={latency < 0 ? '—' : `${Math.round(latency)} ms`} accent={latencyColor(latency)} />
          <Metric label="Bytes RX"     value={formatBytes(rxByte)}           accent="text-blue-400" />
          <Metric label="Bytes TX"     value={formatBytes(txByte)}           accent="text-green-400" />
          <GaugeMetric label="CPU Usage" value={cpuCombinedLabel} percent={cpuGaugeValue} accent="bg-emerald-500" />
          <GaugeMetric label="RAM Usage" value={ramCombinedLabel} percent={ramGaugeValue} accent="bg-sky-500" />
        </div>
        {cpu === null && connected && (
          <p className="text-xs text-muted-foreground mt-3">
            Container resource stats are not available yet. If the broker restarts with the updated image, Broker Health will show CPU and RAM directly from cgroups.
          </p>
        )}
      </CardContent>
    </Card>
  )
}

function Metric({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div>
      <p className="text-xs text-muted-foreground uppercase tracking-wide">{label}</p>
      <p className={`text-xl font-bold ${accent ?? 'text-foreground'}`}>{value}</p>
    </div>
  )
}

function GaugeMetric({
  label,
  value,
  percent,
  accent,
}: {
  label: string
  value: string
  percent: number
  accent: string
}) {
  return (
    <div className="col-span-2 rounded-xl border border-border/60 bg-muted/20 p-3">
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs text-muted-foreground uppercase tracking-wide">{label}</p>
        <p className="text-sm font-semibold text-foreground">{value}</p>
      </div>
      <div className="mt-3 h-2.5 overflow-hidden rounded-full bg-muted">
        <div className={`h-full rounded-full transition-all ${accent}`} style={{ width: `${percent}%` }} />
      </div>
    </div>
  )
}
