'use client'

import { ActivitySquare } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { InfoTooltip, TipRow } from '@/components/ui/info-tooltip'
import type { MonitorStats } from '@/types'

interface QoSPanelProps {
  stats: MonitorStats | null
  isOffline?: boolean
  snapshotLabel?: string
}

function formatRate(value: number | undefined, suffix: string): string {
  return `${(value ?? 0).toFixed(1)} ${suffix}`
}

export function QoSPanel({ stats, isOffline = false, snapshotLabel }: QoSPanelProps) {
  const rxRate     = stats?.load_msg_rx_1min ?? 0
  const txRate     = stats?.load_msg_tx_1min ?? 0
  const inflight   = stats?.messages_inflight ?? 0
  const retained   = stats?.retained_messages ?? 0
  const subscriptions = stats?.total_subscriptions ?? 0

  return (
    <Card className="h-full">
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <div className="flex items-center gap-2">
          <CardTitle className="text-sm font-medium">Activity Metrics</CardTitle>
          <InfoTooltip content={
            <>
              <p className="font-semibold text-foreground mb-1">Message Activity</p>
              <TipRow label="Msg RX rate" text="Messages received per second by the broker during the last minute." />
              <TipRow label="Msg TX rate" text="Messages sent per second by the broker during the last minute." />
              <TipRow label="In-flight" text="QoS 1/2 messages sent but not yet acknowledged by the recipient. A growing number indicates congestion." />
              <TipRow label="Retained" text="Messages stored with retain=true. They represent the last known value for a topic, delivered to new subscribers immediately." />
              <TipRow label="Topic subscriptions" text="Current number of topic subscriptions on the broker. This is a topic-level metric, not a client count." />
            </>
          } />
        </div>
        <div className="p-2 rounded-lg bg-violet-500/10">
          <ActivitySquare className="h-4 w-4 text-violet-500" />
        </div>
      </CardHeader>
      <CardContent className="h-full">
        {isOffline && (
          <p className="text-xs text-amber-700 mb-3">Live rates and in-flight are reset while offline. Retained and topic subscriptions are shown from the last broker snapshot at {snapshotLabel ?? 'before disconnection'}.</p>
        )}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-4">
          <Metric label="Msg RX rate" value={formatRate(rxRate, 'msg/s')} accent="text-blue-500" />
          <Metric label="Msg TX rate" value={formatRate(txRate, 'msg/s')} accent="text-green-500" />
          <Metric label="In-flight msgs" value={String(inflight)} accent="text-yellow-500" />
          <Metric label="Retained msgs" value={String(retained)} accent="text-cyan-500" />
          <Metric label="Topic subscriptions" value={String(subscriptions)} accent="text-violet-500" />
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
