import { NextRequest, NextResponse } from 'next/server'
import { verifyToken, COOKIE_NAME } from '@/lib/auth'
import { readUsers, createUser, findUserByEmail, stripHash } from '@/lib/users'
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

  const users = readUsers().map(stripHash)
  return NextResponse.json({ users }, { status: 200 })
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
    if (password.length < 6) {
      return NextResponse.json({ error: 'Password must be at least 6 characters' }, { status: 400 })
    }
    const validRoles: UserRole[] = ['admin', 'user']
    if (role && !validRoles.includes(role)) {
      return NextResponse.json({ error: 'Invalid role' }, { status: 400 })
    }
    if (findUserByEmail(email)) {
      return NextResponse.json({ error: 'Email already registered' }, { status: 409 })
    }

    const newUser = await createUser({ email, password, firstName, lastName, role: role ?? 'admin' })
    return NextResponse.json({ user: stripHash(newUser) }, { status: 201 })
  } catch (err) {
    console.error('Create user error:', err)
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
  }
}
