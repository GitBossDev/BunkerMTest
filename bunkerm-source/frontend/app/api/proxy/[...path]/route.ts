import { NextRequest, NextResponse } from 'next/server'
import { readFileSync } from 'fs'

// Backend unificado: todos los servicios HTTP viven en un único proceso uvicorn.
// El proxy de Next.js debe apuntar a ese puerto interno, no a los puertos legacy
// de los antiguos microservicios standalone.
const UNIFIED_API_BASE = process.env.BUNKERM_API_URL || 'http://127.0.0.1:9001/api/v1'

// Service registry: first path segment → Python backend base URL
const SERVICES: Record<string, string> = {
  dynsec:         `${UNIFIED_API_BASE}/dynsec`,
  monitor:        `${UNIFIED_API_BASE}/monitor`,
  clientlogs:     `${UNIFIED_API_BASE}/clientlogs`,
  reports:        `${UNIFIED_API_BASE}/reports`,
  config:         `${UNIFIED_API_BASE}/config`,
  // Smart-anomaly también está montado en el backend unificado.
  ai:             `${UNIFIED_API_BASE}/ai`,
}

const KEY_FILE = '/nextjs/data/.api_key'
// Clave por defecto conocida — nunca debe usarse para reenviar requests reales
const INSECURE_DEFAULT_KEY = 'default_api_key_replace_in_production'

// Devuelve la clave activa o null si no hay ninguna configurada.
// null indica que el proxy debe rechazar el request con 503.
function getApiKey(): string | null {
  const envKey = process.env.API_KEY
  if (envKey && envKey !== INSECURE_DEFAULT_KEY) return envKey
  try {
    const fileKey = readFileSync(KEY_FILE, 'utf8').trim()
    if (fileKey && fileKey !== INSECURE_DEFAULT_KEY) return fileKey
  } catch {
    // Archivo de clave aún no disponible (primer arranque antes de que start.sh lo genere)
  }
  return null
}

async function handler(
  req: NextRequest,
  { params }: { params: { path: string[] } }
) {
  const [service, ...rest] = params.path
  const base = SERVICES[service]

  if (!base) {
    return NextResponse.json({ error: `Unknown service: ${service}` }, { status: 404 })
  }

  // Verificar que la clave API esté configurada antes de reenviar
  const apiKey = getApiKey()
  if (!apiKey) {
    return NextResponse.json(
      { error: 'API key not configured. Set the API_KEY environment variable.' },
      { status: 503 }
    )
  }

  // Build upstream URL, preserving all query params
  const upstreamUrl = new URL(rest.length > 0 ? `${base}/${rest.join('/')}` : base)
  req.nextUrl.searchParams.forEach((v, k) => upstreamUrl.searchParams.set(k, v))

  // Reenviar headers inyectando la clave API del lado del servidor (nunca expuesta al browser)
  const forwardHeaders = new Headers()
  forwardHeaders.set('X-API-Key', apiKey)
  const contentType = req.headers.get('content-type')
  if (contentType) forwardHeaders.set('content-type', contentType)

  // Forward body for non-GET/HEAD methods
  const body = ['GET', 'HEAD'].includes(req.method) ? undefined : await req.arrayBuffer()

  try {
    const upstream = await fetch(upstreamUrl.toString(), {
      method: req.method,
      headers: forwardHeaders,
      body: body ?? undefined,
    })

    const responseBody = await upstream.arrayBuffer()
    const responseHeaders = new Headers()
    upstream.headers.forEach((v, k) => {
      // Skip hop-by-hop headers that must not be forwarded
      if (!['content-encoding', 'transfer-encoding', 'connection'].includes(k.toLowerCase())) {
        responseHeaders.set(k, v)
      }
    })

    return new NextResponse(responseBody, {
      status: upstream.status,
      headers: responseHeaders,
    })
  } catch (err) {
    console.error(`[proxy] upstream error for ${service}:`, err)
    return NextResponse.json({ error: 'Upstream service unavailable' }, { status: 502 })
  }
}

export const GET     = handler
export const POST    = handler
export const PUT     = handler
export const DELETE  = handler
export const OPTIONS = handler
