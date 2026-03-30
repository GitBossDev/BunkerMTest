import { NextRequest, NextResponse } from 'next/server'
import { jwtVerify } from 'jose'

const AUTH_SECRET = process.env.AUTH_SECRET || 'fallback-secret-change-in-production'
const secret = new TextEncoder().encode(AUTH_SECRET)
const COOKIE_NAME = 'bunkerm_token'

const PUBLIC_PATHS = ['/login', '/register']
const API_PATHS = ['/api/auth', '/api/logs', '/api/proxy', '/api/settings']

// Paths that require admin role (read-only 'user' role cannot access)
const ADMIN_ONLY_PATHS = ['/settings/users']
// HTTP methods that mutate state — blocked for 'user' role on proxy API
const MUTATING_METHODS = ['POST', 'PUT', 'DELETE', 'PATCH']

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl

  // Skip auth API routes
  if (API_PATHS.some((p) => pathname.startsWith(p))) {
    return NextResponse.next()
  }

  const token = request.cookies.get(COOKIE_NAME)?.value
  const isPublicPath = PUBLIC_PATHS.some((p) => pathname.startsWith(p))

  if (!token) {
    if (isPublicPath) return NextResponse.next()
    return NextResponse.redirect(new URL('/login', request.url))
  }

  try {
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
