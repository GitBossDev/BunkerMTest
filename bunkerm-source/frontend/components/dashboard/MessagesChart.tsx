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
                <p className="font-semibold text-foreground mb-1">Message Activity</p>
                <TipRow label="Received" text="PUBLISH messages sent by clients to the broker (inbound traffic)." />
                <TipRow label="Sent" text="Messages delivered by the broker to subscribers (outbound). Can exceed received if multiple clients subscribe to the same topic." />
                <TipRow label="Total" text="Sum of received + sent within the selected time window. Does not include MQTT control packets (PING, CONNECT, etc.)." />
                <TipRow label="Retained" text="Total messages currently stored with retain=true (global stat, not filtered by period)." />
                <TipRow label="Granularity" text="Each bar represents a 3-minute interval. Data accumulates over time." />
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
          <EmptyPeriod period={period} onSwitch={setPeriod} height={220} />
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

// ── Smart empty state ────────────────────────────────────────────────────────
const WIDER: Partial<Record<StatsPeriod, StatsPeriod>> = {
  '15m': '1h',
  '30m': '1h',
  '1h':  '12h',
  '12h': '1d',
  '1d':  '7d',
}

function EmptyPeriod({
  period,
  onSwitch,
  height,
}: {
  period: StatsPeriod
  onSwitch: (p: StatsPeriod) => void
  height: number
}) {
  const wider = WIDER[period]
  return (
    <div
      className="flex flex-col items-center justify-center gap-3 text-muted-foreground text-sm"
      style={{ height }}
    >
      <span>No activity recorded in this window.</span>
      {wider ? (
        <span className="text-xs">
          Data may be visible in a longer range —{' '}
          <button
            onClick={() => onSwitch(wider)}
            className="text-sky-500 hover:text-sky-400 underline underline-offset-2 font-medium"
          >
            view {wider}
          </button>
        </span>
      ) : (
        <span className="text-xs">Ticks are recorded every 3 minutes while the broker is active.</span>
      )}
    </div>
  )
}

