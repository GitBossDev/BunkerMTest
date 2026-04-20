'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ChevronRight,
  ChevronDown,
  Eye,
  Radio,
  RefreshCw,
  Search,
  Send,
} from 'lucide-react'
import { toast } from 'sonner'
import { monitorApi } from '@/lib/api'
import { formatRelativeTime } from '@/lib/timeUtils'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
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
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import type { MqttTopic, MqttTopicHistoryMessage } from '@/types'

// ── Tree types ────────────────────────────────────────────────────────────────

interface TreeNode {
  name: string
  fullPath: string
  children: Map<string, TreeNode>
  leaf?: MqttTopic
}

const TOPIC_HISTORY_LIMIT = 120

function detectPayloadType(value: string): 'JSON' | 'RAW' {
  try {
    JSON.parse(value ?? '')
    return 'JSON'
  } catch {
    return 'RAW'
  }
}

function formatPayload(value: string): string {
  try {
    return JSON.stringify(JSON.parse(value ?? ''), null, 2)
  } catch {
    return value || '(empty)'
  }
}

function buildTree(topics: MqttTopic[]): TreeNode {
  const root: TreeNode = { name: '', fullPath: '', children: new Map() }
  for (const t of topics) {
    const parts = t.topic.split('/')
    let node = root
    let path = ''
    for (let i = 0; i < parts.length; i++) {
      const part = parts[i]
      path = path ? `${path}/${part}` : part
      if (!node.children.has(part)) {
        node.children.set(part, { name: part, fullPath: path, children: new Map() })
      }
      node = node.children.get(part)!
      if (i === parts.length - 1) {
        node.leaf = t
      }
    }
  }
  return root
}

function countLeaves(node: TreeNode): number {
  const selfCount = node.leaf ? 1 : 0
  const childrenCount = Array.from(node.children.values()).reduce(
    (sum, child) => sum + countLeaves(child),
    0
  )
  return selfCount + childrenCount
}

// ── Tree node component ───────────────────────────────────────────────────────

const TREE_PAGE_SIZE = 200

interface TreeNodeProps {
  node: TreeNode
  depth: number
  defaultOpen?: boolean
  onSelect?: (topic: MqttTopic) => void
}

function TreeNodeView({ node, depth, defaultOpen = false, onSelect }: TreeNodeProps) {
  const [open, setOpen] = useState(defaultOpen || depth < 1)
  const [visibleCount, setVisibleCount] = useState(TREE_PAGE_SIZE)
  const hasChildren = node.children.size > 0
  const isLeaf = !hasChildren && !!node.leaf
  const hasOwnTopicValue = !!node.leaf
  const indent = depth * 16

  if (isLeaf && node.leaf) {
    const t = node.leaf
    return (
      <div
        className="flex items-center gap-2 py-1.5 px-3 rounded-md hover:bg-muted/50 cursor-pointer text-sm group"
        style={{ paddingLeft: `${indent + 12}px` }}
        onClick={() => onSelect?.(t)}
      >
        <span className="mt-0.5 h-2 w-2 rounded-full bg-green-500 shrink-0" />
        <span className="font-mono font-medium shrink-0">{node.name}</span>
        <span className="text-muted-foreground font-mono truncate max-w-[200px]">
          {t.value || <em className="not-italic opacity-50">empty</em>}
        </span>
        <div className="ml-auto flex items-center gap-1.5 shrink-0">
          {t.retained && (
            <Badge variant="outline" className="text-xs border-orange-400 text-orange-500 py-0 px-1.5">
              retained
            </Badge>
          )}
          <Badge variant="secondary" className="text-xs py-0 px-1.5">
            QoS {t.qos}
          </Badge>
          <Badge variant="secondary" className="text-xs py-0 px-1.5">
            ×{t.count}
          </Badge>
          <span className="text-xs text-muted-foreground whitespace-nowrap">
            {formatRelativeTime(t.timestamp)}
          </span>
          <Eye className="h-3.5 w-3.5 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
        </div>
      </div>
    )
  }

  const leafCount = countLeaves(node)
  return (
    <div>
      <div
        className="flex items-center gap-1.5 w-full py-1.5 px-3 rounded-md hover:bg-muted/50 text-sm"
        style={{ paddingLeft: `${indent + 4}px` }}
      >
        <button
          onClick={() => { setOpen((o) => !o); setVisibleCount(TREE_PAGE_SIZE) }}
          className="shrink-0"
          aria-label={open ? `Collapse ${node.name}` : `Expand ${node.name}`}
        >
          {open ? (
            <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
          )}
        </button>

        <button
          onClick={() => {
            if (node.leaf) {
              onSelect?.(node.leaf)
              return
            }
            setOpen((o) => !o)
            setVisibleCount(TREE_PAGE_SIZE)
          }}
          className="flex items-center gap-1.5 min-w-0 flex-1 text-left"
        >
          <span className="font-mono font-semibold shrink-0">{node.name}</span>
          <Badge variant="outline" className="text-xs py-0 px-1.5 ml-1 shrink-0">
            {leafCount}
          </Badge>
          {hasOwnTopicValue && node.leaf && (
            <>
              <span className="text-muted-foreground font-mono truncate max-w-[220px] ml-1">
                {node.leaf.value || <em className="not-italic opacity-50">empty</em>}
              </span>
              <div className="ml-auto flex items-center gap-1.5 shrink-0">
                {node.leaf.retained && (
                  <Badge variant="outline" className="text-xs border-orange-400 text-orange-500 py-0 px-1.5">
                    retained
                  </Badge>
                )}
                <Badge variant="secondary" className="text-xs py-0 px-1.5">
                  QoS {node.leaf.qos}
                </Badge>
                <Badge variant="secondary" className="text-xs py-0 px-1.5">
                  ×{node.leaf.count}
                </Badge>
                <span className="text-xs text-muted-foreground whitespace-nowrap">
                  {formatRelativeTime(node.leaf.timestamp)}
                </span>
                <Eye className="h-3.5 w-3.5 text-muted-foreground" />
              </div>
            </>
          )}
        </button>
      </div>
      {open && (
        <div>
          {Array.from(node.children.values()).slice(0, visibleCount).map((child) => (
            <TreeNodeView key={child.fullPath} node={child} depth={depth + 1} onSelect={onSelect} />
          ))}
          {node.children.size > visibleCount && (
            <button
              className="flex items-center gap-1.5 py-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
              style={{ paddingLeft: `${indent + 28}px` }}
              onClick={(e) => { e.stopPropagation(); setVisibleCount(c => c + TREE_PAGE_SIZE) }}
            >
              Show {Math.min(TREE_PAGE_SIZE, node.children.size - visibleCount)} more
              <span className="opacity-50">({node.children.size - visibleCount} remaining)</span>
            </button>
          )}
        </div>
      )}
    </div>
  )
}

