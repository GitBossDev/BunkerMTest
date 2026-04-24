import { NextRequest, NextResponse } from 'next/server'
import { verifyToken, COOKIE_NAME } from '@/lib/auth'
import { listUsers, createUserViaApi, EmailConflictError } from '@/lib/users-api'
import type { UserRole } from '@/types'

async function requireAdmin(request: NextRequest) {
  const token = request.cookies.get(COOKIE_NAME)?.value
  if (!token) return null
  const user = await verifyToken(token)
  if (!user || user.role !== 'admin') return null
  return user
}

// GET /api/auth/users — list all panel users (admin only)
export async function GET(request: NextRequest) {
  const admin = await requireAdmin(request)
  if (!admin) return NextResponse.json({ error: 'Forbidden' }, { status: 403 })

  try {
    const users = await listUsers()
    return NextResponse.json({ users }, { status: 200 })
  } catch (err) {
    console.error('List users error:', err)
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
  }
}

// POST /api/auth/users — create a new panel user (admin only)
export async function POST(request: NextRequest) {
  const admin = await requireAdmin(request)
  if (!admin) return NextResponse.json({ error: 'Forbidden' }, { status: 403 })

  try {
    const { email, password, firstName, lastName, role } = await request.json()

    if (!email || !password || !firstName || !lastName) {
      return NextResponse.json({ error: 'All fields are required' }, { status: 400 })
    }
    // Enforce password length to prevent bcrypt DoS (>72 bytes = wasted CPU)
    if (password.length < 8 || password.length > 128) {
      return NextResponse.json({ error: 'Password must be between 8 and 128 characters' }, { status: 400 })
    }
    const validRoles: UserRole[] = ['admin', 'user']
    if (role && !validRoles.includes(role)) {
      return NextResponse.json({ error: 'Invalid role' }, { status: 400 })
    }

    const newUser = await createUserViaApi({ email, password, firstName, lastName, role: role ?? 'admin' })
    return NextResponse.json({ user: newUser }, { status: 201 })
  } catch (err) {
    if (err instanceof EmailConflictError) {
      return NextResponse.json({ error: 'Email already registered' }, { status: 409 })
    }
    console.error('Create user error:', err)
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
  }
}
