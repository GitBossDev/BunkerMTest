'use client'

import { Server, Clock, Wifi, WifiOff } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { MonitorStats } from '@/types'

interface BrokerInfoProps {
  stats: MonitorStats | null
}

/** Parse Mosquitto broker version e.g. "mosquitto version 2.0.18" → "2.0.18" */
function parseVersion(raw?: string): string {
  if (!raw) return '—'
  const m = raw.match(/(\d+\.\d+[\d.]*)/)
  return m ? m[1] : raw
}

/** Normalise uptime e.g. "1234 seconds" → "20m 34s" */
function parseUptime(raw?: string): string {
  if (!raw) return '—'
  const m = raw.match(/^(\d+)\s*seconds?$/i)
  if (m) {
    const secs = parseInt(m[1], 10)
    if (secs < 60)    return `${secs}s`
    if (secs < 3600)  return `${Math.floor(secs / 60)}m ${secs % 60}s`
    if (secs < 86400) return `${Math.floor(secs / 3600)}h ${Math.floor((secs % 3600) / 60)}m`
    return `${Math.floor(secs / 86400)}d ${Math.floor((secs % 86400) / 3600)}h`
  }
  return raw
}

export function BrokerInfo({ stats }: BrokerInfoProps) {
  const connected = stats?.mqtt_connected ?? false
  const version   = parseVersion(stats?.broker_version)
  const uptime    = parseUptime(stats?.broker_uptime)

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium">Broker</CardTitle>
        <div className={`p-2 rounded-lg ${connected ? 'bg-green-500/10' : 'bg-red-500/10'}`}>
          {connected
            ? <Wifi className="h-4 w-4 text-green-500" />
            : <WifiOff className="h-4 w-4 text-red-500" />
          }
        </div>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col gap-3">
          <Stat icon={<Server className="h-3.5 w-3.5 text-slate-400" />} label="Version" value={version} />
          <Stat icon={<Clock className="h-3.5 w-3.5 text-slate-400" />}  label="Uptime"  value={uptime} />
        </div>
      </CardContent>
    </Card>
  )
}

function Stat({ icon, label, value }: { icon?: React.ReactNode; label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <div className="flex items-center gap-1 text-muted-foreground text-[10px] uppercase tracking-wide">
        {icon}
        {label}
      </div>
      <div className="text-sm font-semibold text-foreground">{value}</div>
    </div>
  )
}

