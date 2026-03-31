'use client'

import { Users, MessageSquare, Activity, Archive } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import ClientGauge from '@/components/dashboard/ClientGauge'
import type { MonitorStats } from '@/types'

interface StatsCardsProps {
  stats: MonitorStats | null
}

export function StatsCards({ stats }: StatsCardsProps) {
  const connected = stats?.total_connected_clients ?? 0
  const total     = stats?.clients_total ?? connected
  const maximum   = stats?.clients_maximum ?? connected
  const subs      = stats?.total_subscriptions ?? 0
  const retained  = stats?.retained_messages ?? 0
  const msgsRx    = stats?.messages_received_raw ?? 0
  const msgsTx    = stats?.messages_sent_raw ?? 0

  return (
    <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
      {/* ── Clients gauge card ── */}
      <Card className="sm:col-span-2 lg:col-span-2">
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">Client Usage</CardTitle>
          <div className="p-2 rounded-lg bg-blue-500/10">
            <Users className="h-4 w-4 text-blue-500" />
          </div>
        </CardHeader>
        <CardContent className="flex flex-col items-center pt-2">
          <ClientGauge connected={connected} total={total} maximum={maximum} />
        </CardContent>
      </Card>

      {/* ── Subscriptions card ── */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">Subscriptions</CardTitle>
          <div className="p-2 rounded-lg bg-purple-500/10">
            <Activity className="h-4 w-4 text-purple-500" />
          </div>
        </CardHeader>
        <CardContent>
          <div className="text-3xl font-bold">{subs.toLocaleString()}</div>
          <p className="text-xs text-muted-foreground mt-1">Active right now</p>
        </CardContent>
      </Card>

      {/* ── Messages + Retained card ── */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">Messages</CardTitle>
          <div className="p-2 rounded-lg bg-green-500/10">
            <MessageSquare className="h-4 w-4 text-green-500" />
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex justify-between items-end">
            <div>
              <div className="text-2xl font-bold text-blue-500">{msgsRx.toLocaleString()}</div>
              <p className="text-xs text-muted-foreground">Received (cumul.)</p>
            </div>
            <div className="text-right">
              <div className="text-2xl font-bold text-green-500">{msgsTx.toLocaleString()}</div>
              <p className="text-xs text-muted-foreground">Sent (cumul.)</p>
            </div>
          </div>
          <div className="border-t pt-2 flex items-center gap-2">
            <Archive className="h-3 w-3 text-cyan-500 shrink-0" />
            <span className="text-xs text-muted-foreground">
              Retained: <strong className="text-foreground">{retained}</strong>
            </span>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
