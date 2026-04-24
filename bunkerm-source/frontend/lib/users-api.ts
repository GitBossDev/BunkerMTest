/**
 * HTTP client for the BHM Identity API.
 *
 * All calls are server-side (Next.js API routes), never called from the browser.
 * Environment variables:
 *   IDENTITY_API_URL  — base URL of the bhm-identity service (or bhm-api in 5B-1)
 *   IDENTITY_API_KEY  — shared API key (falls back to API_KEY)
 */

const IDENTITY_API_URL = process.env.IDENTITY_API_URL ?? 'http://localhost:9001'
const IDENTITY_API_KEY = process.env.IDENTITY_API_KEY ?? process.env.API_KEY ?? ''

function identityHeaders(): HeadersInit {
  return {
    'Content-Type': 'application/json',
    'X-API-Key': IDENTITY_API_KEY,
  }
}

// ---------------------------------------------------------------------------
// Canonical types returned by the Identity API
// ---------------------------------------------------------------------------

export interface IdentityUserOut {
  id: string
  email: string
  first_name: string
  last_name: string
  role: 'admin' | 'user'
  created_at: string
  updated_at: string
}

/** Normalize an IdentityUserOut to the camelCase shape used by auth.ts / JWT */
export function toUser(u: IdentityUserOut) {
  return {
    id: u.id,
    email: u.email,
    firstName: u.first_name,
    lastName: u.last_name,
    role: u.role as 'admin' | 'user',
    createdAt: u.created_at,
  }
}

export type NormalizedUser = ReturnType<typeof toUser>

// ---------------------------------------------------------------------------
// Custom errors
// ---------------------------------------------------------------------------

export class EmailConflictError extends Error {
  constructor() {
    super('Email already registered')
    this.name = 'EmailConflictError'
  }
}

export class InvalidPasswordError extends Error {
  constructor() {
    super('Current password is incorrect')
    this.name = 'InvalidPasswordError'
  }
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

/**
 * Verify email + password credentials.
 * Returns the normalized user on success, null on 401.
 * Throws on unexpected errors.
 */
export async function verifyCredentials(
  email: string,
  password: string,
): Promise<NormalizedUser | null> {
  const res = await fetch(`${IDENTITY_API_URL}/api/v1/identity/verify`, {
    method: 'POST',
    headers: identityHeaders(),
    body: JSON.stringify({ email, password }),
  })
  if (res.status === 401) return null
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error((body as { detail?: string }).detail ?? `Identity API error: ${res.status}`)
  }
  return toUser(await res.json() as IdentityUserOut)
}

/**
 * List all panel users.
 */
export async function listUsers(): Promise<NormalizedUser[]> {
  const res = await fetch(`${IDENTITY_API_URL}/api/v1/identity/users`, {
    headers: identityHeaders(),
  })
  if (!res.ok) throw new Error(`Identity API error: ${res.status}`)
  const data = await res.json() as { users: IdentityUserOut[] }
  return data.users.map(toUser)
}

/**
 * Create a new panel user.
 * Throws EmailConflictError on 409.
 */
export async function createUserViaApi(data: {
  email: string
  password: string
  firstName: string
  lastName: string
  role?: string
}): Promise<NormalizedUser> {
  const res = await fetch(`${IDENTITY_API_URL}/api/v1/identity/users`, {
    method: 'POST',
    headers: identityHeaders(),
    body: JSON.stringify({
      email: data.email,
      password: data.password,
      first_name: data.firstName,
      last_name: data.lastName,
      role: data.role ?? 'user',
    }),
  })
  if (res.status === 409) throw new EmailConflictError()
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error((body as { detail?: string }).detail ?? `Identity API error: ${res.status}`)
  }
  const d = await res.json() as { user: IdentityUserOut }
  return toUser(d.user)
}

/**
 * Delete a panel user by ID.
 * Throws on last-admin guard (400) or not found (404).
 */
export async function deleteUserViaApi(id: string): Promise<void> {
  const res = await fetch(
    `${IDENTITY_API_URL}/api/v1/identity/users/${encodeURIComponent(id)}`,
    { method: 'DELETE', headers: identityHeaders() },
  )
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error((body as { detail?: string }).detail ?? `Identity API error: ${res.status}`)
  }
}

/**
 * Reset a user's password (admin-initiated, no current password required).
 */
export async function resetUserPasswordViaApi(
  id: string,
  password: string,
): Promise<NormalizedUser> {
  const res = await fetch(
    `${IDENTITY_API_URL}/api/v1/identity/users/${encodeURIComponent(id)}/password`,
    {
      method: 'PATCH',
      headers: identityHeaders(),
      body: JSON.stringify({ password }),
    },
  )
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error((body as { detail?: string }).detail ?? `Identity API error: ${res.status}`)
  }
  const d = await res.json() as { user: IdentityUserOut }
  return toUser(d.user)
}

/**
 * Change own password (requires current password).
 * Throws InvalidPasswordError on 401.
 */
export async function changePasswordViaApi(
  userId: string,
  currentPassword: string,
  newPassword: string,
): Promise<void> {
  const res = await fetch(
    `${IDENTITY_API_URL}/api/v1/identity/users/${encodeURIComponent(userId)}/change-password`,
    {
      method: 'POST',
      headers: identityHeaders(),
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    },
  )
  if (res.status === 401) throw new InvalidPasswordError()
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error((body as { detail?: string }).detail ?? `Identity API error: ${res.status}`)
  }
}
