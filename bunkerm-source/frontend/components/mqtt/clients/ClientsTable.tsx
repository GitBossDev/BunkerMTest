'use client'

import { useState } from 'react'
import { useSession } from 'next-auth/react'
import { toast } from 'sonner'
import { Search, Plus, Trash2, Shield, Users, RefreshCw, ChevronLeft, ChevronRight, MoreHorizontal } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { CreateClientDialog } from './CreateClientDialog'
import { ClientRolesDialog } from './ClientRolesDialog'
import { ClientGroupsDialog } from './ClientGroupsDialog'
import { dynsecApi } from '@/lib/api'
import type { MqttClient, Role, Group } from '@/types'

interface ClientsTableProps {
  clients: MqttClient[]        // Current page's clients (already paginated by parent)
  availableRoles: Role[]
  availableGroups: Group[]
  onRefresh: () => void
  // Server-side pagination & search (controlled by parent/page)
  total: number
  page: number
  totalPages: number
  search: string
  onSearchChange: (value: string) => void
  onPageChange: (page: number) => void
}

/** Returns a compact list of page numbers + '...' separators for ellipsis pagination. */
function buildPageNumbers(current: number, total: number): (number | '...')[] {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1)
  const pages: (number | '...')[] = [1]
  if (current > 3) pages.push('...')
  for (let p = Math.max(2, current - 1); p <= Math.min(total - 1, current + 1); p++) pages.push(p)
  if (current < total - 2) pages.push('...')
  pages.push(total)
  return pages
}

