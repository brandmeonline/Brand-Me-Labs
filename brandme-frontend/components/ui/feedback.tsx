import type { ReactNode } from 'react'

export function StatusChip({
  children,
  tone = 'neutral',
}: {
  children: string
  tone?: 'neutral' | 'success' | 'warning' | 'error'
}) {
  return (
    <span className="bm-status-chip" data-tone={tone}>
      {children}
    </span>
  )
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string
  description: string
  action?: ReactNode
}) {
  return (
    <section className="bm-ui-state">
      <h2 className="bm-section-title">{title}</h2>
      <p>{description}</p>
      {action}
    </section>
  )
}

/** Render inside the flow; no automatic focus change and no dismissal timeout. */
export function ErrorState({
  title,
  description,
  action,
}: {
  title: string
  description: string
  action?: ReactNode
}) {
  return (
    <section className="bm-ui-state bm-ui-state-error">
      <div role="alert">
        <h2 className="bm-section-title">{title}</h2>
        <p>{description}</p>
      </div>
      {action}
    </section>
  )
}

export function Skeleton({ label = 'Loading' }: { label?: string }) {
  return (
    <div role="status" className="bm-skeleton">
      <span className="sr-only">{label}</span>
      <span aria-hidden="true" />
    </div>
  )
}

/** Mount once, then change message. Important actions are retained until explicitly dismissed. */
export function Toast({
  message,
  action,
  onDismiss,
}: {
  message: string | null
  action?: ReactNode
  onDismiss?: () => void
}) {
  return (
    <div className="bm-toast" data-visible={Boolean(message)}>
      <p role="status" aria-atomic="true">
        {message}
      </p>
      {message && (
        <div className="bm-ui-actions">
          {action}
          {onDismiss && (
            <button type="button" className="bm-text-link" onClick={onDismiss}>
              Dismiss notice
            </button>
          )}
        </div>
      )}
    </div>
  )
}
