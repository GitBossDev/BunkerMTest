import { NextRequest, NextResponse } from 'next/server'
import { findUserByEmail, verifyPassword } from '@/lib/users'
import { signToken, cookieOptions, COOKIE_NAME } from '@/lib/auth'

export async function POST(request: NextRequest) {
  try {
    const { email, password } = await request.json()

    if (!email || !password) {
      return NextResponse.json({ error: 'Email and password are required' }, { status: 400 })
    }
    // Prevent bcrypt DoS: bcrypt only hashes the first 72 bytes; a very long
    // input wastes CPU and can be used as a denial-of-service vector.
    if (typeof password !== 'string' || password.length > 128) {
      return NextResponse.json({ error: 'Invalid credentials' }, { status: 401 })
    }

    const user = findUserByEmail(email)
    if (!user) {
      return NextResponse.json({ error: 'Invalid credentials' }, { status: 401 })
    }

    const valid = await verifyPassword(password, user.passwordHash)
    if (!valid) {
      return NextResponse.json({ error: 'Invalid credentials' }, { status: 401 })
    }

    const { passwordHash: _, ...userWithoutHash } = user
    const token = await signToken(userWithoutHash)

    const response = NextResponse.json({ user: userWithoutHash }, { status: 200 })
    response.cookies.set(COOKIE_NAME, token, cookieOptions())

    return response
  } catch (error) {
    console.error('Login error:', error)
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
  }
}