export function ClientsTable({
  clients,
  availableRoles,
  availableGroups,
  onRefresh,
  total,
  page,
  totalPages,
  search,
  onSearchChange,
  onPageChange,
}: ClientsTableProps) {
  const { data: session } = useSession()
  const userRole = (session?.user as { role?: string })?.role ?? 'admin'
  const isAdmin = userRole === 'admin'

  const ADMIN_USERNAME = 'admin'
  const [createOpen, setCreateOpen] = useState(false)
  const [rolesDialogClient, setRolesDialogClient] = useState<MqttClient | null>(null)
  const [groupsDialogClient, setGroupsDialogClient] = useState<MqttClient | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<MqttClient | null>(null)
  const [deletingUsername, setDeletingUsername] = useState<string | null>(null)
  const [togglingUsername, setTogglingUsername] = useState<string | null>(null)
  // Optimistic UI: tracks toggle state locally between re-fetches
  const [localDisabled, setLocalDisabled] = useState<Record<string, boolean>>({})

  const handleToggleDisabled = async (client: MqttClient) => {
    // Use local tracked state; if unknown, assume enabled (false)
    const isCurrentlyDisabled = localDisabled[client.username] ?? client.disabled ?? false
    setTogglingUsername(client.username)
    try {
      if (isCurrentlyDisabled) {
        await dynsecApi.enableClient(client.username)
        setLocalDisabled((prev) => ({ ...prev, [client.username]: false }))
        toast.success(`Client "${client.username}" enabled successfully`)
      } else {
        await dynsecApi.disableClient(client.username)
        setLocalDisabled((prev) => ({ ...prev, [client.username]: true }))
        toast.success(`Client "${client.username}" disabled successfully`)
      }
      onRefresh()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to update client status')
    } finally {
      setTogglingUsername(null)
    }
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    setDeletingUsername(deleteTarget.username)
    try {
      await dynsecApi.deleteClient(deleteTarget.username)
      toast.success(`Client "${deleteTarget.username}" deleted`)
      setDeleteTarget(null)
      onRefresh()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to delete client')
    } finally {
      setDeletingUsername(null)
    }
  }

  return (
    <TooltipProvider>
      <div className="space-y-4">
        {/* Toolbar */}
        <div className="flex items-center gap-3">
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search clients..."
              value={search}
              onChange={(e) => onSearchChange(e.target.value)}
              className="pl-9"
            />
          </div>
          <Button variant="outline" size="icon" onClick={onRefresh} title="Refresh">
            <RefreshCw className="h-4 w-4" />
          </Button>
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="h-4 w-4 mr-2" />
            Create Client
          </Button>
        </div>

        {/* Table */}
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Username</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Roles</TableHead>
                <TableHead>Groups</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {clients.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} className="text-center py-8 text-muted-foreground">
                    {search ? 'No clients match your search.' : 'No clients found.'}
                  </TableCell>
                </TableRow>
              ) : (
                clients.map((client) => (
                  <TableRow key={client.username}>
                    <TableCell className="font-medium">{client.username}</TableCell>

                    <TableCell>
                      {(() => {
                        const disabled = localDisabled[client.username] ?? client.disabled ?? false
                        return (
                          <Badge variant={disabled ? 'destructive' : 'success'}>
                            {disabled ? 'Disabled' : 'Active'}
                          </Badge>
                        )
                      })()}
                    </TableCell>

                    <TableCell>
                      <Badge variant="secondary">
                        {(client.roles ?? []).length} role
                        {(client.roles ?? []).length !== 1 ? 's' : ''}
                      </Badge>
                    </TableCell>

                    <TableCell>
                      <Badge variant="outline">
                        {(client.groups ?? []).length} group
                        {(client.groups ?? []).length !== 1 ? 's' : ''}
                      </Badge>
                    </TableCell>

                    <TableCell>
                      <div className="flex items-center justify-end gap-2">
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <div className="flex items-center">
                              {(() => {
                                const disabled = localDisabled[client.username] ?? client.disabled ?? false
                                return (
                                  <Switch
                                    checked={!disabled}
                                    onCheckedChange={() => handleToggleDisabled(client)}
                                    disabled={togglingUsername === client.username || client.username === ADMIN_USERNAME}
                                    aria-label={`${disabled ? 'Enable' : 'Disable'} ${client.username}`}
                                  />
                                )
                              })()}
                            </div>
                          </TooltipTrigger>
                          <TooltipContent>
                            {client.username === ADMIN_USERNAME
                              ? 'Admin client — protected'
                              : (localDisabled[client.username] ?? client.disabled ?? false) ? 'Enable client' : 'Disable client'}
                          </TooltipContent>
                        </Tooltip>

                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => setRolesDialogClient(client)}
                              aria-label={`Manage roles for ${client.username}`}
                            >
                              <Shield className="h-4 w-4" />
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>Manage roles</TooltipContent>
                        </Tooltip>

                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => setGroupsDialogClient(client)}
                              aria-label={`Manage groups for ${client.username}`}
                            >
                              <Users className="h-4 w-4" />
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>Manage groups</TooltipContent>
                        </Tooltip>

                        {isAdmin && (
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button
                                variant="ghost"
                                size="icon"
                                onClick={() => setDeleteTarget(client)}
                                className="text-destructive hover:text-destructive hover:bg-destructive/10"
                                aria-label={`Delete ${client.username}`}
                                disabled={client.username === ADMIN_USERNAME}
                              >
                                <Trash2 className="h-4 w-4" />
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent>{client.username === ADMIN_USERNAME ? 'Admin client — protected' : 'Delete client'}</TooltipContent>
                          </Tooltip>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>

        {/* Summary + pagination */}
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>{total} client{total !== 1 ? 's' : ''}{search ? ` matching "${search}"` : ''}</span>
          {totalPages > 1 && (
            <div className="flex items-center gap-1">
              <Button variant="ghost" size="sm" className="h-7 px-2" onClick={() => onPageChange(Math.max(1, page - 1))} disabled={page <= 1}>
                <ChevronLeft className="h-3.5 w-3.5" />
              </Button>
              {buildPageNumbers(page, totalPages).map((p, i) =>
                p === '...' ? (
                  <span key={`ellipsis-${i}`} className="flex items-center justify-center h-7 w-7 text-muted-foreground">
                    <MoreHorizontal className="h-3.5 w-3.5" />
                  </span>
                ) : (
                  <Button
                    key={p}
                    variant={p === page ? 'secondary' : 'ghost'}
                    size="sm"
                    className="h-7 w-7 p-0 text-xs"
                    onClick={() => onPageChange(p as number)}
                  >
                    {p}
                  </Button>
                )
              )}
              <Button variant="ghost" size="sm" className="h-7 px-2" onClick={() => onPageChange(Math.min(totalPages, page + 1))} disabled={page >= totalPages}>
                <ChevronRight className="h-3.5 w-3.5" />
              </Button>
            </div>
          )}
        </div>
      </div>

      {/* Create client dialog */}
      <CreateClientDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onSuccess={onRefresh}
      />

      {/* Roles dialog */}
      <ClientRolesDialog
        client={rolesDialogClient}
        open={rolesDialogClient !== null}
        onOpenChange={(v) => { if (!v) setRolesDialogClient(null) }}
        availableRoles={availableRoles}
        onSuccess={onRefresh}
      />

      {/* Groups dialog */}
      <ClientGroupsDialog
        client={groupsDialogClient}
        open={groupsDialogClient !== null}
        onOpenChange={(v) => { if (!v) setGroupsDialogClient(null) }}
        availableGroups={availableGroups}
        onSuccess={onRefresh}
      />

      {/* Delete confirmation dialog */}
      <Dialog open={deleteTarget !== null} onOpenChange={(v) => { if (!v) setDeleteTarget(null) }}>
        <DialogContent className="sm:max-w-[400px]">
          <DialogHeader>
            <DialogTitle>Delete Client</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete client{' '}
              <span className="font-semibold text-foreground">{deleteTarget?.username}</span>?
              This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={deletingUsername !== null}
            >
              {deletingUsername ? 'Deleting...' : 'Delete'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </TooltipProvider>
  )
}
