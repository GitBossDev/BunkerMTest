import { SignJWT, jwtVerify } from 'jose'
import type { User } from '@/types'

// Obtener el secreto de firma desde el entorno.
// Lanza un error explícito si AUTH_SECRET no está definida para evitar emitir
// tokens con un secreto vacío o previsible.
function getSecret(): Uint8Array {
  const raw = process.env.AUTH_SECRET
  if (!raw) {
    throw new Error(
      'AUTH_SECRET no está configurada. ' +
      'Esta variable de entorno es obligatoria para firmar y verificar sesiones.'
    )
  }
  return new TextEncoder().encode(raw)
}

const TOKEN_EXPIRY = '24h'
export const COOKIE_NAME = 'bunkerm_token'

export async function signToken(user: User): Promise<string> {
  return new SignJWT({
    id: user.id,
    email: user.email,
    firstName: user.firstName,
    lastName: user.lastName,
    role: user.role,
  })
    .setProtectedHeader({ alg: 'HS256' })
    .setIssuedAt()
    .setExpirationTime(TOKEN_EXPIRY)
    .sign(getSecret())
}

export async function verifyToken(token: string): Promise<User | null> {
  try {
    const { payload } = await jwtVerify(token, getSecret())
    return {
      id: payload.id as string,
      email: payload.email as string,
      firstName: payload.firstName as string,
      lastName: payload.lastName as string,
      role: (payload.role as 'admin' | 'user') ?? 'admin',
      createdAt: payload.createdAt as string || new Date().toISOString(),
    }
  } catch {
    return null
  }
}

export function cookieOptions(maxAge?: number) {
  return {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'strict' as const,
    path: '/',
    maxAge: maxAge ?? 60 * 60 * 24, // 24h
  }
}
