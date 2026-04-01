'use client'

import { useCallback, useEffect, useState } from 'react'
import { Save, RefreshCw, Loader2, AlertTriangle, Info, RotateCcw } from 'lucide-react'
import { toast } from 'sonner'
import { configApi } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'

interface ListenerData {
  port: number
  bind_address?: string
  per_listener_settings?: boolean
  max_connections?: number
  protocol?: string | null
}

interface ConfigState {
  mqttPort: number
  maxConnections: number        // -1 = unlimited
  wsEnabled: boolean
  wsPort: number
  maxInflight: number           // 0 = use default (20)
  maxQueued: number             // 0 = unlimited
  // kept for round-trip — untouched keys go back as-is
  rawConfig: Record<string, unknown>
  dyncSecListeners: ListenerData[]  // port 8080 and any other non-editable listeners
}

const DEFAULT_STATE: ConfigState = {
  mqttPort: 1900,
  maxConnections: -1,
  wsEnabled: false,
  wsPort: 9001,
  maxInflight: 0,
  maxQueued: 0,
  rawConfig: {},
  dyncSecListeners: [],
}

function parseApiResponse(data: Record<string, unknown>): ConfigState {
  const listeners = (data.listeners as ListenerData[]) ?? []

  // Main TCP listener: first non-websocket listener that is NOT the DynSec HTTP port (8080)
  const mqttListener = listeners.find(
    (l) => (!l.protocol || l.protocol !== 'websockets') && l.port !== 8080
  )

  // WebSocket listener
  const wsListener = listeners.find((l) => l.protocol === 'websockets')

  // DynSec and other non-editable listeners (port 8080, etc.)
  const dyncSecListeners = listeners.filter(
    (l) => l.port === 8080 || (l.protocol && l.protocol !== 'websockets' && l.port !== mqttListener?.port)
  )

  return {
    mqttPort: mqttListener?.port ?? 1900,
    maxConnections: mqttListener?.max_connections ?? -1,
    wsEnabled: !!wsListener,
    wsPort: wsListener?.port ?? 9001,
    maxInflight: (data.max_inflight_messages as number | null) ?? 0,
    maxQueued: (data.max_queued_messages as number | null) ?? 0,
    rawConfig: (data.config as Record<string, unknown>) ?? {},
    dyncSecListeners,
  }
}

function buildSavePayload(state: ConfigState) {
  const listeners: ListenerData[] = [
    {
      port: state.mqttPort,
      bind_address: '',
      per_listener_settings: false,
      max_connections: state.maxConnections,
      protocol: null,
    },
    ...state.dyncSecListeners,
  ]

  if (state.wsEnabled) {
    listeners.push({
      port: state.wsPort,
      bind_address: '',
      per_listener_settings: false,
      max_connections: -1,
      protocol: 'websockets',
    })
  }

  return {
    config: state.rawConfig,
    listeners,
    max_inflight_messages: state.maxInflight > 0 ? state.maxInflight : null,
    max_queued_messages: state.maxQueued > 0 ? state.maxQueued : null,
  }
}

function NumberField({
  id,
  label,
  description,
  value,
  onChange,
  min,
  placeholder,
  disabled,
}: {
  id: string
  label: string
  description: string
  value: number
  onChange: (v: number) => void
  min?: number
  placeholder?: string
  disabled?: boolean
}) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        type="number"
        min={min}
        value={value === -1 ? '' : value === 0 ? '' : value}
        placeholder={placeholder}
        disabled={disabled}
        onChange={(e) => {
          const n = parseInt(e.target.value, 10)
          onChange(isNaN(n) ? (min === 1 ? 1 : -1) : n)
        }}
        className="w-40"
      />
      <p className="text-xs text-muted-foreground">{description}</p>
    </div>
  )
}

