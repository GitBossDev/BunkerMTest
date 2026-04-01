'use client'
import { useState, useEffect, useCallback, useRef } from 'react'

export type AlertSeverity = 'critical' | 'high' | 'medium' | 'low'

export interface BrokerAlert {
  id: string
  type: string
  severity: AlertSeverity
  title: string
  description: string
  timestamp: string
}

interface NotificationsState {
  brokerAlerts: BrokerAlert[]
  badgeCount: number
  loading: boolean
  acknowledgeBroker: (id: string) => Promise<void>
  refresh: () => void
}

const BROKER_POLL_MS = 30_000

export function useNotifications(role?: string): NotificationsState {
  const isAdmin = role === 'admin'
  const [brokerAlerts, setBrokerAlerts] = useState<BrokerAlert[]>([])
  const [loading, setLoading] = useState(false)
  const refreshKeyRef = useRef(0)
  const [refreshKey, setRefreshKey] = useState(0)

  const fetchBrokerAlerts = useCallback(async () => {
    if (!isAdmin) { setBrokerAlerts([]); return }
    try {
      const res = await fetch('/api/proxy/monitor/alerts/broker')
      if (res.ok) {
        const data = await res.json()
        setBrokerAlerts(data.alerts ?? [])
      }
    } catch {
      // silently ignore
    }
  }, [isAdmin])

  useEffect(() => {
    let cancelled = false
    setLoading(true)

    fetchBrokerAlerts().then(() => {
      if (!cancelled) setLoading(false)
    })

    const brokerTimer = setInterval(fetchBrokerAlerts, BROKER_POLL_MS)
    return () => {
      cancelled = true
      clearInterval(brokerTimer)
    }
  }, [fetchBrokerAlerts, refreshKey])

  const acknowledgeBroker = useCallback(async (id: string) => {
    try {
      const res = await fetch(`/api/proxy/monitor/alerts/broker/${id}/acknowledge`, {
        method: 'POST',
      })
      if (res.ok) {
        setBrokerAlerts(prev => prev.filter(a => a.id !== id))
      }
    } catch {
      // ignore
    }
  }, [])

  const refresh = useCallback(() => {
    refreshKeyRef.current += 1
    setRefreshKey(refreshKeyRef.current)
  }, [])

  const badgeCount = brokerAlerts.filter(
    a => a.severity === 'critical' || a.severity === 'high'
  ).length

  return { brokerAlerts, badgeCount, loading, acknowledgeBroker, refresh }
}
