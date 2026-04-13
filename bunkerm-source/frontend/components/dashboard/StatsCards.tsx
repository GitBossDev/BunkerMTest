'use client'

import { Users } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import ClientGauge from '@/components/dashboard/ClientGauge'
import { InfoTooltip, TipRow } from '@/components/ui/info-tooltip'
import type { MonitorStats } from '@/types'

interface StatsCardsProps {
  stats: MonitorStats | null
}

export function StatsCards({ stats }: StatsCardsProps) {
  const connected    = stats?.total_connected_clients ?? 0
  const disconnected = stats?.clients_disconnected ?? 0
  const total        = stats?.clients_total ?? (connected + disconnected)
  const maximum      = stats?.clients_maximum ?? connected
  const subscribedClients = stats?.subscribed_clients ?? 0
  const publisherClients  = stats?.publisher_clients ?? 0

  return (
    <Card className="h-full">
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <div className="flex items-center gap-2">
          <CardTitle className="text-sm font-medium">Clients</CardTitle>
          <InfoTooltip side="bottom" content={
            <>
              <p className="font-semibold text-foreground mb-1">MQTT Clients</p>
              <TipRow label="Connected" text="Clients with an active TCP connection to the broker right now." />
              <TipRow label="Disconnected" text="Clients with a persistent session saved in the broker but no active connection at this moment." />
              <TipRow label="Active sessions" text="Connected + Disconnected (shown above). Disconnected clients retain a persistent session in the broker and receive queued QoS 1/2 messages upon reconnect." />
              <TipRow label="Max concurrent" text="Historical peak of simultaneously connected clients since the last broker restart." />
              <TipRow label="Subscribed clients" text="Connected non-admin clients whose effective DynSec permissions allow subscribing right now. The admin/internal clients are intentionally excluded from this workload counter." />
              <TipRow label="Publisher clients" text="Connected non-admin clients whose effective DynSec permissions allow publishing right now. The admin/internal clients are intentionally excluded from this workload counter." />
            </>
          } />
        </div>
        <div className="p-2 rounded-lg bg-blue-500/10">
          <Users className="h-4 w-4 text-blue-500" />
        </div>
      </CardHeader>
      <CardContent className="h-full">
        <div className="flex flex-col sm:flex-row items-center gap-6">
          {/* Gauge */}
          <div className="shrink-0">
            <ClientGauge connected={connected} maxAllowed={stats?.client_max_connections ?? 10000} />
          </div>

          {/* Stats — 2 columns */}
          <div className="grid grid-cols-2 gap-x-8 gap-y-4 w-full sm:w-auto">
            <Stat label="Connected"      value={connected}    accent="text-blue-500" />
            <Stat label="Disconnected"   value={disconnected} accent="text-orange-400" />
            <Stat label="Active sessions" value={total} />
            <Stat label="Max concurrent"  value={maximum}     accent="text-orange-500" />
            <Stat label="Subscribed clients" value={subscribedClients} accent="text-violet-500" />
            <Stat label="Publisher clients"  value={publisherClients}  accent="text-emerald-500" />
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

function Stat({ label, value, accent }: { label: string; value: number; accent?: string }) {
  return (
    <div>
      <p className="text-xs text-muted-foreground uppercase tracking-wide">{label}</p>
      <p className={`text-2xl font-bold ${accent ?? 'text-foreground'}`}>{value.toLocaleString()}</p>
    </div>
  )
}

