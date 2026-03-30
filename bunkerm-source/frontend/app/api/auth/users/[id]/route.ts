import { NextRequest, NextResponse } from 'next/server'
import { verifyToken, COOKIE_NAME } from '@/lib/auth'
import { readUsers, deleteUser, writeUsers, stripHash } from '@/lib/users'
import bcrypt from 'bcryptjs'

async function requireAdmin(request: NextRequest) {
  const token = request.cookies.get(COOKIE_NAME)?.value
  if (!token) return null
  const user = await verifyToken(token)
  if (!user || user.role !== 'admin') return null
  return user
}

// DELETE /api/auth/users/[id] — remove a panel user (admin only)
export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const admin = await requireAdmin(request)
  if (!admin) return NextResponse.json({ error: 'Forbidden' }, { status: 403 })

  const { id } = await params
  if (id === admin.id) {
    return NextResponse.json({ error: 'Cannot delete your own account' }, { status: 400 })
  }

  const users = readUsers()
  const admins = users.filter((u) => u.role === 'admin')
  const target = users.find((u) => u.id === id)
  if (!target) return NextResponse.json({ error: 'User not found' }, { status: 404 })

  if (target.role === 'admin' && admins.length <= 1) {
    return NextResponse.json({ error: 'Cannot delete the last admin account' }, { status: 400 })
  }

  const success = deleteUser(id)
  if (!success) return NextResponse.json({ error: 'User not found' }, { status: 404 })

  return NextResponse.json({ message: 'User deleted' }, { status: 200 })
}

// PATCH /api/auth/users/[id] — reset password for a panel user (admin only)
export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const admin = await requireAdmin(request)
  if (!admin) return NextResponse.json({ error: 'Forbidden' }, { status: 403 })

  const { id } = await params
  const { password } = await request.json()
  if (!password || password.length < 6) {
    return NextResponse.json({ error: 'Password must be at least 6 characters' }, { status: 400 })
  }

  const users = readUsers()
  const user = users.find((u) => u.id === id)
  if (!user) return NextResponse.json({ error: 'User not found' }, { status: 404 })

  user.passwordHash = await bcrypt.hash(password, 10)
  writeUsers(users)

  return NextResponse.json({ user: stripHash(user) }, { status: 200 })
}
