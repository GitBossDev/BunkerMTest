import { NextResponse } from 'next/server'

// Public self-registration is disabled.
// New users are created by admins via /settings/users.
export async function POST() {
  return NextResponse.json(
    { error: 'Self-registration is disabled. Contact an administrator.' },
    { status: 403 }
  )
}
