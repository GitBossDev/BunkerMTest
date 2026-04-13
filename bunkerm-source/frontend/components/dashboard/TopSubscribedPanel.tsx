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
import { BookMarked } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { InfoTooltip, TipRow } from '@/components/ui/info-tooltip'
import { clientlogsApi } from '@/lib/api'

const BAR_COLORS = [
  '#8b5cf6', '#3b82f6', '#22c55e', '#f59e0b', '#ef4444',
  '#06b6d4', '#ec4899', '#14b8a6', '#f97316', '#84cc16',
  '#6366f1', '#a855f7', '#10b981', '#fbbf24', '#f43f5e',
]

interface TopSubscribedEntry {
  topic: string
  count: number
}

export function TopSubscribedPanel() {
  const [data, setData] = useState<{ top_subscribed: TopSubscribedEntry[]; total_distinct_subscribed: number } | null>(null)

  const fetchData = useCallback(async () => {
    try {
      const res = await clientlogsApi.getTopSubscribed(15)
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

  const topics = data?.top_subscribed ?? []
  const totalDistinct = data?.total_distinct_subscribed ?? 0

  const chartData = topics.map((t) => ({
    topic: t.topic.length > 30 ? `…${t.topic.slice(-28)}` : t.topic,
    count: t.count,
  }))

  return (
    <Card className="h-full">
      <CardHeader className="flex flex-row items-start justify-between pb-2">
        <div>
          <div className="flex items-center gap-2">
            <CardTitle className="text-sm font-medium">Top Subscribed Topics</CardTitle>
            <InfoTooltip side="bottom" content={
              <>
                <p className="font-semibold text-foreground mb-1">Top Subscribed Topics</p>
                <TipRow label="Topic" text="MQTT topic path that clients have subscribed to." />
                <TipRow label="Count" text="Number of subscribe events seen for that topic since the clientlogs service started. Resets on service restart." />
                <TipRow label="Distinct topics" text="Total unique topic patterns subscribed to since service start." />
              </>
            } />
          </div>
          <CardDescription className="text-xs">
            Top {topics.length} topics by subscription count
            <span className="ml-4 text-muted-foreground">
              {totalDistinct} distinct topics
            </span>
          </CardDescription>
        </div>
        <div className="p-2 rounded-lg bg-purple-500/10 shrink-0">
          <BookMarked className="h-4 w-4 text-purple-500" />
        </div>
      </CardHeader>
      <CardContent className="h-full">
        {chartData.length === 0 ? (
          <div className="flex items-center justify-center h-[200px] text-muted-foreground text-sm">
            No subscription data yet
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
                formatter={(v: number) => [v.toLocaleString(), 'Subscriptions']}
              />
              <Bar dataKey="count" name="Subscriptions" radius={[0, 3, 3, 0]}>
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
