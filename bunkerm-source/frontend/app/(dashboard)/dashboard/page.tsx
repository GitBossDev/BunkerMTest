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
  if (!stats) return stats

  const brokerReachable = stats.broker_reachable ?? stats.mqtt_connected ?? false
  if (brokerReachable) return stats

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

  const monitorConnected = stats?.mqtt_connected ?? false
  const brokerConnected = stats?.broker_reachable ?? monitorConnected
  const monitorReconnecting = stats?.monitor_reconnecting ?? (brokerConnected && !monitorConnected)
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
              {brokerConnected && !monitorReconnecting && <Wifi className="h-3 w-3 text-green-500" />}
              {monitorReconnecting && <RefreshCw className="h-3 w-3 animate-spin text-amber-600" />}
              {!brokerConnected && <WifiOff className="h-3 w-3 text-destructive" />}
              {brokerConnected && !monitorReconnecting && 'Broker connected'}
              {monitorReconnecting && 'Broker reachable, monitor reconnecting'}
              {!brokerConnected && 'Broker offline'}
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

      {monitorReconnecting && stats && (
        <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800">
          Broker restarted successfully and is reachable, but the monitoring client is still re-subscribing. The dashboard keeps the latest broker snapshot instead of forcing an offline view. Last broker sample: {lastSnapshotLabel}.
        </div>
      )}

      {!brokerConnected && stats && (
        <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800">
          Broker offline. Live counters are shown as `0` or unavailable. Historical and persisted values remain visible as the last snapshot captured at {lastSnapshotLabel}.
        </div>
      )}

      <section className="space-y-4">
        <SectionHeading
          title="Clients"
          description="Client presence and session state only. Topic counters stay out of this section."
        />
        <StatsCards stats={displayStats} />
      </section>

      <section className="space-y-4">
        <SectionHeading
          title="Message Activity"
          description="Traffic rates, QoS pressure and topic subscription behaviour grouped in one place."
        />
        <div className="grid gap-4 grid-cols-1 lg:grid-cols-3 items-stretch">
          <div className="lg:col-span-1 h-full">
            <QoSPanel stats={displayStats} isOffline={!monitorConnected} snapshotLabel={lastSnapshotLabel} />
          </div>
          <div className="lg:col-span-2 h-full">
            <MessagesChart isOffline={!monitorConnected} snapshotLabel={lastSnapshotLabel} />
          </div>
        </div>
        <div className="grid gap-4 grid-cols-1 lg:grid-cols-2 items-stretch">
          <TopologyPanel />
          <TopSubscribedPanel />
        </div>
      </section>

      <section className="space-y-4">
        <SectionHeading
          title="Broker Health"
          description="Broker identity, latency, container resources and byte transfer."
        />
        <div className="grid gap-4 grid-cols-1 lg:grid-cols-3 items-stretch">
          <div className="lg:col-span-1 h-full">
            <BrokerHealth stats={displayStats} isOffline={!monitorConnected} snapshotLabel={lastSnapshotLabel} />
          </div>
          <div className="lg:col-span-2 h-full">
            <BytesChart isOffline={!monitorConnected} snapshotLabel={lastSnapshotLabel} />
          </div>
        </div>
      </section>
    </div>
  )
}

function SectionHeading({ title, description }: { title: string; description: string }) {
  return (
    <div>
      <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
      <p className="text-sm text-muted-foreground mt-1">{description}</p>
    </div>
  )
}

