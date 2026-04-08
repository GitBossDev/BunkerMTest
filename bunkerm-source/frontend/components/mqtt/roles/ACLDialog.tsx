'use client'

import { useState, useEffect, useMemo } from 'react'
import { toast } from 'sonner'
import { Trash2, Pencil, Check, X } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { dynsecApi, clientlogsApi } from '@/lib/api'
import type { Role, ACL } from '@/types'

/**
 * Given a set of concrete topics (e.g. "lab/device/X/Temp"), generate
 * all useful wildcard variants:
 *   lab/device/X/Temp          (exact)
 *   lab/device/X/+             (last level single-wildcard)
 *   lab/device/+/Temp          (penultimate level)
 *   lab/device/X/#             (subtree from second-to-last)
 *   lab/device/#
 *   lab/#
 *   #
 */
function buildTopicSuggestions(topics: string[]): string[] {
  const set = new Set<string>()
  for (const t of topics) {
    set.add(t)
    const parts = t.split('/')
    // Single-level wildcards: replace each level with +
    for (let i = 0; i < parts.length; i++) {
      const variant = [...parts.slice(0, i), '+', ...parts.slice(i + 1)].join('/')
      set.add(variant)
    }
    // Multi-level wildcards: replace suffix with #
    for (let i = 1; i <= parts.length; i++) {
      const prefix = parts.slice(0, i).join('/')
      set.add(prefix + '/#')
    }
    set.add('#')
  }
  return Array.from(set).sort()
}

/**
 * Topic input with inline completion hint — no dropdown.
 * Shows a grayed suggestion below the field as you type.
 * Press Tab or click the hint to accept; keep typing to override.
 */
function TopicInput({
  value,
  suggestions,
  onChange,
  onKeyDown: extKeyDown,
  placeholder,
  className,
  disabled,
}: {
  value: string
  suggestions: string[]
  onChange: (v: string) => void
  onKeyDown?: React.KeyboardEventHandler<HTMLInputElement>
  placeholder?: string
  className?: string
  disabled?: boolean
}) {
  const completion = useMemo(() => {
    if (!value) return ''
    const lower = value.toLowerCase()
    return suggestions.find((s) => s.toLowerCase().startsWith(lower) && s.length > value.length) ?? ''
  }, [value, suggestions])

  return (
    <div className="space-y-0.5">
      <Input
        value={value}
        placeholder={placeholder}
        className={className}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (completion && e.key === 'Tab') {
            e.preventDefault()
            onChange(completion)
          }
          extKeyDown?.(e)
        }}
      />
      {completion && (
        <p
          className="cursor-pointer truncate px-1 font-mono text-[11px] text-muted-foreground/50 transition-colors hover:text-muted-foreground/80 select-none"
          onClick={() => onChange(completion)}
          title="Tab or click to complete"
        >
          <span className="opacity-50">{value}</span>
          <span className="text-primary/70 font-medium">{completion.slice(value.length)}</span>
        </p>
      )}
    </div>
  )
}

// All ACL types supported by Mosquitto dynamic security
const ACL_TYPES = [
  { value: 'publishClientSend', label: 'Publish (Client Send)' },
  { value: 'publishClientReceive', label: 'Publish (Client Receive)' },
  { value: 'subscribeLiteral', label: 'Subscribe (Literal)' },
  { value: 'subscribePattern', label: 'Subscribe (Pattern)' },
  { value: 'unsubscribeLiteral', label: 'Unsubscribe (Literal)' },
  { value: 'unsubscribePattern', label: 'Unsubscribe (Pattern)' },
]

interface ACLDialogProps {
  role: Role | null
  open: boolean
  onOpenChange: (v: boolean) => void
  onSuccess: (acls: ACL[]) => void
}

