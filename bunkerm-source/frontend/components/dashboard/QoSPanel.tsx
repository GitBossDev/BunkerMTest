'use client'

import { Layers } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { InfoTooltip, TipRow } from '@/components/ui/info-tooltip'
import type { MonitorStats } from '@/types'

interface QoSPanelProps {
  stats: MonitorStats | null
}

function formatBytes(b: number): string {
  if (b < 1024)        return `${b} B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`
  return `${(b / (1024 * 1024)).toFixed(2)} MB`
}

export function QoSPanel({ stats }: QoSPanelProps) {
  const inflight   = stats?.messages_inflight ?? 0
  const stored     = stats?.messages_stored ?? 0
  const storeBytes = stats?.messages_store_bytes ?? 0
  const retained   = stats?.retained_messages ?? 0

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <div className="flex items-center gap-2">
          <CardTitle className="text-sm font-medium">QoS</CardTitle>
          <InfoTooltip content={
            <>
              <p className="font-semibold text-foreground mb-1">Quality of Service</p>
              <TipRow label="In-flight" text="QoS 1/2 messages sent but not yet acknowledged by the recipient. A growing number indicates congestion." />
              <TipRow label="Stored" text="Messages queued for offline clients with a persistent session (QoS 1/2)." />
              <TipRow label="Retained" text="Messages stored with retain=true. They represent the last known value for a topic, delivered to new subscribers immediately." />
            </>
          } />
        </div>
        <div className="p-2 rounded-lg bg-violet-500/10">
          <Layers className="h-4 w-4 text-violet-500" />
        </div>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col gap-4">
          <Metric label="In-flight msgs" value={String(inflight)}                              accent="text-yellow-500" />
          <Metric label="Stored msgs"    value={`${stored} (${formatBytes(storeBytes)})`} />
          <Metric label="Retained msgs"  value={String(retained)}                              accent="text-cyan-500" />
        </div>
      </CardContent>
    </Card>
  )
}

function Metric({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div>
      <p className="text-[10px] text-muted-foreground uppercase tracking-wide">{label}</p>
      <p className={`text-lg font-bold ${accent ?? 'text-foreground'}`}>{value}</p>
    </div>
  )
}
