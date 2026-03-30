'use client'

import { useCallback, useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { toast } from 'sonner'
import {
  UserPlus, Trash2, Loader2, Shield, ShieldCheck, RefreshCw, KeyRound,
} from 'lucide-react'
import { useAuth } from '@/contexts/AuthContext'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import type { User, UserRole } from '@/types'

interface PanelUser extends Omit<User, 'createdAt'> {
  createdAt: string
}

const newUserSchema = z.object({
  firstName: z.string().min(1, 'First name is required'),
  lastName:  z.string().min(1, 'Last name is required'),
  email:     z.string().email('Invalid email address'),
  password:  z.string().min(6, 'Password must be at least 6 characters'),
  role:      z.enum(['admin', 'user']),
})

type NewUserForm = z.infer<typeof newUserSchema>

const resetPasswordSchema = z.object({
  password: z.string().min(6, 'Password must be at least 6 characters'),
})
type ResetPasswordForm = z.infer<typeof resetPasswordSchema>

function RoleBadge({ role }: { role: UserRole }) {
  return role === 'admin' ? (
    <Badge variant="default" className="gap-1">
      <ShieldCheck className="h-3 w-3" /> Admin
    </Badge>
  ) : (
    <Badge variant="secondary" className="gap-1">
      <Shield className="h-3 w-3" /> User
    </Badge>
  )
}

export default function UsersPage() {
  const { user: me } = useAuth()
  const router = useRouter()
  const [users, setUsers] = useState<PanelUser[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [showNewDialog, setShowNewDialog] = useState(false)
  const [resetTarget, setResetTarget] = useState<PanelUser | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)

  const fetchUsers = useCallback(async () => {
    setIsLoading(true)
    try {
      const res = await fetch('/api/auth/users')
      if (!res.ok) throw new Error()
      const data = await res.json()
      setUsers(data.users)
    } catch {
      toast.error('Failed to load users')
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    if (me && me.role !== 'admin') {
      router.replace('/dashboard')
      return
    }
    fetchUsers()
  }, [me, router, fetchUsers])

  // --- New user form ---
  const {
    register: regNew,
    handleSubmit: handleNew,
    reset: resetNew,
    setValue: setNewValue,
    formState: { errors: newErrors, isSubmitting: isCreating },
  } = useForm<NewUserForm>({
    resolver: zodResolver(newUserSchema),
    defaultValues: { role: 'admin' },
  })

  const onCreateUser = async (data: NewUserForm) => {
    const res = await fetch('/api/auth/users', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    const body = await res.json()
    if (!res.ok) {
      toast.error(body.error || 'Failed to create user')
      return
    }
    toast.success(`User ${data.email} created`)
    setShowNewDialog(false)
    resetNew()
    fetchUsers()
  }

  // --- Reset password form ---
  const {
    register: regReset,
    handleSubmit: handleReset,
    reset: resetPwForm,
    formState: { errors: resetErrors, isSubmitting: isResetting },
  } = useForm<ResetPasswordForm>({ resolver: zodResolver(resetPasswordSchema) })

  const onResetPassword = async (data: ResetPasswordForm) => {
    if (!resetTarget) return
    const res = await fetch(`/api/auth/users/${resetTarget.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: data.password }),
    })
    const body = await res.json()
    if (!res.ok) {
      toast.error(body.error || 'Failed to reset password')
      return
    }
    toast.success(`Password updated for ${resetTarget.email}`)
    setResetTarget(null)
    resetPwForm()
  }

  // --- Delete user ---
  const deleteUser = async (u: PanelUser) => {
    if (!confirm(`Delete user ${u.email}? This cannot be undone.`)) return
    setDeletingId(u.id)
    try {
      const res = await fetch(`/api/auth/users/${u.id}`, { method: 'DELETE' })
      const body = await res.json()
      if (!res.ok) {
        toast.error(body.error || 'Failed to delete user')
        return
      }
      toast.success('User deleted')
      fetchUsers()
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <div className="space-y-6 max-w-3xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Panel Users</h1>
          <p className="text-muted-foreground text-sm">Manage who can access this BunkerM instance</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={fetchUsers} disabled={isLoading}>
            <RefreshCw className={`h-4 w-4 mr-1 ${isLoading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
          <Button size="sm" onClick={() => setShowNewDialog(true)}>
            <UserPlus className="h-4 w-4 mr-1" />
            New User
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Users</CardTitle>
          <CardDescription>
            <span className="font-semibold">Admin</span> — full access to all features.{' '}
            <span className="font-semibold">User</span> — read-only access (cannot modify any configuration).
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex items-center justify-center h-32">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Email</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {users.map((u) => (
                  <TableRow key={u.id}>
                    <TableCell className="font-medium">
                      {u.firstName} {u.lastName}
                      {u.id === me?.id && (
                        <span className="ml-2 text-xs text-muted-foreground">(you)</span>
                      )}
                    </TableCell>
                    <TableCell>{u.email}</TableCell>
                    <TableCell><RoleBadge role={u.role} /></TableCell>
                    <TableCell className="text-muted-foreground text-sm">
                      {new Date(u.createdAt).toLocaleDateString()}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-2">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => { setResetTarget(u); resetPwForm() }}
                          title="Reset password"
                        >
                          <KeyRound className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-destructive hover:text-destructive"
                          disabled={deletingId === u.id || u.id === me?.id}
                          onClick={() => deleteUser(u)}
                          title={u.id === me?.id ? 'Cannot delete your own account' : 'Delete user'}
                        >
                          {deletingId === u.id
                            ? <Loader2 className="h-4 w-4 animate-spin" />
                            : <Trash2 className="h-4 w-4" />}
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* New User Dialog */}
      <Dialog open={showNewDialog} onOpenChange={(open) => { setShowNewDialog(open); if (!open) resetNew() }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create New User</DialogTitle>
            <DialogDescription>Add a new user to manage this BunkerM instance.</DialogDescription>
          </DialogHeader>
          <form onSubmit={handleNew(onCreateUser)} className="space-y-4 mt-2">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label htmlFor="firstName">First Name</Label>
                <Input id="firstName" placeholder="John" {...regNew('firstName')} />
                {newErrors.firstName && <p className="text-xs text-destructive">{newErrors.firstName.message}</p>}
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="lastName">Last Name</Label>
                <Input id="lastName" placeholder="Doe" {...regNew('lastName')} />
                {newErrors.lastName && <p className="text-xs text-destructive">{newErrors.lastName.message}</p>}
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="newEmail">Email</Label>
              <Input id="newEmail" type="email" placeholder="user@company.com" {...regNew('email')} />
              {newErrors.email && <p className="text-xs text-destructive">{newErrors.email.message}</p>}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="newPassword">Password</Label>
              <Input id="newPassword" type="password" placeholder="Min. 6 characters" {...regNew('password')} />
              {newErrors.password && <p className="text-xs text-destructive">{newErrors.password.message}</p>}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="role">Role</Label>
              <Select defaultValue="admin" onValueChange={(v) => setNewValue('role', v as UserRole)}>
                <SelectTrigger id="role">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="admin">
                    <div className="flex items-center gap-2">
                      <ShieldCheck className="h-4 w-4" /> Admin — full access
                    </div>
                  </SelectItem>
                  <SelectItem value="user">
                    <div className="flex items-center gap-2">
                      <Shield className="h-4 w-4" /> User — read-only
                    </div>
                  </SelectItem>
                </SelectContent>
              </Select>
              {newErrors.role && <p className="text-xs text-destructive">{newErrors.role.message}</p>}
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button type="button" variant="outline" onClick={() => { setShowNewDialog(false); resetNew() }}>
                Cancel
              </Button>
              <Button type="submit" disabled={isCreating}>
                {isCreating && <Loader2 className="h-4 w-4 animate-spin mr-1" />}
                Create User
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Reset Password Dialog */}
      <Dialog open={!!resetTarget} onOpenChange={(open) => { if (!open) { setResetTarget(null); resetPwForm() } }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reset Password</DialogTitle>
            <DialogDescription>
              Set a new password for <span className="font-medium">{resetTarget?.email}</span>.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleReset(onResetPassword)} className="space-y-4 mt-2">
            <div className="space-y-1.5">
              <Label htmlFor="resetPassword">New Password</Label>
              <Input id="resetPassword" type="password" placeholder="Min. 6 characters" {...regReset('password')} />
              {resetErrors.password && <p className="text-xs text-destructive">{resetErrors.password.message}</p>}
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button type="button" variant="outline" onClick={() => { setResetTarget(null); resetPwForm() }}>
                Cancel
              </Button>
              <Button type="submit" disabled={isResetting}>
                {isResetting && <Loader2 className="h-4 w-4 animate-spin mr-1" />}
                Update Password
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}