export function ACLDialog({ role, open, onOpenChange, onSuccess }: ACLDialogProps) {
  const [currentRole, setCurrentRole] = useState<Role | null>(role)
  const [acltype, setAcltype] = useState<string>('')
  const [topic, setTopic] = useState<string>('')
  const [allow, setAllow] = useState<string>('allow')
  const [addingACL, setAddingACL] = useState(false)
  const [removingACL, setRemovingACL] = useState<string | null>(null)
  const [loadingRole, setLoadingRole] = useState(false)
  const [editingACL, setEditingACL] = useState<ACL | null>(null)
  const [editingTopic, setEditingTopic] = useState<string>('')
  const [savingEdit, setSavingEdit] = useState(false)
  const [testType, setTestType] = useState<string>('')
  const [testTopic, setTestTopic] = useState<string>('')
  const [testResult, setTestResult] = useState<{
    allowed: boolean
    reason: string
    matchedRule: { topic: string; aclType: string; allow: boolean; priority: number } | null
  } | null>(null)
  const [testing, setTesting] = useState(false)
  const [rawTopics, setRawTopics] = useState<string[]>([])

  const topicSuggestions = useMemo(() => buildTopicSuggestions(rawTopics), [rawTopics])

  const editingCompletion = useMemo(() => {
    if (!editingTopic) return ''
    const lower = editingTopic.toLowerCase()
    return topicSuggestions.find((s) => s.toLowerCase().startsWith(lower) && s.length > editingTopic.length) ?? ''
  }, [editingTopic, topicSuggestions])

  useEffect(() => {
    if (open && role) {
      setCurrentRole(role)
      refreshRole(role.rolename)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, role?.rolename])

  useEffect(() => {
    if (!open) return
    clientlogsApi.getTopSubscribed(200)
      .then((res) => setRawTopics((res as { top_subscribed: { topic: string }[] }).top_subscribed.map((t) => t.topic)))
      .catch(() => { /* silently ignore — autocomplete is best-effort */ })
  }, [open])

  const refreshRole = async (rolename: string) => {
    setLoadingRole(true)
    try {
      // Backend returns { role: "string_name", acls: [{aclType, topic, permission, priority}] }
      const res = await dynsecApi.getRole(rolename) as { role: string; acls?: ACL[] }
      setCurrentRole({ rolename: res.role ?? rolename, acls: res.acls ?? [] })
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to load role details')
    } finally {
      setLoadingRole(false)
    }
  }

  const handleAddACL = async () => {
    if (!currentRole || !acltype || !topic) return
    setAddingACL(true)
    try {
      await dynsecApi.addRoleACL(currentRole.rolename, {
        aclType: acltype,
        topic,
        permission: allow,
      })
      toast.success('ACL added successfully')
      setAcltype('')
      setTopic('')
      setAllow('allow')
      await refreshRole(currentRole.rolename)
      // notify parent with updated acls so count can update
      const updated = { rolename: currentRole.rolename, acls: currentRole.acls ?? [] }
      onSuccess(updated.acls)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to add ACL')
    } finally {
      setAddingACL(false)
    }
  }

  const handleRemoveACL = async (acl: ACL) => {
    if (!currentRole) return
    const key = `${acl.aclType}:${acl.topic}`
    setRemovingACL(key)
    try {
      await dynsecApi.removeRoleACL(currentRole.rolename, acl.aclType, acl.topic)
      toast.success('ACL removed successfully')
      await refreshRole(currentRole.rolename)
      onSuccess(currentRole.acls ?? [])
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to remove ACL')
    } finally {
      setRemovingACL(null)
    }
  }

  const handleStartEdit = (acl: ACL) => {
    setEditingACL(acl)
    setEditingTopic(acl.topic)
  }

  const handleCancelEdit = () => {
    setEditingACL(null)
    setEditingTopic('')
  }

  const handleSaveEdit = async () => {
    if (!currentRole || !editingACL || !editingTopic.trim()) return
    if (editingTopic.trim() === editingACL.topic) {
      handleCancelEdit()
      return
    }
    setSavingEdit(true)
    try {
      // Mosquitto has no "update ACL" command — remove old, add new
      await dynsecApi.removeRoleACL(currentRole.rolename, editingACL.aclType, editingACL.topic)
      await dynsecApi.addRoleACL(currentRole.rolename, {
        aclType: editingACL.aclType,
        topic: editingTopic.trim(),
        permission: editingACL.permission,
      })
      toast.success('ACL updated successfully')
      setEditingACL(null)
      setEditingTopic('')
      await refreshRole(currentRole.rolename)
      onSuccess(currentRole.acls ?? [])
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to update ACL')
    } finally {
      setSavingEdit(false)
    }
  }

  const handleTestACL = async () => {
    if (!currentRole || !testType || !testTopic) return
    setTesting(true)
    try {
      const result = await dynsecApi.testRoleACL(currentRole.rolename, testType, testTopic)
      setTestResult(result)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to test ACL')
    } finally {
      setTesting(false)
    }
  }

  const handleClose = () => {
    setAcltype('')
    setTopic('')
    setAllow('allow')
    setEditingACL(null)
    setEditingTopic('')
    setTestType('')
    setTestTopic('')
    setTestResult(null)
    onOpenChange(false)
  }

  const acls = currentRole?.acls ?? []

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[640px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            Manage ACLs
            {currentRole && (
              <span className="ml-2 text-sm font-normal text-muted-foreground">
                — {currentRole.rolename}
              </span>
            )}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {/* Existing ACLs */}
          <div className="space-y-2">
            <Label className="text-sm font-medium">Current ACLs</Label>
            {loadingRole ? (
              <p className="text-sm text-muted-foreground">Loading...</p>
            ) : acls.length === 0 ? (
              <p className="text-sm text-muted-foreground">No ACLs defined for this role.</p>
            ) : (
              <div className="rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Type</TableHead>
                      <TableHead>Topic</TableHead>
                      <TableHead>Permission</TableHead>
                      <TableHead className="w-20" />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {acls.map((acl) => {
                      const key = `${acl.aclType}:${acl.topic}`
                      const typeLabel =
                        ACL_TYPES.find((t) => t.value === acl.aclType)?.label ?? acl.aclType
                      const isEditing =
                        editingACL?.aclType === acl.aclType && editingACL?.topic === acl.topic
                      return (
                        <TableRow key={key}>
                          <TableCell className="text-xs font-mono">{typeLabel}</TableCell>
                          <TableCell className="font-mono text-xs max-w-[180px]">
                            {isEditing ? (
                              <div className="space-y-0.5">
                                <input
                                  className="w-full rounded border border-input bg-background px-2 py-1 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-ring"
                                  value={editingTopic}
                                  onChange={(e) => setEditingTopic(e.target.value)}
                                  onKeyDown={(e) => {
                                    if (editingCompletion && e.key === 'Tab') { e.preventDefault(); setEditingTopic(editingCompletion) }
                                    if (e.key === 'Enter') handleSaveEdit()
                                    if (e.key === 'Escape') handleCancelEdit()
                                  }}
                                  autoFocus
                                  disabled={savingEdit}
                                />
                                {editingCompletion && (
                                  <p
                                    className="cursor-pointer truncate font-mono text-[10px] text-muted-foreground/50 transition-colors hover:text-muted-foreground/80 select-none"
                                    onClick={() => setEditingTopic(editingCompletion)}
                                    title="Tab or click to complete"
                                  >
                                    <span className="opacity-50">{editingTopic}</span>
                                    <span className="text-primary/70 font-medium">{editingCompletion.slice(editingTopic.length)}</span>
                                  </p>
                                )}
                              </div>
                            ) : (
                              <span className="truncate block">{acl.topic}</span>
                            )}
                          </TableCell>
                          <TableCell>
                            <Badge variant={acl.permission === 'allow' ? 'success' : 'destructive'}>
                              {acl.permission === 'allow' ? 'Allow' : 'Deny'}
                            </Badge>
                          </TableCell>
                          <TableCell>
                            <div className="flex items-center gap-1">
                              {isEditing ? (
                                <>
                                  <Button
                                    variant="ghost"
                                    size="icon"
                                    className="h-7 w-7 text-green-600 hover:text-green-600 hover:bg-green-50"
                                    onClick={handleSaveEdit}
                                    disabled={savingEdit || !editingTopic.trim()}
                                    aria-label="Save edit"
                                  >
                                    <Check className="h-3.5 w-3.5" />
                                  </Button>
                                  <Button
                                    variant="ghost"
                                    size="icon"
                                    className="h-7 w-7 text-muted-foreground hover:text-foreground"
                                    onClick={handleCancelEdit}
                                    disabled={savingEdit}
                                    aria-label="Cancel edit"
                                  >
                                    <X className="h-3.5 w-3.5" />
                                  </Button>
                                </>
                              ) : (
                                <>
                                  <Button
                                    variant="ghost"
                                    size="icon"
                                    className="h-7 w-7 text-muted-foreground hover:text-foreground"
                                    onClick={() => handleStartEdit(acl)}
                                    disabled={removingACL === key || !!editingACL}
                                    aria-label="Edit topic"
                                  >
                                    <Pencil className="h-3.5 w-3.5" />
                                  </Button>
                                  <Button
                                    variant="ghost"
                                    size="icon"
                                    className="h-7 w-7 text-destructive hover:text-destructive hover:bg-destructive/10"
                                    onClick={() => handleRemoveACL(acl)}
                                    disabled={removingACL === key || !!editingACL}
                                    aria-label="Remove ACL"
                                  >
                                    <Trash2 className="h-3.5 w-3.5" />
                                  </Button>
                                </>
                              )}
                            </div>
                          </TableCell>
                        </TableRow>
                      )
                    })}
                  </TableBody>
                </Table>
              </div>
            )}
          </div>

          <Separator />

          {/* Add new ACL */}
          <div className="space-y-3">
            <Label className="text-sm font-medium">Add ACL</Label>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">ACL Type</Label>
                <Select value={acltype} onValueChange={setAcltype}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select type..." />
                  </SelectTrigger>
                  <SelectContent>
                    {ACL_TYPES.map((t) => (
                      <SelectItem key={t.value} value={t.value}>
                        {t.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">Topic</Label>
                <TopicInput
                  placeholder="e.g. sensors/#"
                  value={topic}
                  suggestions={topicSuggestions}
                  onChange={setTopic}
                />
              </div>

              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">Permission</Label>
                <Select value={allow} onValueChange={setAllow}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="allow">Allow</SelectItem>
                    <SelectItem value="deny">Deny</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <Button
              onClick={handleAddACL}
              disabled={!acltype || !topic || addingACL}
              size="sm"
            >
              {addingACL ? 'Adding...' : 'Add ACL'}
            </Button>
          </div>

          <Separator />

          {/* Test ACL */}
          <div className="space-y-3">
            <Label className="text-sm font-medium">Test Access</Label>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">ACL Type</Label>
                <Select value={testType} onValueChange={(v) => { setTestType(v); setTestResult(null) }}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select type..." />
                  </SelectTrigger>
                  <SelectContent>
                    {ACL_TYPES.map((t) => (
                      <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">Topic</Label>
                <TopicInput
                  placeholder="e.g. plant/water-plant-1/sensors/#"
                  value={testTopic}
                  suggestions={topicSuggestions}
                  onChange={(v) => { setTestTopic(v); setTestResult(null) }}
                  onKeyDown={(e) => { if (e.key === 'Enter') handleTestACL() }}
                />
              </div>
            </div>
            <Button
              onClick={handleTestACL}
              disabled={!testType || !testTopic || testing || !currentRole}
              size="sm"
              variant="secondary"
            >
              {testing ? 'Testing...' : 'Test Access'}
            </Button>
            {testResult && (
              <div className={`rounded-md border p-3 text-sm ${
                testResult.allowed
                  ? 'border-green-400 bg-green-50 dark:bg-green-950/30'
                  : 'border-red-400 bg-red-50 dark:bg-red-950/30'
              }`}>
                <div className="flex items-center gap-2 font-medium">
                  {testResult.allowed ? (
                    <Check className="h-4 w-4 text-green-600" />
                  ) : (
                    <X className="h-4 w-4 text-red-600" />
                  )}
                  <span className={testResult.allowed ? 'text-green-700 dark:text-green-400' : 'text-red-700 dark:text-red-400'}>
                    {testResult.allowed ? 'Access Allowed' : 'Access Denied'}
                  </span>
                  <Badge variant="outline" className="ml-auto text-xs">
                    {testResult.reason === 'role_acl' ? 'Role ACL' : 'Default ACL'}
                  </Badge>
                </div>
                {testResult.matchedRule && (
                  <p className="mt-1.5 text-xs text-muted-foreground font-mono">
                    Matched: {testResult.matchedRule.aclType} → {testResult.matchedRule.topic}
                  </p>
                )}
              </div>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={handleClose}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
