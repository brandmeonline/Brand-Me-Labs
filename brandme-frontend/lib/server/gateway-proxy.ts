/** Thin same-origin transport. Domain authorization and persistence stay in the gateway. */
const READ = new Set(['GET', 'HEAD'])
const ROOTS = new Set(['session', 'me', 'recommendations', 'wardrobe', 'closet', 'outfits',
  'relationships', 'blocks', 'decisions', 'shares', 'notifications', 'reports', 'rewards',
  'benefits', 'catalog', 'providers', 'assistant', 'delegations', 'commerce', 'assets',
  'ownership', 'chain', 'transfers', 'reprint-jobs'])
const MAX_REQUEST = 256 * 1024
const MAX_RESPONSE = 2 * 1024 * 1024

export function problem(status: number, code: string, title: string): Response {
  return Response.json({ type: 'about:blank', status, code, title }, {
    status, headers: { 'Cache-Control': 'private, no-store', 'Content-Type': 'application/problem+json' },
  })
}

export function gatewayBase(env: Record<string, string | undefined>): URL | null {
  if (!env.BRANDME_GATEWAY_URL) return null
  const url = new URL(env.BRANDME_GATEWAY_URL)
  const loopback = ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)
  if (url.username || url.password || url.search || url.hash ||
      !['/', '/api/v1', '/api/v1/'].includes(url.pathname) ||
      !(url.protocol === 'https:' || (loopback && url.protocol === 'http:' &&
        ['demo', 'development'].includes(env.BRANDME_MODE ?? '')))) throw new Error('Invalid gateway configuration')
  url.pathname = '/api/v1/'
  return url
}

async function boundedBody(stream: ReadableStream<Uint8Array> | null, limit: number): Promise<Uint8Array> {
  if (!stream) return new Uint8Array()
  const reader = stream.getReader()
  const chunks: Uint8Array[] = []
  let size = 0
  try {
    while (true) {
      const next = await reader.read()
      if (next.done) break
      size += next.value.byteLength
      if (size > limit) { await reader.cancel(); throw new RangeError('Payload too large') }
      chunks.push(next.value)
    }
  } finally { reader.releaseLock() }
  const body = new Uint8Array(size)
  let offset = 0
  for (const chunk of chunks) { body.set(chunk, offset); offset += chunk.length }
  return body
}

export async function proxyGateway(request: Request, parts: string[],
  env: Record<string, string | undefined>, fetchImpl: typeof fetch = fetch): Promise<Response> {
  const catalogId = parts.length === 3 && parts[0] === 'catalog' && parts[1] === 'products'
  if (!parts.length || !ROOTS.has(parts[0]) || parts.some((p,i) => !(catalogId && i === 2
    ? /^[a-zA-Z0-9_-]{1,80}:[a-zA-Z0-9_-]{1,128}$/.test(p) : /^[a-zA-Z0-9_-]{1,128}$/.test(p))))
    return problem(404, 'not_found', 'This service is not available.')
  // No operator APIs, account grants, provider activation or arbitrary upstream URLs.
  if (parts[0] === 'commerce' && parts[1] === 'ops')
    return problem(404, 'not_found', 'This service is not available.')
  if (parts[0] === 'providers' && !READ.has(request.method))
    return problem(405, 'method_not_allowed', 'Provider setup belongs in Operations.')
  const isDevSession = parts.join('/') === 'session/dev'
  if (isDevSession && (env.NODE_ENV === 'production' || !['demo', 'development'].includes(env.BRANDME_MODE ?? '')))
    return problem(404, 'not_found', 'This service is not available.')
  const unsafe = !READ.has(request.method)
  if (unsafe) {
    const origin = request.headers.get('origin')
    const expected = env.BRANDME_PUBLIC_ORIGIN || new URL(request.url).origin
    if (origin !== expected || request.headers.get('sec-fetch-site') === 'cross-site')
      return problem(403, 'csrf_failed', 'Reload this page before trying again.')
    if (request.headers.get('content-type')?.split(';')[0] !== 'application/json')
      return problem(415, 'unsupported_media_type', 'Use a JSON request.')
    if (!isDevSession && !request.headers.get('x-csrf-token'))
      return problem(403, 'csrf_failed', 'Reload this page before trying again.')
  }
  let base: URL | null
  try { base = gatewayBase(env) } catch { return problem(503, 'gateway_unconfigured', 'Account services are not connected.') }
  if (!base) return problem(503, 'gateway_unconfigured', 'Account services are not connected.')
  const url = new URL(parts.map(encodeURIComponent).join('/'), base)
  url.search = new URL(request.url).search
  if (url.search.length > 2048) return problem(400, 'invalid_query', 'The request is too long.')
  const headers = new Headers({ Accept: 'application/json' })
  const cookie = request.headers.get('cookie')?.split(';').map(c => c.trim()).find(c => c.startsWith('bm_session='))
  if (cookie) headers.set('cookie', cookie)
  for (const key of ['origin', 'x-csrf-token', 'if-match', 'idempotency-key']) {
    const value = request.headers.get(key)
    if (value && value.length <= 512) headers.set(key, value)
  }
  let body: Uint8Array | undefined
  if (unsafe) {
    headers.set('Content-Type', 'application/json')
    try { body = await boundedBody(request.body, MAX_REQUEST) }
    catch { return problem(413, 'payload_too_large', 'This request is too large.') }
  }
  try {
    const upstream = await fetchImpl(url, {
      method: request.method, headers, body: body as BodyInit | undefined,
      redirect: 'manual', cache: 'no-store', signal: AbortSignal.timeout(15000),
    })
    if (upstream.status >= 300 && upstream.status < 400)
      return problem(502, 'upstream_redirect', 'The account service could not complete this request.')
    const responseHeaders = new Headers({ 'Cache-Control': 'private, no-store', Vary: 'Cookie', 'X-Content-Type-Options': 'nosniff' })
    for (const key of ['etag', 'date', 'retry-after', 'x-request-id', 'x-brandme-environment', 'x-brandme-simulation']) {
      const value = upstream.headers.get(key)
      if (value) responseHeaders.set(key, value)
    }
    const sessionCookie = upstream.headers.get('set-cookie')
    if (parts[0] === 'session' && sessionCookie?.startsWith('bm_session=') &&
        /;\s*HttpOnly(?:;|$)/i.test(sessionCookie) && !/;\s*Domain=/i.test(sessionCookie))
      responseHeaders.set('Set-Cookie', sessionCookie)
    if (upstream.status === 204 || request.method === 'HEAD') return new Response(null, { status: upstream.status, headers: responseHeaders })
    const type = upstream.headers.get('content-type') ?? ''
    if (!type.startsWith('application/json') && !type.startsWith('application/problem+json'))
      return problem(502, 'invalid_response', 'The account service returned an unreadable response.')
    const bytes = await boundedBody(upstream.body, MAX_RESPONSE)
    responseHeaders.set('Content-Type', type)
    return new Response(bytes as BodyInit, { status: upstream.status, headers: responseHeaders })
  } catch {
    // A timed-out mutation may have committed. Never automatically resubmit it.
    return problem(503, unsafe ? 'outcome_unknown' : 'gateway_unavailable', unsafe
      ? 'The result is not confirmed. Refresh the record before trying again.'
      : 'Account services are temporarily unavailable.')
  }
}
