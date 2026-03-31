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
  const connected = stats?.total_connected_clients ?? 0
  const total     = stats?.clients_total ?? connected
  const maximum   = stats?.clients_maximum ?? connected
  const subs      = stats?.total_subscriptions ?? 0

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <div className="flex items-center gap-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">Clients</CardTitle>
          <InfoTooltip side="bottom" content={
            <>
              <p className="font-semibold text-foreground mb-1">Clientes MQTT</p>
              <TipRow label="Conectados" text="Clientes con conexión TCP activa en este momento." />
              <TipRow label="Sesiones activas" text="Total de sesiones registradas por el broker (conectadas + desconectadas pero recordadas)." />
              <TipRow label="Máximo" text="Pico histórico de clientes conectados simultáneamente desde el último reinicio del broker." />
              <TipRow label="Suscripciones" text="Total de suscripciones a topics activas en este momento (un cliente puede tener varias)." />
            </>
          } />
        </div>
        <div className="p-2 rounded-lg bg-blue-500/10">
          <Users className="h-4 w-4 text-blue-500" />
        </div>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col sm:flex-row items-center gap-6">
          {/* Gauge */}
          <div className="shrink-0">
            <ClientGauge connected={connected} total={total} maximum={maximum} />
          </div>

          {/* Stats */}
          <div className="flex-1 grid grid-cols-2 gap-x-8 gap-y-4 w-full sm:w-auto">
            <Stat label="Connected" value={connected} accent="text-blue-500" />
            <Stat label="Active sessions" value={total} />
            <Stat label="Max concurrent" value={maximum} accent="text-orange-500" />
            <Stat label="Subscriptions" value={subs} accent="text-purple-500" />
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

