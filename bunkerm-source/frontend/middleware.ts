import { NextRequest, NextResponse } from 'next/server'
import { jwtVerify } from 'jose'

// El secreto de autenticación debe provenir exclusivamente de AUTH_SECRET.
// Si no está configurado, el middleware entra en modo degradado seguro:
// todas las sesiones son rechazadas y solo se permiten rutas públicas.
const _raw_secret = process.env.AUTH_SECRET
const secret: Uint8Array | null = _raw_secret ? new TextEncoder().encode(_raw_secret) : null
const COOKIE_NAME = 'bunkerm_token'

const PUBLIC_PATHS = ['/login', '/register']
// Rutas de API de autenticación que no requieren cookie JWT
const AUTH_API_PATHS = ['/api/auth', '/api/logs', '/api/settings']
// Paths that require admin role (read-only 'user' role cannot access)
const ADMIN_ONLY_PATHS = ['/settings/users']
// HTTP methods that mutate state — blocked for 'user' role on proxy API
const MUTATING_METHODS = ['POST', 'PUT', 'DELETE', 'PATCH']

// ─── Granular access control for 'user' role ─────────────────────────────────
// Prefixes where user role can only read (GET allowed, mutations blocked)
const USER_READONLY_PREFIXES = [
  '/api/proxy/config/',           // Broker configuration (mosquitto.conf)
  '/api/proxy/security/',         // Security settings
  '/api/proxy/monitor/alerts/config',  // Alert threshold configuration
]

// Endpoints blocked for 'user' role by specific HTTP method
const USER_BLOCKED_ENDPOINTS: Array<{ prefix: string; methods: string[] }> = [
  // Cannot import password files
  { prefix: '/api/proxy/dynsec/import-password-file', methods: ['POST', 'PUT', 'PATCH'] },
]

/**
 * Determines if an endpoint is blocked for the 'user' role.
 * User can CREATE/UPDATE sub-resources (ACLs, group members) but cannot DELETE root entities.
 */
function isBlockedForUser(pathname: string, method: string): boolean {
  // 1. Read-only prefixes: block all mutations
  if (
    MUTATING_METHODS.includes(method) &&
    USER_READONLY_PREFIXES.some((p) => pathname.startsWith(p))
  ) {
    return true
  }

  // 2. Specific endpoint blocks by method
  for (const rule of USER_BLOCKED_ENDPOINTS) {
    if (rule.methods.includes(method) && pathname.startsWith(rule.prefix)) {
      return true
    }
  }

  // 3. DELETE root DynSec entities (clients/roles/groups) but allow sub-resources
  //    Pattern: /api/proxy/dynsec/{clients|roles|groups}/{name}  (exactly 2 segments)
  //    Allowed: /api/proxy/dynsec/roles/{name}/acls  (3+ segments = sub-resource)
  if (method === 'DELETE' && pathname.startsWith('/api/proxy/dynsec/')) {
    const dynsecPath = pathname.slice('/api/proxy/dynsec/'.length)
    const segments = dynsecPath.split('/').filter(Boolean)
    const ROOT_COLLECTIONS = ['clients', 'roles', 'groups']
    if (segments.length === 2 && ROOT_COLLECTIONS.includes(segments[0])) {
      return true  // Block: DELETE /clients/{name}, /roles/{name}, /groups/{name}
    }
  }

  return false
}

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl

  // Las rutas de auth API no requieren cookie JWT
  if (AUTH_API_PATHS.some((p) => pathname.startsWith(p))) {
    return NextResponse.next()
  }

  const token = request.cookies.get(COOKIE_NAME)?.value
  const isPublicPath = PUBLIC_PATHS.some((p) => pathname.startsWith(p))

  if (!token) {
    if (isPublicPath) return NextResponse.next()
    // Para rutas API sin cookie devolver 401 JSON en lugar de redirigir
    if (pathname.startsWith('/api/')) {
      return NextResponse.json({ error: 'Authentication required' }, { status: 401 })
    }
    return NextResponse.redirect(new URL('/login', request.url))
  }

  try {
    // AUTH_SECRET no configurada — tratar la sesión como inválida de forma segura
    if (!secret) throw new Error('AUTH_SECRET not configured')
    const { payload } = await jwtVerify(token, secret)
    const role = (payload.role as string) ?? 'admin'

    // Valid token — redirect away from public paths
    if (isPublicPath) {
      return NextResponse.redirect(new URL('/dashboard', request.url))
    }

    // 'user' role: block admin-only pages
    if (role === 'user' && ADMIN_ONLY_PATHS.some((p) => pathname.startsWith(p))) {
      return NextResponse.redirect(new URL('/dashboard', request.url))
    }

    // 'user' role: granular permission checks for API mutations
    if (role === 'user' && isBlockedForUser(pathname, request.method)) {
      return NextResponse.json(
        { error: 'Insufficient permissions for this operation' },
        { status: 403 }
      )
    }

    return NextResponse.next()
  } catch {
    // Invalid token - clear cookie and redirect to login
    if (isPublicPath) return NextResponse.next()
    const response = NextResponse.redirect(new URL('/login', request.url))
    response.cookies.delete(COOKIE_NAME)
    return response
  }
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico|.*\\.png$).*)'],
}
