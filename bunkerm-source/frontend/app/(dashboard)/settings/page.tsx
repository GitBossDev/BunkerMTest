'use client'

import { useCallback, useEffect, useState } from 'react'
import { Eye, EyeOff, Copy, RefreshCw, KeyRound, Check, Clock } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { getStoredTimezone, setStoredTimezone } from '@/lib/timeUtils'

const TIMEZONE_OPTIONS: { group: string; zones: { value: string; label: string }[] }[] = [
  {
    group: 'Auto-detect',
    zones: [{ value: 'auto', label: 'Browser timezone (auto)' }],
  },
  {
    group: 'UTC',
    zones: [{ value: 'UTC', label: 'UTC' }],
  },
  {
    group: 'Europe',
    zones: [
      { value: 'Europe/Madrid',    label: 'Madrid (CET/CEST)' },
      { value: 'Europe/London',    label: 'London (GMT/BST)' },
      { value: 'Europe/Paris',     label: 'Paris (CET/CEST)' },
      { value: 'Europe/Berlin',    label: 'Berlin (CET/CEST)' },
      { value: 'Europe/Lisbon',    label: 'Lisbon (WET/WEST)' },
      { value: 'Europe/Rome',      label: 'Rome (CET/CEST)' },
      { value: 'Europe/Amsterdam', label: 'Amsterdam (CET/CEST)' },
      { value: 'Europe/Warsaw',    label: 'Warsaw (CET/CEST)' },
      { value: 'Europe/Helsinki',  label: 'Helsinki (EET/EEST)' },
      { value: 'Europe/Moscow',    label: 'Moscow (MSK)' },
    ],
  },
  {
    group: 'Americas',
    zones: [
      { value: 'America/New_York',    label: 'New York (ET)' },
      { value: 'America/Chicago',     label: 'Chicago (CT)' },
      { value: 'America/Denver',      label: 'Denver (MT)' },
      { value: 'America/Los_Angeles', label: 'Los Angeles (PT)' },
      { value: 'America/Sao_Paulo',   label: 'São Paulo (BRT)' },
    ],
  },
  {
    group: 'Asia / Pacific',
    zones: [
      { value: 'Asia/Dubai',       label: 'Dubai (GST)' },
      { value: 'Asia/Kolkata',     label: 'India (IST)' },
      { value: 'Asia/Bangkok',     label: 'Bangkok (ICT)' },
      { value: 'Asia/Shanghai',    label: 'China (CST)' },
      { value: 'Asia/Tokyo',       label: 'Tokyo (JST)' },
      { value: 'Australia/Sydney', label: 'Sydney (AEST/AEDT)' },
    ],
  },
]

type KeySource = 'env' | 'file' | 'default'

interface ApiKeyInfo {
  key: string
  source: KeySource
}

const SOURCE_LABEL: Record<KeySource, { label: string; variant: 'secondary' | 'outline' | 'destructive' }> = {
  env:     { label: 'Environment variable',  variant: 'secondary' },
  file:    { label: 'Auto-generated',        variant: 'secondary' },
  default: { label: 'Insecure default',      variant: 'destructive' },
}

