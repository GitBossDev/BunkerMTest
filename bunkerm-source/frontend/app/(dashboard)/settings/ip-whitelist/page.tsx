'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { Info, Loader2, Plus, RefreshCw, Save, Shield, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { securityApi } from '@/lib/api'
import type {
  IPWhitelistAction,
  IPWhitelistDocument,
  IPWhitelistEntry,
  IPWhitelistMode,
  IPWhitelistPolicy,
  IPWhitelistPolicyUpsert,
  IPWhitelistScope,
  IPWhitelistStatus,
} from '@/types'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'

const SCOPE_OPTIONS: Array<{ value: IPWhitelistScope; label: string }> = [
  { value: 'api_admin', label: 'API Admin' },
  { value: 'mqtt_clients', label: 'MQTT Clients' },
]

const MODE_OPTIONS: Array<{ value: IPWhitelistMode; label: string; description: string }> = [
  {
    value: 'disabled',
    label: 'Disabled',
    description: 'No auditing or blocking is applied.',
  },
  {
    value: 'audit',
    label: 'Audit',
    description: 'Evaluates policy and records decisions without blocking access.',
  },
  {
    value: 'enforce',
    label: 'Enforce',
    description: 'Blocks requests outside the whitelist for enforced scopes.',
  },
]

function clonePolicy(policy: IPWhitelistPolicy): IPWhitelistPolicy {
  return {
    ...policy,
    trustedProxies: [...(policy.trustedProxies || [])],
    defaultAction: {
      api_admin: policy.defaultAction?.api_admin || 'allow',
      mqtt_clients: policy.defaultAction?.mqtt_clients || 'allow',
    },
    entries: (policy.entries || []).map((entry) => ({ ...entry })),
    lastUpdatedBy: {
      type: policy.lastUpdatedBy?.type || 'human',
      id: policy.lastUpdatedBy?.id || 'admin@bhm.local',
    },
  }
}

function normalizePolicyForUpsert(policy: IPWhitelistPolicy): IPWhitelistPolicyUpsert {
  const trustedProxies = Array.from(
    new Set(
      (policy.trustedProxies || [])
        .map((value) => value.trim())
        .filter(Boolean)
    )
  )

  return {
    mode: policy.mode,
    trustedProxies,
    defaultAction: {
      api_admin: policy.defaultAction.api_admin,
      mqtt_clients: policy.defaultAction.mqtt_clients,
    },
    entries: policy.entries.map((entry) => ({
      id: entry.id.trim(),
      cidr: entry.cidr.trim(),
      scope: entry.scope,
      description: entry.description.trim(),
      enabled: entry.enabled,
    })),
    lastUpdatedBy: {
      type: 'human',
      id: 'admin@bhm.local',
    },
  }
}

function validatePolicyDraft(policy: IPWhitelistPolicy): string | null {
  if (!MODE_OPTIONS.some((mode) => mode.value === policy.mode)) {
    return 'Invalid mode selected.'
  }

  const ids = new Set<string>()
  for (let idx = 0; idx < policy.entries.length; idx++) {
    const entry = policy.entries[idx]
    const row = idx + 1

    if (!entry.id.trim()) {
      return `Entry ${row}: id is required.`
    }
    if (!/^[A-Za-z0-9_.-]+$/.test(entry.id.trim())) {
      return `Entry ${row}: id may only contain letters, numbers, hyphens, underscores, and dots.`
    }
    if (ids.has(entry.id.trim())) {
      return `Entry ${row}: duplicated id '${entry.id.trim()}'.`
    }
    ids.add(entry.id.trim())

    if (!entry.cidr.trim()) {
      return `Entry ${row}: cidr is required.`
    }
    if (!SCOPE_OPTIONS.some((scope) => scope.value === entry.scope)) {
      return `Entry ${row}: invalid scope.`
    }
  }

  const actions: IPWhitelistAction[] = ['allow', 'deny']
  if (!actions.includes(policy.defaultAction.api_admin) || !actions.includes(policy.defaultAction.mqtt_clients)) {
    return 'Default actions must be allow or deny for both scopes.'
  }

  return null
}

function entryFactory(): IPWhitelistEntry {
  return {
    id: '',
    cidr: '',
    scope: 'api_admin',
    description: '',
    enabled: true,
  }
}

