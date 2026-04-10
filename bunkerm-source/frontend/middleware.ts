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

    // 'user' role: block mutating API proxy calls (read-only mode)
    if (
      role === 'user' &&
      pathname.startsWith('/api/proxy') &&
      MUTATING_METHODS.includes(request.method)
    ) {
      return NextResponse.json(
        { error: 'Insufficient permissions — this account is read-only' },
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
