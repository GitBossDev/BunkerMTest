'use client'

import { useCallback, useEffect, useState } from 'react'
import { ShieldCheck, Loader2, Save } from 'lucide-react'
import { toast } from 'sonner'
import { dynsecApi } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'

type DefaultACL = {
  publishClientSend: boolean
  publishClientReceive: boolean
  subscribe: boolean
  unsubscribe: boolean
}

const DEFAULT_ACL_LABELS: Record<keyof DefaultACL, string> = {
  publishClientSend: 'Publish (Client Send)',
  publishClientReceive: 'Publish (Client Receive)',
  subscribe: 'Subscribe',
  unsubscribe: 'Unsubscribe',
}

export function DefaultACLCard() {
  const [config, setConfig] = useState<DefaultACL | null>(null)
  const [saving, setSaving] = useState(false)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await dynsecApi.getDefaultACL()
      setConfig(data)
    } catch {
      toast.error('Failed to load default ACL access settings')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const handleToggle = (key: keyof DefaultACL) => {
    if (!config) return
    setConfig({ ...config, [key]: !config[key] })
  }

  const handleSave = async () => {
    if (!config) return
    setSaving(true)
    try {
      await dynsecApi.setDefaultACL(config)
      toast.success('Default ACL access updated')
    } catch {
      toast.error('Failed to update default ACL access')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-5 w-5 text-muted-foreground" />
          <div>
            <CardTitle>Default ACL Access</CardTitle>
            <CardDescription className="mt-1">
              Fallback permissions applied when no role rule matches. Deny subscribe to enforce role-based topic restrictions.
            </CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="flex items-center gap-2 py-4">
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
            <span className="text-sm text-muted-foreground">Loading...</span>
          </div>
        ) : config ? (
          <div className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {(Object.keys(DEFAULT_ACL_LABELS) as (keyof DefaultACL)[]).map((key) => (
                <div key={key} className="flex items-center justify-between rounded-md border px-4 py-3">
                  <Label htmlFor={`acl-${key}`} className="text-sm cursor-pointer select-none">
                    {DEFAULT_ACL_LABELS[key]}
                  </Label>
                  <div className="flex items-center gap-2 ml-4">
                    <span className={`text-xs font-medium ${config[key] ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                      {config[key] ? 'Allow' : 'Deny'}
                    </span>
                    <Switch
                      id={`acl-${key}`}
                      checked={config[key]}
                      onCheckedChange={() => handleToggle(key)}
                    />
                  </div>
                </div>
              ))}
            </div>
            <Button size="sm" onClick={handleSave} disabled={saving}>
              {saving ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Save className="h-4 w-4 mr-2" />}
              Save
            </Button>
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}
