import type { ReactNode } from 'react'
export function PageHeading({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string
  title: string
  description?: string
  actions?: ReactNode
}) {
  return (
    <header className="bm-page-heading">
      <div>
        {eyebrow && <p className="bm-eyebrow">{eyebrow}</p>}
        <h1 className="bm-display-title">{title}</h1>
        {description && <p className="bm-page-description">{description}</p>}
      </div>
      {actions}
    </header>
  )
}