export default function MosquittoConfigPage() {
  const [state, setState] = useState<ConfigState>(DEFAULT_STATE)
  const [saved, setSaved] = useState<ConfigState>(DEFAULT_STATE)
  const [isLoading, setIsLoading] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [isRestarting, setIsRestarting] = useState(false)

  const fetchConfig = useCallback(async () => {
    setIsLoading(true)
    try {
      const data = await configApi.getMosquittoConfig() as Record<string, unknown>
      const parsed = parseApiResponse(data)
      setState(parsed)
      setSaved(parsed)
    } catch {
      toast.error('Failed to load broker configuration')
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => { fetchConfig() }, [fetchConfig])

  const isDirty = JSON.stringify(state) !== JSON.stringify(saved)

  const handleSave = async () => {
    setIsSaving(true)
    try {
      const payload = buildSavePayload(state)
      await configApi.saveMosquittoConfig(payload)
      setSaved(state)
      toast.success('Configuration saved — click "Apply (Reload)" to activate changes')
    } catch {
      toast.error('Failed to save configuration')
    } finally {
      setIsSaving(false)
    }
  }

  const handleRestart = async () => {
    setIsRestarting(true)
    try {
      await configApi.restartMosquitto()
      toast.success('Mosquitto reloaded — changes are now active')
    } catch {
      toast.error('Failed to reload Mosquitto')
    } finally {
      setIsRestarting(false)
    }
  }

  const set = <K extends keyof ConfigState>(key: K, value: ConfigState[K]) =>
    setState((s) => ({ ...s, [key]: value }))

  return (
    <div className="space-y-6 max-w-2xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Broker Configuration</h1>
          <p className="text-muted-foreground text-sm">Mosquitto broker settings</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={fetchConfig} disabled={isLoading || isSaving}>
            <RefreshCw className={`h-4 w-4 mr-1 ${isLoading ? 'animate-spin' : ''}`} />
            Reload
          </Button>
          <Button variant="outline" size="sm" onClick={handleRestart} disabled={isRestarting || isLoading}>
            {isRestarting ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <RotateCcw className="h-4 w-4 mr-1" />}
            Apply (Reload)
          </Button>
          <Button size="sm" onClick={handleSave} disabled={isSaving || !isDirty || isLoading}>
            {isSaving ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Save className="h-4 w-4 mr-1" />}
            Save
          </Button>
        </div>
      </div>

      {isDirty && (
        <div className="flex items-center gap-2 rounded-md border border-amber-300 bg-amber-50 dark:bg-amber-950/30 px-3 py-2 text-sm text-amber-700 dark:text-amber-400">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          Unsaved changes — save and restart the broker to apply.
        </div>
      )}

      {isLoading ? (
        <div className="flex items-center justify-center h-48">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <>
          {/* Listeners */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-base">Listeners</CardTitle>
                <Badge variant="outline" className="text-xs">Requires restart</Badge>
              </div>
              <CardDescription>Network ports the broker listens on</CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              <NumberField
                id="mqttPort"
                label="MQTT Port (TCP)"
                description="Default: 1900. Standard MQTT is 1883."
                value={state.mqttPort}
                min={1}
                placeholder="1900"
                onChange={(v) => set('mqttPort', v)}
              />
              <div className="flex items-start gap-2 rounded-md bg-blue-500/10 px-3 py-2 text-xs text-blue-700 dark:text-blue-400">
                <Info className="h-3.5 w-3.5 mt-0.5 shrink-0" />
                <span>This is the <strong>internal</strong> container port. Your docker-compose maps it to a different host port (e.g. <strong>1901:1900</strong>). External clients connect to the host port.</span>
              </div>

              <Separator />

              {/* WebSocket */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <Label htmlFor="wsToggle">WebSocket Listener</Label>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      Enables MQTT over WebSocket for browser clients
                    </p>
                  </div>
                  <Switch
                    id="wsToggle"
                    checked={state.wsEnabled}
                    onCheckedChange={(v) => set('wsEnabled', v)}
                  />
                </div>

                {state.wsEnabled && (
                  <NumberField
                    id="wsPort"
                    label="WebSocket Port"
                    description="Default: 9001"
                    value={state.wsPort}
                    min={1}
                    placeholder="9001"
                    onChange={(v) => set('wsPort', v)}
                  />
                )}
              </div>

              <Separator />

              <div className="flex items-start gap-2 rounded-md bg-muted/50 px-3 py-2 text-xs text-muted-foreground">
                <Info className="h-3.5 w-3.5 mt-0.5 shrink-0" />
                <span>The DynSec HTTP listener (port 8080) is managed internally and is not shown here.</span>
              </div>
            </CardContent>
          </Card>

          {/* Connection limits */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-base">Connection Limits</CardTitle>
                <Badge variant="outline" className="text-xs">Requires restart</Badge>
              </div>
              <CardDescription>Control resource usage and client behaviour</CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              <NumberField
                id="maxConn"
                label="Max Connections"
                description="Maximum simultaneous clients. Leave empty for unlimited (−1)."
                value={state.maxConnections}
                min={-1}
                placeholder="unlimited"
                onChange={(v) => set('maxConnections', v < 1 ? -1 : v)}
              />

              <Separator />

              <NumberField
                id="maxInflight"
                label="Max Inflight Messages"
                description="QoS 1/2 messages awaiting ACK per client (currently in transit). Too low causes publisher backpressure. 0 = broker default (20)."
                value={state.maxInflight}
                min={0}
                placeholder="default (20)"
                onChange={(v) => set('maxInflight', Math.max(0, v))}
              />

              <NumberField
                id="maxQueued"
                label="Max Queued Messages"
                description="Messages spooled for offline persistent-session clients; delivered on reconnect. 0 = unlimited (memory risk with many offline clients)."
                value={state.maxQueued}
                min={0}
                placeholder="unlimited"
                onChange={(v) => set('maxQueued', Math.max(0, v))}
              />
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}

