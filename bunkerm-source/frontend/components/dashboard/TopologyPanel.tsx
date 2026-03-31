'use client'

import { useState, useEffect, useCallback } from 'react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts'
import { Network } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { monitorApi } from '@/lib/api'
import type { TopologyStats } from '@/types'

const BAR_COLORS = [
  '#3b82f6', '#8b5cf6', '#22c55e', '#f59e0b', '#ef4444',
  '#06b6d4', '#ec4899', '#14b8a6', '#f97316', '#84cc16',
  '#6366f1', '#a855f7', '#10b981', '#fbbf24', '#f43f5e',
]

export function TopologyPanel() {
  const [data, setData] = useState<TopologyStats | null>(null)

  const fetchData = useCallback(async () => {
    try {
      const res = await monitorApi.getTopologyStats(15) as TopologyStats
      setData(res)
    } catch {
      // fail silently
    }
  }, [])

  useEffect(() => {
    fetchData()
    const id = setInterval(fetchData, 30_000)
    return () => clearInterval(id)
  }, [fetchData])

  const topics      = data?.top_topics ?? []
  const totalTopics = data?.total_distinct_topics ?? 0
  const disconnected = data?.clients_disconnected ?? 0
  const expired     = data?.clients_expired ?? 0

  const chartData = topics.map((t) => ({
    topic: t.topic.length > 30 ? `…${t.topic.slice(-28)}` : t.topic,
    count: t.count,
  }))

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between pb-2">
        <div>
          <CardTitle className="text-sm font-medium">Topic Topology</CardTitle>
          <CardDescription className="text-xs">
            Top {topics.length} topics by message count
            <span className="ml-4 text-muted-foreground">
              {totalTopics} distinct topics
            </span>
            {disconnected > 0 && (
              <span className="ml-4 text-orange-500">{disconnected} disconnected</span>
            )}
            {expired > 0 && (
              <span className="ml-4 text-red-500">{expired} expired</span>
            )}
          </CardDescription>
        </div>
        <div className="p-2 rounded-lg bg-blue-500/10 shrink-0">
          <Network className="h-4 w-4 text-blue-500" />
        </div>
      </CardHeader>
      <CardContent>
        {chartData.length === 0 ? (
          <div className="flex items-center justify-center h-[200px] text-muted-foreground text-sm">
            No topic data yet
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={Math.max(200, chartData.length * 28)}>
            <BarChart
              layout="vertical"
              data={chartData}
              margin={{ top: 0, right: 20, left: 10, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" horizontal={false} className="stroke-muted" />
              <XAxis type="number" tick={{ fontSize: 10 }} />
              <YAxis
                type="category"
                dataKey="topic"
                width={180}
                tick={{ fontSize: 10 }}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'hsl(var(--card))',
                  border: '1px solid hsl(var(--border))',
                  borderRadius: '8px',
                  fontSize: '12px',
                }}
                formatter={(v: number) => [v.toLocaleString(), 'Messages']}
              />
              <Bar dataKey="count" name="Messages" radius={[0, 3, 3, 0]}>
                {chartData.map((_, i) => (
                  <Cell key={i} fill={BAR_COLORS[i % BAR_COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  )
}
