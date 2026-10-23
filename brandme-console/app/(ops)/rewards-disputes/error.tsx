'use client'

export default function RewardDisputesError({ reset }: { error: Error; reset: () => void }) {
  return (
    <section className="console-notice" role="alert" aria-labelledby="rewards-disputes-error">
      <h2 id="rewards-disputes-error">Reward disputes could not be shown.</h2>
      <p>Nothing was changed. Try again; if this keeps happening, check the gateway connection.</p>
      <button type="button" onClick={reset}>
        Try again
      </button>
    </section>
  )
}
