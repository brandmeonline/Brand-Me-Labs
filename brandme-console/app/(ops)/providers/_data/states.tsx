// Page states for operator reads that did not return data (lane: opus-commerce-agents).
import Link from 'next/link'
import type { Loaded } from './gateway'

const COPY: Record<Exclude<Loaded<unknown>['state'], 'ok'>, { title: string; body: string }> = {
  not_connected: {
    title: 'This console is not connected to the gateway.',
    body: 'Set BRANDME_GATEWAY_URL for the console server. No provider or purchase data is shown until it can be read from the gateway.',
  },
  unauthenticated: {
    title: 'Sign in as an operator to see this page.',
    body: 'The gateway needs an operator bearer token on this request. This page does not use a cookie session.',
  },
  denied: {
    title: 'Your account does not have the operator role for this page.',
    body: 'Ask an administrator for the role. Being able to see this page in the navigation does not grant access.',
  },
  not_found: {
    title: 'That provider is not registered in this environment.',
    body: 'Only providers registered by the server appear here. Nothing is created from a URL.',
  },
  not_built: { title: 'Not built in this release.', body: '' },
  unavailable: { title: 'The data could not be loaded.', body: '' },
}

export function LoadState({ result, backHref }: { result: Exclude<Loaded<unknown>, { state: 'ok' }>; backHref?: string }) {
  const copy = COPY[result.state]
  const detail = 'detail' in result ? result.detail : copy.body
  return (
    <section className="console-notice" aria-labelledby="load-state-heading" role="status">
      <h2 id="load-state-heading">{copy.title}</h2>
      {detail && <p>{detail}</p>}
      {backHref && (
        <p>
          <Link href={backHref}>Back to providers</Link>
        </p>
      )}
    </section>
  )
}
