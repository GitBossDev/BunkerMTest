import { NextRequest, NextResponse } from 'next/server'
import { verifyToken, COOKIE_NAME } from '@/lib/auth'
import { deleteUserViaApi, resetUserPasswordViaApi } from '@/lib/users-api'

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

  try {
    await deleteUserViaApi(id)
    return NextResponse.json({ message: 'User deleted' }, { status: 200 })
  } catch (err) {
    const msg = err instanceof Error ? err.message : 'Internal server error'
    const status = msg.includes('not found') ? 404 : msg.includes('last admin') ? 400 : 500
    return NextResponse.json({ error: msg }, { status })
  }
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
  if (!password || password.length < 8 || password.length > 128) {
    return NextResponse.json({ error: 'Password must be between 8 and 128 characters' }, { status: 400 })
  }

  try {
    const user = await resetUserPasswordViaApi(id, password)
    return NextResponse.json({ user }, { status: 200 })
  } catch (err) {
    const msg = err instanceof Error ? err.message : 'Internal server error'
    const status = msg.includes('not found') ? 404 : 500
    return NextResponse.json({ error: msg }, { status })
  }
}
