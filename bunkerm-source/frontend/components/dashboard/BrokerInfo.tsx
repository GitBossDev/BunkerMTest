'use client'

import { useEffect, useState } from 'react'
import { Server, Clock, Wifi, WifiOff, Cpu, MemoryStick } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { InfoTooltip, TipRow } from '@/components/ui/info-tooltip'
import { monitorApi } from '@/lib/api'
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

/** Format bytes: 1 048 576 → "1.0 MB" */
function fmtBytes(b: number | null): string {
  if (b === null || b === undefined) return '—'
  if (b < 1024) return `${b} B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(0)} KB`
  return `${(b / 1024 / 1024).toFixed(1)} MB`
}

export function BrokerInfo({ stats }: BrokerInfoProps) {
  const connected = stats?.mqtt_connected ?? false
  const version   = parseVersion(stats?.broker_version)
  const uptime    = parseUptime(stats?.broker_uptime)

  const [cpu, setCpu] = useState<number | null>(null)
  const [rss, setRss] = useState<number | null>(null)

  useEffect(() => {
    let mounted = true
    const fetchResources = async () => {
      try {
        const r = await monitorApi.getResourceStats()
        if (mounted) {
          setCpu(r.mosquitto_cpu_pct)
          setRss(r.mosquitto_rss_bytes)
        }
      } catch { /* ignore */ }
    }
    fetchResources()
    const id = setInterval(fetchResources, 10_000)
    return () => { mounted = false; clearInterval(id) }
  }, [])

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <div className="flex items-center gap-2">
          <CardTitle className="text-sm font-medium">Broker</CardTitle>
          <InfoTooltip side="bottom" content={
            <>
              <p className="font-semibold text-foreground mb-1">Broker Information</p>
              <TipRow label="Version" text="Eclipse Mosquitto version installed in the container." />
              <TipRow label="Uptime" text="How long the Mosquitto process has been running without a restart. An unexpected restart may indicate an error." />
              <TipRow label="CPU" text="Mosquitto process CPU usage, sampled every 10 s. Shows effort needed to route messages." />
              <TipRow label="RAM (RSS)" text="Resident set size — physical memory held by Mosquitto right now. Grows with retained messages and large session stores." />
              <TipRow label="Status icon" text="Green = monitor connected to the broker · Red = no connection (the broker may be restarting)." />
            </>
          } />
        </div>
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
          <Stat icon={<Cpu className="h-3.5 w-3.5 text-slate-400" />}    label="CPU"     value={cpu !== null ? `${cpu.toFixed(1)} %` : '—'} />
          <Stat icon={<MemoryStick className="h-3.5 w-3.5 text-slate-400" />} label="RAM (RSS)" value={fmtBytes(rss)} />
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

