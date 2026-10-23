/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Server-side client for the gateway's operator routes (lane:
 * opus-consumer-domains; shared by the (ops)/moderation and
 * (ops)/rewards-disputes subtrees). Runs only on the server.
 *
 * The console shell is not an authorization boundary. Every read and action
 * here forwards the operator's own credentials (session cookie or bearer)
 * to the gateway, which checks `moderation:admin`, aal2 outside development
 * and no delegation; the domain checks again and refuses self-review. No role
 * is assumed or injected here. How the console's session reaches the gateway
 * (shared cookie domain vs. a server-side token exchange) is an integration
 * decision (proposal PD-18).
 */

import { cookies, headers } from 'next/headers'

export type OpsResult<T> =
  | { kind: 'ok'; data: T }
  | { kind: 'unconnected'; detail: string }
  | { kind: 'signed_out' }
  | { kind: 'denied'; detail: string }
  | { kind: 'error'; status: number; code: string; detail: string; requestId: string | null }

export interface Page<T> {
  items: T[]
  next_cursor: string | null
}

function gatewayBase(): string | null {
  const base = process.env.BRANDME_GATEWAY_INTERNAL_URL
  return base ? base.replace(/\/+$/, '') : null
}

export async function opsFetch<T>(path: string, init?: { method?: 'GET' | 'POST'; body?: unknown }): Promise<OpsResult<T>> {
  const base = gatewayBase()
  if (!base) return { kind: 'unconnected', detail: 'BRANDME_GATEWAY_INTERNAL_URL is not configured for this console.' }
  const forward: Record<string, string> = { accept: 'application/json' }
  const cookie = (await cookies()).toString()
  if (cookie) forward.cookie = cookie
  const authorization = (await headers()).get('authorization')
  if (authorization) forward.authorization = authorization
  if (init?.body !== undefined) forward['content-type'] = 'application/json'
  let res: Response
  try {
    res = await fetch(`${base}/api/v1/ops${path}`, {
      method: init?.method ?? 'GET',
      headers: forward,
      body: init?.body === undefined ? undefined : JSON.stringify(init.body),
      cache: 'no-store',
    })
  } catch {
    return { kind: 'unconnected', detail: 'The gateway could not be reached.' }
  }
  if (res.status === 401) return { kind: 'signed_out' }
  const body = (await res.json().catch(() => null)) as Record<string, unknown> | null
  if (res.status === 403) return { kind: 'denied', detail: String(body?.detail ?? 'This session is not permitted to do that.') }
  if (!res.ok) {
    return {
      kind: 'error',
      status: res.status,
      code: String(body?.code ?? 'error'),
      detail: String(body?.detail ?? 'The request failed.'),
      requestId: res.headers.get('x-request-id'),
    }
  }
  return { kind: 'ok', data: body as T }
}

export function formatTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '—' : d.toISOString().replace('T', ' ').slice(0, 16) + ' UTC'
}
