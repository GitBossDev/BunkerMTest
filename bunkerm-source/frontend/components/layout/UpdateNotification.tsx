'use client'
import { Bell, AlertTriangle, AlertCircle, Activity, RefreshCw, CheckCheck } from 'lucide-react'
import { useNotifications, type AlertSeverity } from '@/hooks/useNotifications'
import { useAuth } from '@/contexts/AuthContext'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

function timeAgo(isoString: string): string {
  const ms = Date.now() - new Date(isoString).getTime()
  const s = Math.floor(ms / 1000)
  if (s < 60) return `${s}s ago`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

function SeverityIcon({ severity }: { severity: AlertSeverity }) {
  if (severity === 'critical') return <AlertCircle className="h-4 w-4 text-destructive shrink-0" />
  if (severity === 'high') return <AlertTriangle className="h-4 w-4 text-orange-500 shrink-0" />
  return <AlertTriangle className="h-4 w-4 text-yellow-500 shrink-0" />
}

export function UpdateNotification() {
  const { user } = useAuth()
  const { brokerAlerts, badgeCount, loading, acknowledgeBroker, refresh } =
    useNotifications(user?.role)

  // Bell is only meaningful for admins (broker alerts are admin-only)
  if (user?.role !== 'admin') return null

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="relative">
          <Bell className="h-4 w-4" />
          {badgeCount > 0 && (
            <span className="absolute -top-0.5 -right-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-destructive text-[10px] font-bold text-destructive-foreground">
              {badgeCount > 9 ? '9+' : badgeCount}
            </span>
          )}
          <span className="sr-only">Broker Alerts</span>
        </Button>
      </DropdownMenuTrigger>

      <DropdownMenuContent className="w-96" align="end">
        <DropdownMenuLabel className="flex items-center justify-between">
          <span>Broker Alerts</span>
          <Button variant="ghost" size="sm" className="h-6 w-6 p-0" onClick={refresh} title="Refresh">
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
          </Button>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />

        <div className="max-h-96 overflow-y-auto">
          {brokerAlerts.length === 0 ? (
            <div className="p-4 flex items-center gap-3 text-muted-foreground">
              <Activity className="h-4 w-4 shrink-0 text-green-500" />
              <span className="text-sm">All systems normal — no active alerts.</span>
            </div>
          ) : (
            brokerAlerts.map(alert => (
              <div key={alert.id} className="px-3 py-2 flex items-start gap-2.5 hover:bg-muted/50">
                <SeverityIcon severity={alert.severity} />
                <div className="flex-1 min-w-0 space-y-0.5">
                  <p className="text-sm font-medium leading-snug">{alert.title}</p>
                  <p className="text-xs text-muted-foreground leading-snug line-clamp-2">{alert.description}</p>
                  <p className="text-[11px] text-muted-foreground/60">{timeAgo(alert.timestamp)}</p>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 px-2 text-[11px] shrink-0"
                  onClick={() => acknowledgeBroker(alert.id)}
                >
                  <CheckCheck className="h-3 w-3 mr-1" />
                  Ack
                </Button>
              </div>
            ))
          )}
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
