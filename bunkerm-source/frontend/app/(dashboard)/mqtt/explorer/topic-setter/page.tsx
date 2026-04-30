'use client'

import { useEffect, useMemo, useState } from 'react'
import { Button } from '@/components/ui/button'
import { toast } from 'sonner'
import { formatRelativeTime } from '@/lib/timeUtils'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { monitorApi } from '@/lib/api'

type Unit = 'seconds' | 'minutes' | 'hours' | 'years'

interface StoredEntry {
  id: string
  topic: string
  children: string[]
  expiresAt: number
  savedAt: number
}

const STORAGE_KEY = 'bunker_topic_setter_entries_v1'
const HIST_STORAGE_KEY = 'bunker_topic_setter_histories_v1'
const TOPIC_HISTORY_LIMIT = 120

function unitSeconds(u: Unit) {
  switch (u) {
    case 'seconds':
      return 1
    case 'minutes':
      return 60
    case 'hours':
      return 3600
    case 'years':
      return 31536000
  }
}

function formatRemaining(ms: number) {
  if (ms <= 0) return 'expired'
  const s = Math.floor(ms / 1000)
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h`
  const d = Math.floor(h / 24)
  return `${d}d`
}

export default function TopicSetterPage() {
  const [topic, setTopic] = useState('')
  const [value, setValue] = useState(5)
  const [unit, setUnit] = useState<Unit>('minutes')
  const [entries, setEntries] = useState<StoredEntry[]>([])
  const [loadingSave, setLoadingSave] = useState(false)
  const [histories, setHistories] = useState<Record<string, any[]>>({})
  const [historyLoading, setHistoryLoading] = useState<Record<string, boolean>>({})
  const [expandedHistory, setExpandedHistory] = useState<Record<string, boolean>>({})

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (raw) setEntries(JSON.parse(raw))
    } catch {
      setEntries([])
    }
    try {
      const rawH = localStorage.getItem(HIST_STORAGE_KEY)
      if (rawH) {
        try {
          const parsed = JSON.parse(rawH) as Record<string, any[]>
          // ensure arrays are sorted oldest->newest
          for (const k of Object.keys(parsed)) {
            parsed[k].sort((a: any, b: any) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())
          }
          setHistories(parsed)
        } catch {
          setHistories({})
        }
      }
    } catch {}
  }, [])

  useEffect(() => {
    const t = setInterval(() => {
      setEntries((prev) => {
        const now = Date.now()
        const next = prev.filter((e) => e.expiresAt > now)
        if (next.length !== prev.length) {
          try { localStorage.setItem(STORAGE_KEY, JSON.stringify(next)) } catch {}
        }
        return next
      })
    }, 1000)
    return () => clearInterval(t)
  }, [])

  // Poll localStorage for external updates (keeps this tab in sync with explorer updates)
  useEffect(() => {
    let lastEntriesRaw: string | null = null
    let lastHistRaw: string | null = null
    const t = setInterval(() => {
      try {
        const rawE = localStorage.getItem(STORAGE_KEY)
        if (rawE && rawE !== lastEntriesRaw) {
          lastEntriesRaw = rawE
          try { setEntries(JSON.parse(rawE)) } catch {}
        }
        const rawH = localStorage.getItem(HIST_STORAGE_KEY)
        if (rawH && rawH !== lastHistRaw) {
          lastHistRaw = rawH
          try {
            const parsed = JSON.parse(rawH) as Record<string, any[]>
            for (const k of Object.keys(parsed)) {
              parsed[k].sort((a: any, b: any) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())
            }
            setHistories(parsed)
          } catch {}
        }
      } catch {}
    }, 2500)
    return () => clearInterval(t)
  }, [])

  const save = async () => {
    if (!topic.trim()) return
    setLoadingSave(true)
    try {
      const trimmed = topic.trim()
      const now = Date.now()
      const exists = entries.find((x) => x.topic === trimmed && x.expiresAt > now)
      if (exists) {
        toast.error('Topic already saved')
        setLoadingSave(false)
        return
      }
      const data = await monitorApi.getTopics()
      const all = data.topics?.map((t: any) => t.topic) ?? []
      const childrenFound = all.filter((t: string) => t === trimmed || t.startsWith(trimmed + '/'))
      const children = Array.from(new Set([trimmed, ...childrenFound]))
      const expiresAt = now + value * unitSeconds(unit) * 1000
      const entry: StoredEntry = {
        id: `${trimmed}::${now}`,
        topic: trimmed,
        children,
        expiresAt,
        savedAt: now,
      }
      const next = [entry, ...entries]
      setEntries(next)
      try { localStorage.setItem(STORAGE_KEY, JSON.stringify(next)) } catch {}
      // fetch and persist history immediately so it survives reload
      try {
        const dataH = await monitorApi.getTopicHistory(entry.topic, TOPIC_HISTORY_LIMIT)
        const arr = (dataH.history ?? [])
        arr.sort((a: any, b: any) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())
        const nextH = { ...(histories || {}), [entry.id]: arr }
        setHistories(nextH)
        try { localStorage.setItem(HIST_STORAGE_KEY, JSON.stringify(nextH)) } catch {}
      } catch {}
    } finally {
      setLoadingSave(false)
    }
  }

  const remove = (id: string) => {
    const next = entries.filter((e) => e.id !== id)
    setEntries(next)
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(next)) } catch {}
    try {
      const copy = { ...(histories || {}) }
      if (copy[id]) {
        delete copy[id]
        setHistories(copy)
        localStorage.setItem(HIST_STORAGE_KEY, JSON.stringify(copy))
      }
    } catch {}
  }

  const refreshChildren = async (id: string) => {
    const e = entries.find((x) => x.id === id)
    if (!e) return
    try {
      const data = await monitorApi.getTopics()
      const all = data.topics?.map((t: any) => t.topic) ?? []
      const childrenFound = all.filter((t: string) => t === e.topic || t.startsWith(e.topic + '/'))
      const children = Array.from(new Set([e.topic, ...childrenFound]))
      const next = entries.map((x) => (x.id === id ? { ...x, children } : x))
      setEntries(next)
      try { localStorage.setItem(STORAGE_KEY, JSON.stringify(next)) } catch {}
    } catch {}
  }

  const fetchHistory = async (id: string) => {
    const entry = entries.find((x) => x.id === id)
    if (!entry) return
    setHistoryLoading((s) => ({ ...s, [id]: true }))
    try {
      const data = await monitorApi.getTopicHistory(entry.topic, TOPIC_HISTORY_LIMIT)
      const arr = (data.history ?? [])
      // ensure ascending-by-time order (oldest -> newest)
      arr.sort((a: any, b: any) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())
      const nextH = { ...(histories || {}), [id]: arr }
      setHistories(nextH)
      try { localStorage.setItem(HIST_STORAGE_KEY, JSON.stringify(nextH)) } catch {}
    } catch {
      const nextH = { ...(histories || {}), [id]: [] }
      setHistories(nextH)
      try { localStorage.setItem(HIST_STORAGE_KEY, JSON.stringify(nextH)) } catch {}
    } finally {
      setHistoryLoading((s) => ({ ...s, [id]: false }))
    }
  }

  // keep histories in localStorage and prune when entries change
  // but avoid running on mount before histories are loaded
  useEffect(() => {
    try {
      if (!histories || Object.keys(histories).length === 0) return
      const allowed = new Set(entries.map((e) => e.id))
      const pruned: Record<string, any[]> = {}
      for (const k of Object.keys(histories)) {
        if (allowed.has(k)) pruned[k] = histories[k]
      }
      setHistories(pruned)
      localStorage.setItem(HIST_STORAGE_KEY, JSON.stringify(pruned))
    } catch {}
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entries])

  const now = Date.now()

  const active = useMemo(() => entries.filter((e) => e.expiresAt > now), [entries, now])

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">Topic Setter</h1>
          <p className="text-muted-foreground text-sm">Pin a topic and its children for a limited time</p>
        </div>
      </div>
        {/* Topic Setter Form */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">Set Topic</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="sm:col-span-2 space-y-1">
              <Label>Topic</Label>
              <Input placeholder="e.g. sensors/room1" value={topic} onChange={(e) => setTopic(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label>Duration</Label>
              <div className="flex gap-2">
                <Input type="number" value={value} onChange={(e) => setValue(Number(e.target.value))} />
                <Select value={unit} onValueChange={(v) => setUnit(v as Unit)}>
                  <SelectTrigger className="w-36">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="seconds">seconds</SelectItem>
                    <SelectItem value="minutes">minutes</SelectItem>
                    <SelectItem value="hours">hours</SelectItem>
                    <SelectItem value="years">years</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          </div>

          <div className="flex justify-end">
            <Button onClick={save} disabled={loadingSave}>
              Save Topic
            </Button>
          </div>
        </CardContent>
      </Card>
    {/* Topic Setter List */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">Saved Topics</CardTitle>
        </CardHeader>
        <CardContent className="p-2 space-y-2">
          <div className="flex gap-2 items-center justify-end mb-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                try {
                  const blob = new Blob([JSON.stringify(entries, null, 2)], { type: 'application/json' })
                  const url = URL.createObjectURL(blob)
                  const a = document.createElement('a')
                  a.href = url
                  a.download = 'bunker_topic_setter_entries.json'
                  a.click()
                  URL.revokeObjectURL(url)
                } catch {}
              }}
            >
              Export
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={() => {
                setEntries([])
                setHistories({})
                try { localStorage.removeItem(STORAGE_KEY) } catch {}
                try { localStorage.removeItem(HIST_STORAGE_KEY) } catch {}
              }}
            >
              Clear All
            </Button>
          </div>
          {active.length === 0 ? (
            <p className="text-center py-6 text-muted-foreground text-sm">No pinned topics</p>
          ) : (
            <div className="space-y-2">
              {active.map((e) => (
                <div key={e.id} className="border rounded-md p-3">
                  <div className="flex items-start gap-3">
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-semibold break-all">{e.topic}</span>
                        <Badge variant="secondary">{e.children.length}</Badge>
                        <span className="text-xs text-muted-foreground">saved {new Date(e.savedAt).toLocaleString()}</span>
                        <span className="ml-auto text-xs text-muted-foreground">{formatRemaining(e.expiresAt - Date.now())}</span>
                      </div>
                      <div className="mt-2 text-sm text-muted-foreground">
                        {e.children.slice(0, 20).map((c) => (
                          <div key={c} className="font-mono text-xs truncate">{c}</div>
                        ))}
                        {e.children.length > 20 && <div className="text-xs text-muted-foreground">...and more</div>}
                      </div>
                      <div className="mt-3">
                        <div className="flex items-center gap-2">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={async () => {
                              const isOpen = !!expandedHistory[e.id]
                              if (!isOpen && !histories[e.id]) await fetchHistory(e.id)
                              setExpandedHistory((s) => ({ ...s, [e.id]: !isOpen }))
                            }}
                          >
                            {expandedHistory[e.id] ? 'Hide History' : 'Show History'}
                          </Button>
                        </div>
                        {expandedHistory[e.id] && (
                          <div className="mt-2 rounded-md border bg-muted/20 p-2">
                            {historyLoading[e.id] ? (
                              <div className="text-xs text-muted-foreground">Loading history...</div>
                            ) : !histories[e.id] || histories[e.id].length === 0 ? (
                              <div className="text-xs text-muted-foreground">No history captured for this topic yet.</div>
                            ) : (
                              <div className="space-y-2 max-h-[40vh] overflow-y-auto">
                                {histories[e.id].map((h: any, idx: number) => (
                                  <div key={h.id || idx} className="p-2 border rounded-md">
                                    <div className="flex items-center gap-2 text-xs">
                                      <Badge variant="outline">#{histories[e.id].length - idx}</Badge>
                                      <span className="text-muted-foreground">{formatRelativeTime(h.timestamp)}</span>
                                      <Badge variant="secondary">QoS {h.qos}</Badge>
                                      <Badge variant="outline">{h.payload_bytes} B</Badge>
                                      {h.retained && (
                                        <Badge variant="outline" className="border-orange-400 text-orange-500">retained</Badge>
                                      )}
                                    </div>
                                    <pre className="text-xs font-mono whitespace-pre-wrap break-all rounded-md bg-white/5 p-2 mt-2">{String(h.value)}</pre>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                    <div className="flex flex-col gap-2">
                      <Button variant="outline" size="sm" onClick={() => refreshChildren(e.id)}>Refresh</Button>
                      <Button variant="destructive" size="sm" onClick={() => remove(e.id)}>Remove</Button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
