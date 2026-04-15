'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
  LayoutDashboard,
  Users,
  Shield,
  UsersRound,
  FileText,
  Activity,
  Upload,
  Settings,
  Lock,
  ChevronRight,
  Wifi,
  Radio,
  KeyRound,
  UserCog,
  Cross,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Separator } from '@/components/ui/separator'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { useAuth } from '@/contexts/AuthContext'

interface NavItem {
  label: string
  href: string
  icon: React.ElementType
}

interface NavGroup {
  title: string
  items: NavItem[]
}

const BASE_NAV_GROUPS: NavGroup[] = [
  {
    title: 'Overview',
    items: [
      { label: 'Dashboard', href: '/dashboard', icon: LayoutDashboard },
    ],
  },
  {
    title: 'ACL',
    items: [
      { label: 'Clients', href: '/mqtt/clients', icon: Users },
      { label: 'Roles', href: '/mqtt/roles', icon: Shield },
      { label: 'Groups', href: '/mqtt/groups', icon: UsersRound },
    ],
  },
  {
    title: 'Tools',
    items: [
      { label: 'Connected Clients', href: '/mqtt/connected-clients', icon: Wifi },
      { label: 'MQTT Explorer', href: '/mqtt/explorer', icon: Radio },
      { label: 'Broker Logs', href: '/mqtt/broker-logs', icon: FileText },
      { label: 'Client Logs', href: '/mqtt/client-logs', icon: Activity },
    ],
  },
  {
    title: 'Monitoring',
    items: [
      { label: 'Alerts', href: '/ai/monitoring', icon: Activity },
    ],
  },
  {
    title: 'Configuration',
    items: [
      { label: 'Broker Config', href: '/mqtt/config', icon: Settings },
      { label: 'Security & ACL', href: '/mqtt/dynsec-config', icon: Lock },
      { label: 'Import Password', href: '/mqtt/import-password', icon: Upload },
      { label: 'Settings', href: '/settings', icon: KeyRound },
    ],
  },
]

interface SidebarProps {
  className?: string
  onNavClick?: () => void
}

export function Sidebar({ className, onNavClick }: SidebarProps) {
  const pathname = usePathname()
  const { user } = useAuth()

  // Inject the admin-only "Panel Users" link into the Configuration group
  const navGroups: NavGroup[] = BASE_NAV_GROUPS.map((group) => {
    if (group.title === 'Configuration' && user?.role === 'admin') {
      return {
        ...group,
        items: [
          ...group.items,
          { label: 'Panel Users', href: '/settings/users', icon: UserCog },
        ],
      }
    }
    return group
  })

  return (
    <TooltipProvider>
      <aside
        className={cn(
          'flex flex-col h-full bg-sidebar text-sidebar-foreground',
          className
        )}
      >
        {/* Logo */}
        <div className="flex items-center gap-2 px-4 h-14 border-b border-sidebar-border">
          <div className="flex items-center justify-center w-8 h-8 bg-primary-gradient rounded-lg shadow-sm">
            <Cross className="w-4 h-4 text-white" />
          </div>
          <span className="font-bold text-lg">BHM</span>
        </div>

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto py-4 px-3 space-y-6">
          {navGroups.map((group) => (
            <div key={group.title}>
              <p className="text-xs font-semibold text-sidebar-foreground/40 uppercase tracking-wider px-2 mb-2">
                {group.title}
              </p>
              <ul className="space-y-0.5">
                {group.items.map((item) => {
                  const isActive = pathname === item.href || pathname.startsWith(item.href + '/')
                  const Icon = item.icon
                  return (
                    <li key={item.href}>
                      <Link
                        href={item.href}
                        onClick={onNavClick}
                        className={cn(
                          'flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors',
                          isActive
                            ? 'bg-primary-gradient text-primary-foreground shadow-sm hover:brightness-105'
                            : 'text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-foreground'
                        )}
                      >
                        <Icon className="h-4 w-4 shrink-0" />
                        {item.label}
                        {isActive && <ChevronRight className="ml-auto h-3 w-3" />}
                      </Link>
                    </li>
                  )
                })}
              </ul>
            </div>
          ))}
        </nav>

        {/* Footer */}
        <div className="p-4 border-t border-sidebar-border">
          <p className="text-xs text-sidebar-foreground/40 text-center">
            Broker Health Management {process.env.NEXT_PUBLIC_CURRENT_VERSION || 'v1.0.0'}
          </p>
        </div>
      </aside>
    </TooltipProvider>
  )
}
