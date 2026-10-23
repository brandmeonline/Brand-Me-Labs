'use client'

export default function ModerationError({ reset }: { error: Error; reset: () => void }) {
  return (
    <section className="console-notice" role="alert" aria-labelledby="moderation-error">
      <h2 id="moderation-error">Moderation could not be shown.</h2>
      <p>Nothing was changed. Try again; if this keeps happening, check the gateway connection.</p>
      <button type="button" onClick={reset}>
        Try again
      </button>
    </section>
  )
}
