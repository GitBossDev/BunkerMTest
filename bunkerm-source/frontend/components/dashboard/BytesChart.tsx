'use client'

import { useState, useEffect, useCallback } from 'react'
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { InfoTooltip, TipRow } from '@/components/ui/info-tooltip'
import { monitorApi } from '@/lib/api'
import type { PeriodBytesData, StatsPeriod } from '@/types'

const PERIODS: StatsPeriod[] = ['15m', '30m', '1h', '12h', '1d', '7d']

const REFRESH_MS: Record<StatsPeriod, number> = {
  '15m': 10_000,
  '30m': 15_000,
  '1h':  20_000,
  '12h': 60_000,
  '1d':  60_000,
  '7d':  120_000,
}

/** Auto-scale a bytes value and return a human-readable string */
function autoScaleBytes(values: number[]): { divisor: number; unit: string } {
  const max = Math.max(...values, 0)
  if (max >= 1_048_576) return { divisor: 1_048_576, unit: 'MB' }
  if (max >= 1_024)     return { divisor: 1_024,     unit: 'KB' }
  return                       { divisor: 1,          unit: 'B'  }
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

export function BytesChart() {
  const [period, setPeriod] = useState<StatsPeriod>('1h')
  const [chartData, setChartData] = useState<{ time: string; sent: number; received: number }[]>([])
  const [unit, setUnit] = useState('B/s')
  const [loading, setLoading] = useState(true)

  const fetchData = useCallback(async () => {
    try {
      const raw = await monitorApi.getBytesForPeriod(period) as PeriodBytesData
      if (!raw?.timestamps?.length) {
        setChartData([])
        return
      }

      const allValues = [...raw.bytes_received, ...raw.bytes_sent]
      const { divisor, unit: u } = autoScaleBytes(allValues)
      setUnit(`${u}/s`)

      setChartData(
        raw.timestamps.map((ts, i) => ({
          time:     formatLabel(ts, period),
          received: parseFloat(((raw.bytes_received[i] ?? 0) / divisor).toFixed(2)),
          sent:     parseFloat(((raw.bytes_sent[i]     ?? 0) / divisor).toFixed(2)),
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

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-2 pb-2">
        <div className="flex items-center gap-2">
          <CardTitle className="text-sm font-medium">Bytes Transfer ({unit})</CardTitle>
          <InfoTooltip side="bottom" content={
            <>
              <p className="font-semibold text-foreground mb-1">Transferencia de bytes</p>
              <TipRow label="RX (Received)" text="Bytes recibidos por el broker desde los clientes (mensajes PUBLISH + cabeceras MQTT)." />
              <TipRow label="TX (Sent)" text="Bytes enviados por el broker a los clientes (entregas de mensajes + ACKs)." />
              <TipRow label="Escala" text="Se ajusta automáticamente a B/s, KB/s o MB/s según el volumen del período seleccionado." />
              <TipRow label="Granularidad" text="Cada barra representa un intervalo de 3 minutos." />
            </>
          } />
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
      <CardContent>
        {loading ? (
          <div className="flex items-center justify-center h-[250px] text-muted-foreground text-sm">
            Loading…
          </div>
        ) : chartData.length === 0 ? (
          <div className="flex items-center justify-center h-[250px] text-muted-foreground text-sm">
            Not enough data yet for this period
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={250}>
            <AreaChart data={chartData} margin={{ top: 5, right: 10, left: 10, bottom: 0 }}>
              <defs>
                <linearGradient id="bytesSent" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#3b82f6" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="bytesReceived" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#22c55e" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
              <XAxis dataKey="time" tick={{ fontSize: 10 }} />
              <YAxis
                tickFormatter={(v) => `${v}`}
                tick={{ fontSize: 11 }}
                width={55}
                unit={` ${unit}`}
              />
              <Tooltip
                formatter={(value: number) => [`${value} ${unit}`, undefined]}
                contentStyle={{
                  backgroundColor: 'hsl(var(--card))',
                  border: '1px solid hsl(var(--border))',
                  borderRadius: '8px',
                  fontSize: '12px',
                }}
              />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Area type="monotone" dataKey="sent"     name="Sent"     stroke="#3b82f6" fill="url(#bytesSent)"     strokeWidth={2} />
              <Area type="monotone" dataKey="received" name="Received" stroke="#22c55e" fill="url(#bytesReceived)" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  )
}

