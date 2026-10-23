'use client'
import Link from 'next/link'
import { explainError } from '@/lib/client/gateway'
import { Button } from './button'

export function ResourceState({ loading, error, retry }: { loading: boolean; error: unknown; retry?: () => void }) {
  if (loading) return <p role="status" className="bm-notice">Loading your saved information…</p>
  if (!error) return null
  return <section className="bm-notice" aria-label="Service status">
    <p role="alert">{explainError(error)}</p>
    <div className="bm-actions">{retry && <Button variant="secondary" onClick={retry}>Try again</Button>}
      <Link href="/me/connections">Review account connection</Link></div>
  </section>
}
