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
    // Validate email format server-side
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    if (!emailRegex.test(email)) {
      return NextResponse.json({ error: 'Invalid email address' }, { status: 400 })
    }
    // Enforce password length to prevent bcrypt DoS (>72 bytes = wasted CPU)
    if (password.length < 8 || password.length > 128) {
      return NextResponse.json({ error: 'Password must be between 8 and 128 characters' }, { status: 400 })
    }
    // Sanitize name fields: reject if they contain control characters
    if (/[\x00-\x1F\x7F]/.test(firstName) || /[\x00-\x1F\x7F]/.test(lastName)) {
      return NextResponse.json({ error: 'Name contains invalid characters' }, { status: 400 })
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
