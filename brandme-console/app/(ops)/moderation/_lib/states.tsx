/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Shared non-data states for this lane's operator pages: unconnected,
 * signed out, denied and failed. Each says what is true and what to do next;
 * none implies access was verified.
 */

import type { OpsResult } from './ops-gateway'

export function OpsState({ result, area }: { result: Exclude<OpsResult<unknown>, { kind: 'ok' }>; area: string }) {
  if (result.kind === 'unconnected') {
    return (
      <section className="console-notice" aria-labelledby="ops-state">
        <h2 id="ops-state">{area} is not connected.</h2>
        <p>{result.detail} No records were loaded and no action is available.</p>
      </section>
    )
  }
  if (result.kind === 'signed_out') {
    return (
      <section className="console-notice" aria-labelledby="ops-state">
        <h2 id="ops-state">Sign in with an operator session.</h2>
        <p>The gateway did not recognize a session for this request. {area} records stay unavailable until you sign in.</p>
      </section>
    )
  }
  if (result.kind === 'denied') {
    return (
      <section className="console-notice" aria-labelledby="ops-state">
        <h2 id="ops-state">You do not have access to {area.toLowerCase()}.</h2>
        <p>
          {result.detail} Operator actions need the moderation role and a recently strengthened sign-in. Operators never
          handle their own records.
        </p>
      </section>
    )
  }
  return (
    <section className="console-notice" role="alert" aria-labelledby="ops-state">
      <h2 id="ops-state">{area} could not be loaded.</h2>
      <p>
        {result.detail} ({result.code}, status {result.status}
        {result.requestId ? `, request ${result.requestId}` : ''})
      </p>
    </section>
  )
}

export function ActionBanner({ done, failed }: { done?: string; failed?: string }) {
  if (failed) {
    return (
      <p className="console-notice" role="alert">
        The action was not applied: {failed}
      </p>
    )
  }
  if (done) {
    return (
      <p className="console-notice" role="status">
        {done}
      </p>
    )
  }
  return null
}