// ── Payload validation ────────────────────────────────────────────────────────

type PayloadType = 'RAW' | 'JSON' | 'XML'

function validatePayload(payload: string, type: PayloadType): string | null {
  if (!payload.trim()) return null
  if (type === 'JSON') {
    try { JSON.parse(payload) } catch { return 'Payload is not valid JSON' }
  } else if (type === 'XML') {
    const doc = new DOMParser().parseFromString(payload, 'text/xml')
    if (doc.querySelector('parsererror')) return 'Payload is not valid XML'
  }
  return null
}

// ── Publish Panel ─────────────────────────────────────────────────────────────

interface PublishPanelProps {
  // no clients needed — publish always uses the monitor's admin MQTT connection
}

function PublishPanel(_props: PublishPanelProps) {
  const [open, setOpen] = useState(false)
  const [topic, setTopic] = useState('')
  const [payload, setPayload] = useState('')
  const [payloadType, setPayloadType] = useState<PayloadType>('RAW')
  const [qos, setQos] = useState<string>('0')
  const [retain, setRetain] = useState(false)
  const [isPublishing, setIsPublishing] = useState(false)

  async function handlePublish() {
    if (!topic.trim()) {
      toast.error('Topic is required')
      return
    }
    const validationError = validatePayload(payload, payloadType)
    if (validationError) {
      toast.error(validationError)
      return
    }
    setIsPublishing(true)
    try {
      await monitorApi.publishMessage({
        topic: topic.trim(),
        payload,
        qos: parseInt(qos) as 0 | 1 | 2,
        retain,
      })
      toast.success(`Published to "${topic.trim()}"`)
    } catch {
      toast.error('Failed to publish message')
    } finally {
      setIsPublishing(false)
    }
  }

  return (
    <Card>
      {/* Accordion header */}
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center justify-between w-full px-6 py-4 text-left"
      >
        <div className="flex items-center gap-2">
          <Send className="h-4 w-4 text-muted-foreground" />
          <span className="font-semibold text-sm">Publish Message</span>
        </div>
        {open ? (
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-4 w-4 text-muted-foreground" />
        )}
      </button>

      {open && (
        <CardContent className="pt-0 pb-5 space-y-4">
          {/* Row 1: Topic + admin badge */}
          <div className="flex items-end gap-4">
            <div className="flex-1 space-y-1.5">
              <Label htmlFor="pub-topic">Topic</Label>
              <Input
                id="pub-topic"
                placeholder="e.g. sensors/temperature"
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label className="invisible">Connection</Label>
              <div className="flex items-center h-9 px-3 rounded-md border bg-muted/40 text-xs text-muted-foreground whitespace-nowrap">
                Admin connection
              </div>
            </div>
          </div>

          {/* Row 2: Payload type + QoS + Retain */}
          <div className="flex items-end gap-4">
            {/* Payload type toggle */}
            <div className="space-y-1.5">
              <Label>Payload Type</Label>
              <div className="flex rounded-md border overflow-hidden">
                {(['RAW', 'JSON', 'XML'] as PayloadType[]).map((t) => (
                  <button
                    key={t}
                    onClick={() => setPayloadType(t)}
                    className={`px-4 py-1.5 text-sm font-medium transition-colors ${
                      payloadType === t
                        ? 'bg-primary text-primary-foreground'
                        : 'bg-background text-muted-foreground hover:bg-muted'
                    }`}
                  >
                    {t}
                  </button>
                ))}
              </div>
            </div>

            {/* QoS */}
            <div className="space-y-1.5">
              <Label htmlFor="pub-qos">QoS</Label>
              <Select value={qos} onValueChange={setQos}>
                <SelectTrigger id="pub-qos" className="w-24">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="0">0 — At most once</SelectItem>
                  <SelectItem value="1">1 — At least once</SelectItem>
                  <SelectItem value="2">2 — Exactly once</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Retain */}
            <div className="space-y-1.5">
              <Label htmlFor="pub-retain">Retain</Label>
              <div className="flex items-center h-9">
                <Switch
                  id="pub-retain"
                  checked={retain}
                  onCheckedChange={setRetain}
                />
              </div>
            </div>
          </div>

          {/* Row 3: Payload textarea */}
          <div className="space-y-1.5">
            <Label htmlFor="pub-payload">Payload</Label>
            <Textarea
              id="pub-payload"
              placeholder={
                payloadType === 'JSON'
                  ? '{"key": "value"}'
                  : payloadType === 'XML'
                  ? '<root><key>value</key></root>'
                  : 'Enter payload...'
              }
              value={payload}
              onChange={(e) => setPayload(e.target.value)}
              className="font-mono text-sm min-h-[80px]"
            />
          </div>

          {/* Row 4: Publish button */}
          <div className="flex justify-end">
            <Button onClick={handlePublish} disabled={isPublishing}>
              <Send className="h-4 w-4 mr-2" />
              {isPublishing ? 'Publishing...' : 'Publish'}
            </Button>
          </div>
        </CardContent>
      )}
    </Card>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function MqttExplorerPage() {
  const [topics, setTopics] = useState<MqttTopic[]>([])
  const [selectedTopicHistory, setSelectedTopicHistory] = useState<MqttTopicHistoryMessage[]>([])
  const [isHistoryLoading, setIsHistoryLoading] = useState(false)
  const [search, setSearch] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [selectedTopic, setSelectedTopic] = useState<MqttTopic | null>(null)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchTopics = useCallback(async (showLoading = false) => {
    if (showLoading) setIsLoading(true)
    try {
      const data = await monitorApi.getTopics('db')
      setTopics(data.topics ?? [])
    } catch {
      toast.error('Failed to fetch MQTT topics')
    } finally {
      if (showLoading) setIsLoading(false)
    }
  }, [])

  const fetchSelectedTopicHistory = useCallback(async (topic: string) => {
    if (!topic.trim()) {
      setSelectedTopicHistory([])
      return
    }

    setIsHistoryLoading(true)
    try {
      const data = await monitorApi.getTopicHistory(topic, TOPIC_HISTORY_LIMIT)
      setSelectedTopicHistory(data.history ?? [])
    } catch {
      setSelectedTopicHistory([])
      toast.error('Failed to fetch topic history')
    } finally {
      setIsHistoryLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchTopics(true)
    intervalRef.current = setInterval(() => fetchTopics(false), 3000)
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [fetchTopics])

  // Keep selected topic up to date as data refreshes
  useEffect(() => {
    if (selectedTopic) {
      const updated = topics.find((t) => t.topic === selectedTopic.topic)
      if (updated) setSelectedTopic(updated)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topics])

  useEffect(() => {
    if (!selectedTopic) {
      setSelectedTopicHistory([])
      return
    }
    fetchSelectedTopicHistory(selectedTopic.topic)
  }, [selectedTopic?.topic, selectedTopic?.timestamp, fetchSelectedTopicHistory])

  const filtered = search
    ? topics.filter((t) => t.topic.toLowerCase().includes(search.toLowerCase()))
    : topics

  const tree = buildTree(filtered)

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Radio className="h-6 w-6" />
            MQTT Explorer
          </h1>
          <p className="text-muted-foreground text-sm">
            Live topic tree with values and metadata
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => fetchTopics(true)}
          disabled={isLoading}
        >
          <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      {/* Publish panel (accordion) */}
      <PublishPanel />

      {/* Filter bar */}
      <div className="flex items-center gap-3">
        <div className="relative max-w-sm w-full">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Filter topics..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-8"
          />
        </div>
        <Badge variant="secondary">
          {filtered.length} topic{filtered.length !== 1 ? 's' : ''}
        </Badge>
      </div>

      {/* Topic tree usando React*/}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">Topic Tree</CardTitle>
        </CardHeader>
        <CardContent className="p-2">
          {filtered.length === 0 ? (
            <p className="text-center py-8 text-muted-foreground text-sm">
              {isLoading
                ? 'Loading topics...'
                : topics.length === 0
                ? 'No topics received yet. Publish a message to see it here.'
                : 'No topics match the filter.'}
            </p>
          ) : (
            <div className="space-y-0.5">
              {Array.from(tree.children.values()).map((child) => (
                <TreeNodeView
                  key={child.fullPath}
                  node={child}
                  depth={0}
                  defaultOpen
                  onSelect={setSelectedTopic}
                />
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Payload detail Sheet */}
      <Sheet open={!!selectedTopic} onOpenChange={(o) => { if (!o) setSelectedTopic(null) }}>
        <SheetContent className="w-[520px] sm:max-w-[560px] overflow-y-auto">
          <SheetHeader>
            <SheetTitle className="font-mono text-sm break-all">
              {selectedTopic?.topic}
            </SheetTitle>
          </SheetHeader>
          {selectedTopic && (
            <div className="mt-4 space-y-3">
              <div className="flex flex-wrap gap-2">
                {selectedTopic.retained && (
                  <Badge variant="outline" className="border-orange-400 text-orange-500">
                    retained
                  </Badge>
                )}
                <Badge variant="secondary">QoS {selectedTopic.qos}</Badge>
                <Badge variant="secondary">×{selectedTopic.count} messages</Badge>
                <span className="text-xs text-muted-foreground self-center">
                  {formatRelativeTime(selectedTopic.timestamp)}
                </span>
              </div>
              <div className="rounded-md border bg-muted/30">
                <div className="flex items-center justify-between px-3 py-2 border-b">
                  <span className="text-xs font-medium text-muted-foreground">Payload</span>
                  <Badge variant="outline" className="text-xs">
                    {detectPayloadType(selectedTopic.value ?? '')}
                  </Badge>
                </div>
                <pre className="text-xs font-mono whitespace-pre-wrap break-all p-4 overflow-auto max-h-[60vh]">
                  {formatPayload(selectedTopic.value ?? '')}
                </pre>
              </div>

              <div className="rounded-md border">
                <div className="flex items-center justify-between px-3 py-2 border-b bg-muted/20">
                  <span className="text-xs font-medium text-muted-foreground">Message History</span>
                  <Badge variant="secondary" className="text-xs">
                    {selectedTopicHistory.length} captured
                  </Badge>
                </div>

                {isHistoryLoading ? (
                  <p className="p-4 text-xs text-muted-foreground">Loading topic history...</p>
                ) : selectedTopicHistory.length === 0 ? (
                  <p className="p-4 text-xs text-muted-foreground">No history captured for this topic yet.</p>
                ) : (
                  <div className="max-h-[52vh] overflow-y-auto divide-y">
                    {selectedTopicHistory.map((entry, idx) => (
                      <div key={entry.id} className="p-3 space-y-2">
                        <div className="flex flex-wrap items-center gap-2 text-xs">
                          <Badge variant="outline">#{selectedTopicHistory.length - idx}</Badge>
                          <span className="text-muted-foreground">{formatRelativeTime(entry.timestamp)}</span>
                          <Badge variant="secondary">QoS {entry.qos}</Badge>
                          <Badge variant="outline">{detectPayloadType(entry.value)}</Badge>
                          <Badge variant="outline">{entry.payload_bytes} B</Badge>
                          {entry.retained && (
                            <Badge variant="outline" className="border-orange-400 text-orange-500">
                              retained
                            </Badge>
                          )}
                        </div>
                        <pre className="text-xs font-mono whitespace-pre-wrap break-all rounded-md border bg-muted/20 p-3">
                          {formatPayload(entry.value)}
                        </pre>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </SheetContent>
      </Sheet>
    </div>
  )
}
