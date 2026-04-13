'use client'

import { useEffect, useState, useCallback } from 'react'
import { RefreshCw, Wifi, WifiOff } from 'lucide-react'
import { monitorApi } from '@/lib/api'
import { StatsCards } from '@/components/dashboard/StatsCards'
import { BytesChart } from '@/components/dashboard/BytesChart'
import { MessagesChart } from '@/components/dashboard/MessagesChart'
import { BrokerHealth } from '@/components/dashboard/BrokerHealth'
import { QoSPanel } from '@/components/dashboard/QoSPanel'
import { TopologyPanel } from '@/components/dashboard/TopologyPanel'
import { TopSubscribedPanel } from '@/components/dashboard/TopSubscribedPanel'
import { Button } from '@/components/ui/button'
import type { MonitorStats } from '@/types'

function normalizeOfflineStats(stats: MonitorStats | null): MonitorStats | null {
  if (!stats || stats.mqtt_connected) return stats

  return {
    ...stats,
    total_connected_clients: 0,
    clients_disconnected: 0,
    clients_total: 0,
    total_subscriptions: 0,
    messages_inflight: 0,
    load_msg_rx_1min: 0,
    load_msg_tx_1min: 0,
    load_bytes_rx_1min: 0,
    load_bytes_tx_1min: 0,
    load_connections_1min: 0,
    latency_ms: -1,
  }
}

function formatSnapshotTime(raw: string | undefined): string {
  if (!raw) return 'before disconnection'
  const date = new Date(raw)
  if (Number.isNaN(date.getTime())) return 'before disconnection'
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export default function DashboardPage() {
  const [stats, setStats] = useState<MonitorStats | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)

  const fetchData = useCallback(async () => {
    setIsLoading(true)
    try {
      const data = await monitorApi.getStats() as MonitorStats
      setStats(data)
      setLastUpdated(new Date())
    } catch {
      // Backend may not be running — fail silently
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 10_000)
    return () => clearInterval(interval)
  }, [fetchData])

  const brokerConnected = stats?.mqtt_connected ?? false
  const displayStats = normalizeOfflineStats(stats)
  const lastSnapshotLabel = formatSnapshotTime(stats?.last_broker_sample_at)

  return (
    <div className="space-y-6">
      {/* ── Header ── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Dashboard</h1>
          <p className="text-muted-foreground text-sm">MQTT Broker Overview</p>
        </div>
        <div className="flex items-center gap-3">
          {stats && (
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              {brokerConnected
                ? <Wifi className="h-3 w-3 text-green-500" />
                : <WifiOff className="h-3 w-3 text-destructive" />}
              {brokerConnected ? 'Broker connected' : 'Broker offline'}
            </div>
          )}
          {lastUpdated && (
            <span className="text-xs text-muted-foreground hidden sm:block">
              Updated {lastUpdated.toLocaleTimeString()}
            </span>
          )}
          <Button variant="outline" size="sm" onClick={fetchData} disabled={isLoading}>
            <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </div>
      </div>

      {!brokerConnected && stats && (
        <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800">
          Broker offline. Live counters are shown as `0` or unavailable. Historical and persisted values remain visible as the last snapshot captured at {lastSnapshotLabel}.
        </div>
      )}

      {/* ── Row 1: Clients (2/3) + QoS (1/3) ── */}
      <div className="grid gap-4 grid-cols-1 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <StatsCards stats={displayStats} />
        </div>
        <QoSPanel stats={displayStats} isOffline={!brokerConnected} snapshotLabel={lastSnapshotLabel} />
      </div>

      {/* ── Row 2: Bytes Transfer (2/3) + Broker Health (1/3) ── */}
      <div className="grid gap-4 grid-cols-1 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <BytesChart isOffline={!brokerConnected} snapshotLabel={lastSnapshotLabel} />
        </div>
        <BrokerHealth stats={displayStats} isOffline={!brokerConnected} snapshotLabel={lastSnapshotLabel} />
      </div>

      {/* ── Row 3: Message Activity ── */}
      <div className="grid gap-4 grid-cols-1">
        <MessagesChart retained={stats?.retained_messages ?? 0} isOffline={!brokerConnected} snapshotLabel={lastSnapshotLabel} />
      </div>

      {/* ── Row 4: Topic topology + Top subscribed ── */}
      <div className="grid gap-4 grid-cols-1 lg:grid-cols-2">
        <TopologyPanel />
        <TopSubscribedPanel />
      </div>
    </div>
  )
}

