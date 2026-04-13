'use client'

import { useEffect, useState, useCallback, useRef } from 'react'
import { RefreshCw } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { ClientsTable } from '@/components/mqtt/clients/ClientsTable'
import { dynsecApi } from '@/lib/api'
import type { ClientSummary, MqttClient, Role, Group } from '@/types'

const PAGE_SIZE = 50

export default function ClientsPage() {
  const [clients, setClients] = useState<MqttClient[]>([])
  const [roles, setRoles] = useState<Role[]>([])
  const [groups, setGroups] = useState<Group[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  // Server-side pagination & search state
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [total, setTotal] = useState(0)
  const [totalPages, setTotalPages] = useState(1)
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Core fetch — reads page+search from dynamic-security.json in one backend call (no N+1)
  const fetchClients = useCallback(async (
    p: number,
    s: string,
    showRefresh = false,
  ) => {
    if (showRefresh) setRefreshing(true)
    try {
      const [res, rolesRes, groupsRes] = await Promise.all([
        dynsecApi.getClientsPaginated({ page: p, limit: PAGE_SIZE, search: s || undefined }),
        dynsecApi.getRoles(),
        dynsecApi.getGroups(),
      ])
      // Map flat role/group string arrays to the { rolename, groupname } shape
      const clientsList: MqttClient[] = res.clients.map((client: ClientSummary) => ({
        username: client.username,
        disabled: client.disabled,
        roles: client.roles.map((roleName) => ({ rolename: roleName })),
        groups: client.groups.map((groupName) => ({ groupname: groupName })),
      }))
      setClients(clientsList)
      setTotal(res.total)
      setTotalPages(res.pages)
      // If a delete left us on a now-empty page, clamp back
      if (p > res.pages) setPage(Math.max(1, res.pages))
      setRoles(rolesRes as Role[])
      setGroups(groupsRes as Group[])
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to load data')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  // Initial load
  useEffect(() => {
    fetchClients(1, '')
  }, [fetchClients])

  // Debounced search — resets to page 1 after 300 ms idle
  const handleSearchChange = useCallback((value: string) => {
    setSearch(value)
    if (searchTimer.current) clearTimeout(searchTimer.current)
    searchTimer.current = setTimeout(() => {
      setPage(1)
      fetchClients(1, value)
    }, 300)
  }, [fetchClients])

  const handlePageChange = useCallback((newPage: number) => {
    setPage(newPage)
    fetchClients(newPage, search)
  }, [search, fetchClients])

  const handleRefresh = useCallback(() => {
    fetchClients(page, search, true)
  }, [page, search, fetchClients])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="flex flex-col items-center gap-3 text-muted-foreground">
          <RefreshCw className="h-6 w-6 animate-spin" />
          <p className="text-sm">Loading clients...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">MQTT Clients</h1>
          <p className="text-muted-foreground text-sm mt-1">
            Manage MQTT client accounts, their roles and group memberships.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={handleRefresh}
          disabled={refreshing}
        >
          <RefreshCw className={`h-4 w-4 mr-2 ${refreshing ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      <ClientsTable
        clients={clients}
        availableRoles={roles}
        availableGroups={groups}
        onRefresh={handleRefresh}
        total={total}
        page={page}
        totalPages={totalPages}
        search={search}
        onSearchChange={handleSearchChange}
        onPageChange={handlePageChange}
      />
    </div>
  )
}

