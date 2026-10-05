'use client'
import Link from 'next/link'
export default function ErrorPage({
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  return (
    <section className="bm-empty-state" role="alert">
      <p className="bm-eyebrow">Something interrupted this page</p>
      <h1 className="bm-display-title">Let’s try that again.</h1>
      <p>Your display settings are still here. We couldn’t load this page.</p>
      <div className="bm-action-row">
        <button className="bm-button" onClick={reset}>
          Try again
        </button>
        <Link className="bm-button bm-button-outline" href="/today">
          Back to Today
        </Link>
      </div>
    </section>
  )
}