export default function SettingsPage() {
  const [info, setInfo] = useState<ApiKeyInfo | null>(null)
  const [revealed, setRevealed] = useState(false)
  const [copied, setCopied] = useState(false)
  const [isRegenerating, setIsRegenerating] = useState(false)
  const [timezone, setTimezone] = useState<string>('auto')

  const fetchKey = useCallback(async () => {
    try {
      const res = await fetch('/api/settings/apikey')
      const data = await res.json()
      setInfo(data)
    } catch {
      toast.error('Failed to load API key info')
    }
  }, [])

  useEffect(() => { fetchKey() }, [fetchKey])
  useEffect(() => { setTimezone(getStoredTimezone()) }, [])

  function handleTimezoneChange(value: string) {
    setTimezone(value)
    setStoredTimezone(value)
    toast.success('Timezone updated')
  }

  async function copyToClipboard() {
    if (!info) return
    await navigator.clipboard.writeText(info.key)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  async function regenerate() {
    if (!confirm('Generate a new API key? All services will switch to it within ~5 seconds.')) return
    setIsRegenerating(true)
    try {
      const res = await fetch('/api/settings/apikey', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'regenerate' }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error)
      setInfo({ key: data.key, source: 'file' })
      setRevealed(false)
      toast.success('API key regenerated successfully')
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : 'Failed to regenerate key')
    } finally {
      setIsRegenerating(false)
    }
  }

  const maskedKey = info ? `${info.key.slice(0, 6)}${'•'.repeat(20)}${info.key.slice(-4)}` : ''
  const displayKey = info ? (revealed ? info.key : maskedKey) : '...'
  const sourceInfo = info ? SOURCE_LABEL[info.source] : null

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <KeyRound className="h-6 w-6" />
          Settings
        </h1>
        <p className="text-muted-foreground text-sm">Manage your BunkerM instance configuration</p>
      </div>

      {/* Timezone */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Clock className="h-4 w-4" />
            Display Timezone
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Choose the timezone used to display timestamps across the panel. By default the
            browser&apos;s own timezone is used. Changes take effect immediately.
          </p>
          <div className="flex items-center gap-3">
            <Select value={timezone} onValueChange={handleTimezoneChange}>
              <SelectTrigger className="w-64">
                <SelectValue placeholder="Select timezone" />
              </SelectTrigger>
              <SelectContent>
                {TIMEZONE_OPTIONS.map((group) => (
                  <SelectGroup key={group.group}>
                    <SelectLabel>{group.group}</SelectLabel>
                    {group.zones.map((z) => (
                      <SelectItem key={z.value} value={z.value}>
                        {z.label}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                ))}
              </SelectContent>
            </Select>
            {timezone !== 'auto' && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => handleTimezoneChange('auto')}
                className="text-muted-foreground"
              >
                Reset to auto
              </Button>
            )}
          </div>
          {timezone === 'auto' && (
            <p className="text-xs text-muted-foreground">
              Currently using browser timezone:{' '}
              <code>{Intl.DateTimeFormat().resolvedOptions().timeZone}</code>
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">API Key</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            This key authenticates communication between the web interface and the MQTT
            broker services. It is generated automatically on first startup and persisted
            across container restarts. It is never exposed to the browser — all API calls
            are proxied server-side.
          </p>

          {/* Key display */}
          <div className="flex items-center gap-2">
            <code className="flex-1 font-mono text-sm bg-muted rounded-md px-3 py-2 overflow-hidden text-ellipsis whitespace-nowrap">
              {displayKey}
            </code>
            <Button variant="ghost" size="icon" onClick={() => setRevealed((r) => !r)} title={revealed ? 'Hide' : 'Reveal'}>
              {revealed ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </Button>
            <Button variant="ghost" size="icon" onClick={copyToClipboard} title="Copy to clipboard">
              {copied ? <Check className="h-4 w-4 text-green-500" /> : <Copy className="h-4 w-4" />}
            </Button>
          </div>

          {/* Source badge */}
          {sourceInfo && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              Source:
              <Badge variant={sourceInfo.variant}>{sourceInfo.label}</Badge>
              {info?.source === 'env' && (
                <span className="text-xs">(set via <code>API_KEY</code> environment variable — regenerate has no effect)</span>
              )}
            </div>
          )}

          {/* Regenerate */}
          <div className="pt-2 border-t">
            <Button
              variant="outline"
              onClick={regenerate}
              disabled={isRegenerating || info?.source === 'env'}
            >
              <RefreshCw className={`h-4 w-4 mr-2 ${isRegenerating ? 'animate-spin' : ''}`} />
              Regenerate Key
            </Button>
            {info?.source === 'env' && (
              <p className="text-xs text-muted-foreground mt-2">
                The key is controlled by the <code>API_KEY</code> environment variable. Remove it to
                allow auto-generation.
              </p>
            )}
          </div>

          {/* Custom key note */}
          <div className="rounded-md bg-muted p-3 text-xs text-muted-foreground space-y-1">
            <p className="font-medium text-foreground">Using a custom key</p>
            <p>Pass <code>-e API_KEY=your_key</code> when running the container. The same value is
            used automatically — no other configuration needed.</p>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
