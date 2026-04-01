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

export interface AnomalyAlert {
  id: string
  entity_type: string
  entity_id: string
  anomaly_type: string
  severity: AlertSeverity
  description: string
  acknowledged: boolean
  created_at: string
}

interface NotificationsState {
  brokerAlerts: BrokerAlert[]
  anomalyAlerts: AnomalyAlert[]
  /** Count of unacknowledged critical+high alerts (badge number) */
  badgeCount: number
  loading: boolean
  acknowledgeAnomaly: (id: string) => Promise<void>
  acknowledgeBroker: (id: string) => Promise<void>
  refresh: () => void
}

const BROKER_POLL_MS = 30_000
const ANOMALY_POLL_MS = 60_000

export function useNotifications(role?: string): NotificationsState {
  const isAdmin = role === 'admin'
  const [brokerAlerts, setBrokerAlerts] = useState<BrokerAlert[]>([])
  const [anomalyAlerts, setAnomalyAlerts] = useState<AnomalyAlert[]>([])
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
      // silently ignore — broker panel shows connection status separately
    }
  }, [isAdmin])

  const fetchAnomalyAlerts = useCallback(async () => {
    try {
      const res = await fetch('/api/proxy/ai/api/v1/alerts?acknowledged=false')
      if (res.ok) {
        const data: AnomalyAlert[] = await res.json()
        // Only surface high/critical to the badge; keep all for dropdown
        setAnomalyAlerts(
          data.filter(a => ['critical', 'high', 'medium', 'low'].includes(a.severity))
        )
      }
    } catch {
      // silently ignore
    }
  }, [])

  // Initial fetch + periodic polling
  useEffect(() => {
    let cancelled = false
    setLoading(true)

    const doFetch = async () => {
      await Promise.all([fetchBrokerAlerts(), fetchAnomalyAlerts()])
      if (!cancelled) setLoading(false)
    }

    doFetch()

    const brokerTimer = setInterval(fetchBrokerAlerts, BROKER_POLL_MS)
    const anomalyTimer = setInterval(fetchAnomalyAlerts, ANOMALY_POLL_MS)

    return () => {
      cancelled = true
      clearInterval(brokerTimer)
      clearInterval(anomalyTimer)
    }
  }, [fetchBrokerAlerts, fetchAnomalyAlerts, refreshKey])

  const acknowledgeAnomaly = useCallback(async (id: string) => {
    try {
      const res = await fetch(`/api/proxy/ai/api/v1/alerts/${id}/acknowledge`, {
        method: 'POST',
      })
      if (res.ok) {
        setAnomalyAlerts(prev => prev.filter(a => a.id !== id))
      }
    } catch {
      // ignore
    }
  }, [])

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

  const badgeCount =
    brokerAlerts.filter(a => a.severity === 'critical' || a.severity === 'high').length +
    anomalyAlerts.filter(a => !a.acknowledged && (a.severity === 'critical' || a.severity === 'high')).length

  return { brokerAlerts, anomalyAlerts, badgeCount, loading, acknowledgeAnomaly, acknowledgeBroker, refresh }
}
