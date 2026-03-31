'use client'

import { useState, useEffect, useCallback } from 'react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { InfoTooltip, TipRow } from '@/components/ui/info-tooltip'
import { monitorApi } from '@/lib/api'
import type { PeriodMessageData, StatsPeriod } from '@/types'

const PERIODS: StatsPeriod[] = ['15m', '30m', '1h', '12h', '1d', '7d']

// Refresh intervals per period (ms)
const REFRESH_MS: Record<StatsPeriod, number> = {
  '15m': 10_000,
  '30m': 15_000,
  '1h':  20_000,
  '12h': 60_000,
  '1d':  60_000,
  '7d':  120_000,
}

function formatLabel(ts: string, period: StatsPeriod): string {
  try {
    const d = new Date(ts)
    if (['15m', '30m', '1h'].includes(period)) {
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    }
    if (['12h', '1d'].includes(period)) {
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    }
    return d.toLocaleDateString([], { month: 'short', day: 'numeric' })
  } catch {
    return ts
  }
}

interface Props {
  retained?: number
}

export function MessagesChart({ retained = 0 }: Props) {
  const [period, setPeriod] = useState<StatsPeriod>('1h')
  const [chartData, setChartData] = useState<{ time: string; received: number; sent: number }[]>([])
  const [loading, setLoading] = useState(true)

  const fetchData = useCallback(async () => {
    try {
      const raw = await monitorApi.getMessagesForPeriod(period) as PeriodMessageData
      if (!raw?.timestamps?.length) {
        setChartData([])
        return
      }
      setChartData(
        raw.timestamps.map((ts, i) => ({
          time: formatLabel(ts, period),
          received: raw.msg_received[i] ?? 0,
          sent:     raw.msg_sent[i]     ?? 0,
        }))
      )
    } catch {
      // keep previous data on error
    } finally {
      setLoading(false)
    }
  }, [period])

  useEffect(() => {
    setLoading(true)
    fetchData()
    const interval = setInterval(fetchData, REFRESH_MS[period])
    return () => clearInterval(interval)
  }, [fetchData, period])

  const totalRx  = chartData.reduce((s, d) => s + d.received, 0)
  const totalTx  = chartData.reduce((s, d) => s + d.sent, 0)
  const totalAll = totalRx + totalTx

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-2 pb-2">
        <div>
          <div className="flex items-center gap-2">
            <CardTitle className="text-sm font-medium">Message Activity</CardTitle>
            <InfoTooltip side="bottom" content={
              <>
                <p className="font-semibold text-foreground mb-1">Actividad de mensajes</p>
                <TipRow label="Recibidos" text="Mensajes PUBLISH que los clientes han enviado al broker (inbound)." />
                <TipRow label="Enviados" text="Mensajes que el broker ha entregado a los suscriptores (outbound). Puede ser mayor que los recibidos si hay múltiples suscriptores por topic." />
                <TipRow label="Total" text="Suma de recibidos + enviados en la ventana temporal. No incluye mensajes de control MQTT (PING, CONNECT, etc.)." />
                <TipRow label="Retained" text="Total de mensajes con retain=true almacenados actualmente (dato global, no filtrado por período)." />
                <TipRow label="Granularidad" text="Cada barra representa un intervalo de 3 minutos." />
              </>
            } />
          </div>
          <CardDescription className="text-xs text-muted-foreground">
            Received &amp; sent per interval
          </CardDescription>
        </div>
        <div className="flex flex-wrap gap-1">
          {PERIODS.map((p) => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`px-2 py-0.5 text-xs rounded border transition-colors ${
                p === period
                  ? 'bg-primary text-primary-foreground border-primary'
                  : 'bg-transparent text-muted-foreground border-border hover:border-primary/50'
              }`}
            >
              {p}
            </button>
          ))}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Summary stats row */}
        <div className="grid grid-cols-4 gap-2 text-center border rounded-lg p-2 bg-muted/30">
          <SumStat label="Total" value={totalAll} color="text-foreground" />
          <SumStat label="Received" value={totalRx} color="text-blue-500" />
          <SumStat label="Sent" value={totalTx} color="text-green-500" />
          <SumStat label="Retained" value={retained} color="text-cyan-500" />
        </div>

        {loading ? (
          <div className="flex items-center justify-center h-[220px] text-muted-foreground text-sm">
            Loading…
          </div>
        ) : chartData.length === 0 ? (
          <div className="flex items-center justify-center h-[220px] text-muted-foreground text-sm">
            Not enough data yet for this period
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={chartData} margin={{ top: 5, right: 10, left: 10, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
              <XAxis dataKey="time" tick={{ fontSize: 10 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'hsl(var(--card))',
                  border: '1px solid hsl(var(--border))',
                  borderRadius: '8px',
                  fontSize: '12px',
                }}
              />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="received" name="Received" fill="#3b82f6" radius={[3, 3, 0, 0]} />
              <Bar dataKey="sent"     name="Sent"     fill="#22c55e" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  )
}

function SumStat({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div>
      <p className="text-[10px] text-muted-foreground uppercase tracking-wide">{label}</p>
      <p className={`text-base font-bold ${color}`}>{value.toLocaleString()}</p>
    </div>
  )
}

