'use client'
import { createBrandmeClient } from '@brandme/contracts'

export class GatewayError extends Error {
  status: number
  code: string
  constructor(status: number, code: string, message: string) {
    super(message); this.status = status; this.code = code
  }
}
export type Resource<T> = { data: T | null; error: GatewayError | null; loading: boolean }
export const typedGateway = createBrandmeClient({ baseUrl: '/api/v1' })

export async function read<T>(path: string, signal?: AbortSignal): Promise<T> {
  // Foundation owns the generated contract. Lane DTOs cover endpoints it has not generated yet.
  if (path === '/me') {
    const { data, error, response } = await typedGateway.GET('/me', { signal, cache: 'no-store' })
    if (!response.ok) throw new GatewayError(response.status, error?.code ?? 'request_failed', error?.title ?? 'The request could not be completed.')
    return data as T
  }
  return decode<T>(await fetch(`/api/v1${path}`, { credentials: 'same-origin', cache: 'no-store', signal }))
}
async function decode<T>(response: Response): Promise<T> {
  if (response.status === 204) return undefined as T
  const data = await response.json().catch(() => null)
  if (!response.ok) throw new GatewayError(response.status, data?.code ?? 'request_failed',
    data?.title ?? 'The request could not be completed.')
  if (data === null) throw new GatewayError(502, 'invalid_response', 'The service returned an unreadable response.')
  return data as T
}

let pending: Promise<unknown> = Promise.resolve()
let accountVersion = 0
export function invalidateAccountRequests() { accountVersion++ }
/** Serialize rotating CSRF sessions across tabs; keys remain in memory only. Never retry a write automatically. */
export function command<T>(path: string, body: unknown = {}, options: {
  method?: 'POST' | 'PATCH' | 'PUT' | 'DELETE'; version?: string; key?: string
} = {}): Promise<T> {
  const version = accountVersion
  const execute = async () => {
    if (version !== accountVersion) throw new GatewayError(409, 'account_changed', 'Your account changed. Review the action again.')
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    try {
      const session = await read<{ csrf_token: string }>('/session')
      headers['X-CSRF-Token'] = session.csrf_token
    } catch (error) {
      if (!(path === '/session/dev' && error instanceof GatewayError && error.status === 401)) throw error
    }
    if (version !== accountVersion) throw new GatewayError(409, 'account_changed', 'Your account changed. Review the action again.')
    if (options.version !== undefined) headers['If-Match'] = `"${options.version}"`
    if (options.key) headers['Idempotency-Key'] = options.key
    return decode<T>(await fetch(`/api/v1${path}`, { method: options.method ?? 'POST',
      headers, body: JSON.stringify(body), credentials: 'same-origin', cache: 'no-store' }))
  }
  const locked = async (): Promise<T> => typeof navigator !== 'undefined' && navigator.locks
    ? await navigator.locks.request('brandme:session-write', execute) : await execute()
  const result = pending.then(locked, locked)
  pending = result.catch(() => undefined)
  return result
}

export function explainError(error: unknown): string {
  if (error instanceof GatewayError) {
    if (error.code === 'account_changed') return error.message
    if (error.status === 401) return 'Sign in to see your saved data.'
    if (error.status === 403) return 'This account does not have access to this action.'
    if (error.status === 404) return 'This record or service is not available. It may have been removed or revoked.'
    if (error.status === 409 || error.status === 412) return 'A newer version was saved elsewhere. Reload and review it before applying your changes.'
    if (error.code === 'outcome_unknown') return error.message
    if (error.status >= 500) return 'This service is not connected or temporarily unavailable. No result is confirmed.'
    return error.message
  }
  return 'The connection was interrupted. Check your connection and refresh the record.'
}