export default function IpWhitelistPage() {
  const [document, setDocument] = useState<IPWhitelistDocument | null>(null)
  const [draftPolicy, setDraftPolicy] = useState<IPWhitelistPolicy | null>(null)
  const [status, setStatus] = useState<IPWhitelistStatus | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [refreshingStatus, setRefreshingStatus] = useState(false)

  const loadWhitelist = useCallback(async () => {
    setLoading(true)
    setLoadError(null)
    try {
      const payload = await securityApi.getIpWhitelist()
      setDocument(payload)
      setDraftPolicy(clonePolicy(payload.policy))
      setStatus(payload.status)
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to load IP whitelist'
      setLoadError(message)
      toast.error(message)
    } finally {
      setLoading(false)
    }
  }, [])

  const refreshStatus = useCallback(async () => {
    setRefreshingStatus(true)
    try {
      const payload = await securityApi.getIpWhitelistStatus()
      setStatus(payload)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to refresh whitelist status')
    } finally {
      setRefreshingStatus(false)
    }
  }, [])

  useEffect(() => {
    loadWhitelist()
  }, [loadWhitelist])

  const isDirty = useMemo(() => {
    if (!document || !draftPolicy) return false
    return JSON.stringify(normalizePolicyForUpsert(document.policy)) !== JSON.stringify(normalizePolicyForUpsert(draftPolicy))
  }, [document, draftPolicy])

  const updateEntry = (index: number, patch: Partial<IPWhitelistEntry>) => {
    setDraftPolicy((current) => {
      if (!current) return current
      const next = clonePolicy(current)
      next.entries[index] = { ...next.entries[index], ...patch }
      return next
    })
  }

  const removeEntry = (index: number) => {
    setDraftPolicy((current) => {
      if (!current) return current
      const next = clonePolicy(current)
      next.entries.splice(index, 1)
      return next
    })
  }

  const addEntry = () => {
    setDraftPolicy((current) => {
      if (!current) return current
      const next = clonePolicy(current)
      next.entries.push(entryFactory())
      return next
    })
  }

  const setTrustedProxiesText = (rawText: string) => {
    const values = rawText
      .split('\n')
      .map((value) => value.trim())
      .filter(Boolean)

    setDraftPolicy((current) => {
      if (!current) return current
      return {
        ...clonePolicy(current),
        trustedProxies: values,
      }
    })
  }

  const savePolicy = async () => {
    if (!draftPolicy) return

    const validationError = validatePolicyDraft(draftPolicy)
    if (validationError) {
      toast.error(validationError)
      return
    }

    setSaving(true)
    try {
      const payload = normalizePolicyForUpsert(draftPolicy)
      const updated = await securityApi.updateIpWhitelist(payload)
      setDocument(updated)
      setDraftPolicy(clonePolicy(updated.policy))
      setStatus(updated.status)
      toast.success('IP whitelist policy saved')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to save IP whitelist')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="space-y-4 max-w-6xl">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Shield className="h-6 w-6" />
          IP Whitelist
        </h1>
        <div className="flex items-center gap-2 text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading whitelist policy...
        </div>
      </div>
    )
  }

  if (loadError || !draftPolicy || !status) {
    return (
      <div className="space-y-4 max-w-6xl">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Shield className="h-6 w-6" />
          IP Whitelist
        </h1>
        <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-4 py-3 text-sm space-y-3">
          <p className="text-destructive font-medium">Unable to load IP whitelist policy</p>
          <p className="text-muted-foreground">{loadError || 'Missing policy or status payload from API response.'}</p>
          <Button variant="outline" onClick={loadWhitelist}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Retry
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6 max-w-6xl">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Shield className="h-6 w-6" />
            IP Whitelist
          </h1>
          <p className="text-muted-foreground text-sm">
            Manage IP-based access policy for API admin scope and broker-facing MQTT client scope.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={refreshStatus} disabled={refreshingStatus}>
            {refreshingStatus ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4 mr-2" />
            )}
            Refresh Status
          </Button>
          <Button onClick={savePolicy} disabled={!isDirty || saving}>
            {saving ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <Save className="h-4 w-4 mr-2" />
            )}
            Save Policy
          </Button>
        </div>
      </div>

      <div className="rounded-lg border bg-muted/40 px-4 py-3 text-sm text-muted-foreground flex items-start gap-2">
        <Info className="h-4 w-4 mt-0.5 shrink-0" />
        <p>
          api_admin can be enforced now. mqtt_clients status is already exposed, but final broker-facing enforcement remains a dedicated platform scope.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Policy</CardTitle>
          <CardDescription>
            Version {draftPolicy.version} · Last updated {draftPolicy.lastUpdatedAt || 'never'}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="space-y-1.5">
              <Label>Mode</Label>
              <Select
                value={draftPolicy.mode}
                onValueChange={(value) => {
                  setDraftPolicy((current) => {
                    if (!current) return current
                    return {
                      ...clonePolicy(current),
                      mode: value as IPWhitelistMode,
                    }
                  })
                }}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select mode" />
                </SelectTrigger>
                <SelectContent>
                  {MODE_OPTIONS.map((mode) => (
                    <SelectItem key={mode.value} value={mode.value}>
                      {mode.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label>Default Action (API Admin)</Label>
              <Select
                value={draftPolicy.defaultAction.api_admin}
                onValueChange={(value) => {
                  setDraftPolicy((current) => {
                    if (!current) return current
                    return {
                      ...clonePolicy(current),
                      defaultAction: {
                        ...current.defaultAction,
                        api_admin: value as IPWhitelistAction,
                      },
                    }
                  })
                }}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="allow">allow</SelectItem>
                  <SelectItem value="deny">deny</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label>Default Action (MQTT Clients)</Label>
              <Select
                value={draftPolicy.defaultAction.mqtt_clients}
                onValueChange={(value) => {
                  setDraftPolicy((current) => {
                    if (!current) return current
                    return {
                      ...clonePolicy(current),
                      defaultAction: {
                        ...current.defaultAction,
                        mqtt_clients: value as IPWhitelistAction,
                      },
                    }
                  })
                }}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="allow">allow</SelectItem>
                  <SelectItem value="deny">deny</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="trustedProxies">Trusted Proxies (one CIDR/IP per line)</Label>
            <Textarea
              id="trustedProxies"
              className="min-h-[96px]"
              value={draftPolicy.trustedProxies.join('\n')}
              onChange={(event) => setTrustedProxiesText(event.target.value)}
              placeholder={'10.0.0.0/24\n127.0.0.1/32'}
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-2">
            <div>
              <CardTitle className="text-base">Entries</CardTitle>
              <CardDescription>
                Define explicit CIDR/IP rules by scope. Disabled entries are ignored.
              </CardDescription>
            </div>
            <Button variant="outline" onClick={addEntry}>
              <Plus className="h-4 w-4 mr-2" />
              Add Entry
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {draftPolicy.entries.length === 0 && (
            <p className="text-sm text-muted-foreground">No whitelist entries yet.</p>
          )}

          {draftPolicy.entries.map((entry, index) => (
            <div key={`${entry.id}-${index}`} className="rounded-md border p-3 space-y-3">
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-3">
                <div className="space-y-1.5">
                  <Label>ID</Label>
                  <Input
                    value={entry.id}
                    onChange={(event) => updateEntry(index, { id: event.target.value })}
                    placeholder="office-vpn"
                  />
                </div>

                <div className="space-y-1.5 lg:col-span-2">
                  <Label>CIDR / IP</Label>
                  <Input
                    value={entry.cidr}
                    onChange={(event) => updateEntry(index, { cidr: event.target.value })}
                    placeholder="203.0.113.0/24"
                  />
                </div>

                <div className="space-y-1.5">
                  <Label>Scope</Label>
                  <Select
                    value={entry.scope}
                    onValueChange={(value) => updateEntry(index, { scope: value as IPWhitelistScope })}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {SCOPE_OPTIONS.map((scope) => (
                        <SelectItem key={scope.value} value={scope.value}>
                          {scope.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-1.5">
                  <Label>Enabled</Label>
                  <div className="flex h-10 items-center justify-between rounded-md border px-3">
                    <Switch
                      checked={entry.enabled}
                      onCheckedChange={(value) => updateEntry(index, { enabled: value })}
                    />
                    <Badge variant={entry.enabled ? 'secondary' : 'outline'}>
                      {entry.enabled ? 'on' : 'off'}
                    </Badge>
                  </div>
                </div>
              </div>

              <div className="flex items-end gap-2">
                <div className="space-y-1.5 flex-1">
                  <Label>Description</Label>
                  <Input
                    value={entry.description}
                    onChange={(event) => updateEntry(index, { description: event.target.value })}
                    placeholder="Office VPN"
                  />
                </div>
                <Button variant="outline" onClick={() => removeEntry(index)}>
                  <Trash2 className="h-4 w-4 mr-2" />
                  Remove
                </Button>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Runtime Status</CardTitle>
          <CardDescription>
            Current enforcement and reconciliation status by scope.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="rounded-md border p-3 space-y-1.5">
            <h3 className="font-medium">api_admin</h3>
            <p className="text-sm text-muted-foreground">Mode: {status.apiAdmin.mode}</p>
            <p className="text-sm text-muted-foreground">Entries: {status.apiAdmin.configuredEntries}</p>
            <p className="text-sm text-muted-foreground">Last decision: {status.apiAdmin.lastDecisionResult || 'n/a'}</p>
            <p className="text-sm text-muted-foreground">Last IP: {status.apiAdmin.lastEvaluatedIp || 'n/a'}</p>
          </div>

          <div className="rounded-md border p-3 space-y-1.5">
            <h3 className="font-medium">mqtt_clients</h3>
            <p className="text-sm text-muted-foreground">Mode: {status.mqttClients.mode}</p>
            <p className="text-sm text-muted-foreground">Entries: {status.mqttClients.configuredEntries}</p>
            <p className="text-sm text-muted-foreground">Desired version: {status.mqttClients.desiredVersion}</p>
            <p className="text-sm text-muted-foreground">Applied version: {status.mqttClients.appliedVersion}</p>
            <p className="text-sm text-muted-foreground">Observed version: {status.mqttClients.observedVersion}</p>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
