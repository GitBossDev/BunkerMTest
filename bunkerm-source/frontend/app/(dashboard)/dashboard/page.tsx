'use client'

import { useEffect, useState, useCallback } from 'react'
import { RefreshCw, Wifi, WifiOff } from 'lucide-react'
import { monitorApi } from '@/lib/api'
import { StatsCards } from '@/components/dashboard/StatsCards'
import { BytesChart } from '@/components/dashboard/BytesChart'
import { MessagesChart } from '@/components/dashboard/MessagesChart'
import { BrokerInfo } from '@/components/dashboard/BrokerInfo'
import { BrokerHealth } from '@/components/dashboard/BrokerHealth'
import { QoSPanel } from '@/components/dashboard/QoSPanel'
import { TopologyPanel } from '@/components/dashboard/TopologyPanel'
import { Button } from '@/components/ui/button'
import type { MonitorStats } from '@/types'

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

      {/* ── Row 1: Clients panel ── */}
      <StatsCards stats={stats} />

      {/* ── Row 2: Bytes + Messages charts ── */}
      <div className="grid gap-4 grid-cols-1 lg:grid-cols-2">
        <BytesChart />
        <MessagesChart retained={stats?.retained_messages ?? 0} />
      </div>

      {/* ── Row 3: Broker info + Health + QoS ── */}
      <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
        <BrokerInfo stats={stats} />
        <div className="sm:col-span-2 lg:col-span-2">
          <BrokerHealth stats={stats} />
        </div>
        <QoSPanel stats={stats} />
      </div>

      {/* ── Row 4: Topic topology ── */}
      <TopologyPanel />
    </div>
  )
}

