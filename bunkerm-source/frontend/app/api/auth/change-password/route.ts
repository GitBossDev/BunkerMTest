import { NextRequest, NextResponse } from 'next/server'
import { verifyToken, COOKIE_NAME } from '@/lib/auth'
import { changePasswordViaApi, InvalidPasswordError } from '@/lib/users-api'

export async function POST(request: NextRequest) {
  const token = request.cookies.get(COOKIE_NAME)?.value
  if (!token) return NextResponse.json({ error: 'Not authenticated' }, { status: 401 })

  const currentUser = await verifyToken(token)
  if (!currentUser) return NextResponse.json({ error: 'Invalid token' }, { status: 401 })

  const { currentPassword, newPassword } = await request.json()
  if (!currentPassword || !newPassword) {
    return NextResponse.json({ error: 'All fields required' }, { status: 400 })
  }
  // Prevent bcrypt DoS
  if (typeof currentPassword !== 'string' || currentPassword.length > 128) {
    return NextResponse.json({ error: 'Current password is incorrect' }, { status: 401 })
  }
  if (newPassword.length < 8 || newPassword.length > 128) {
    return NextResponse.json({ error: 'Password must be between 8 and 128 characters' }, { status: 400 })
  }

  try {
    await changePasswordViaApi(currentUser.id, currentPassword, newPassword)
    return NextResponse.json({ message: 'Password changed successfully' }, { status: 200 })
  } catch (err) {
    if (err instanceof InvalidPasswordError) {
      return NextResponse.json({ error: 'Current password is incorrect' }, { status: 401 })
    }
    console.error('Change password error:', err)
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
  }
}
