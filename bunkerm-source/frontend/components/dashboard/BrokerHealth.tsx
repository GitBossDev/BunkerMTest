'use client'

import { Activity } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { InfoTooltip, TipRow } from '@/components/ui/info-tooltip'
import type { MonitorStats } from '@/types'

interface BrokerHealthProps {
  stats: MonitorStats | null
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

export function BrokerHealth({ stats }: BrokerHealthProps) {
  const rxMsg  = stats?.load_msg_rx_1min  ?? 0
  const txMsg  = stats?.load_msg_tx_1min  ?? 0
  const rxByte = stats?.load_bytes_rx_1min ?? 0
  const txByte = stats?.load_bytes_tx_1min ?? 0
  const latency  = stats?.latency_ms ?? -1

  const latencyLabel = latency < 0 ? '—' : `${Math.round(latency)} ms`

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <div className="flex items-center gap-2">
          <CardTitle className="text-sm font-medium">Broker Health</CardTitle>
          <InfoTooltip content={
            <>
              <p className="font-semibold text-foreground mb-1">Broker Performance</p>
              <TipRow label="Msg RX/TX" text="Messages received/sent per second. 1-minute moving average reported by Mosquitto." />
              <TipRow label="Bytes RX/TX" text="Data volume transferred per second, including MQTT protocol headers." />
              <TipRow label="Latency" text="Round-trip time: the monitor publishes a ping to the broker and measures the response time. Green &lt;50ms · Yellow &lt;200ms · Red &gt;200ms." />
            </>
          } />
        </div>
        <div className="p-2 rounded-lg bg-emerald-500/10">
          <Activity className="h-4 w-4 text-emerald-500" />
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-x-6 gap-y-4">
          <Metric label="Msg RX rate"  value={`${rxMsg.toFixed(1)} msg/s`}  accent="text-blue-500" />
          <Metric label="Msg TX rate"  value={`${txMsg.toFixed(1)} msg/s`}  accent="text-green-500" />
          <Metric label="Bytes RX"     value={formatBytes(rxByte)}           accent="text-blue-400" />
          <Metric label="Bytes TX"     value={formatBytes(txByte)}           accent="text-green-400" />
          <Metric label="Latency"      value={latencyLabel}                  accent={latencyColor(latency)} />
        </div>
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
