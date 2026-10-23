// Page header for this lane's operator pages (lane: opus-commerce-agents).
// Same markup and shell classes as the optional `ConsolePageHeader` in shell contract v1
// (console-page-header / console-eyebrow / console-page-actions), kept lane-owned so these
// pages build on branches where the shell has not merged yet. Renders the page's single <h1>.
import type { ReactNode } from 'react'

export function PageHeader({
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
    <header className="console-page-header">
      <div>
        {eyebrow && <p className="console-eyebrow">{eyebrow}</p>}
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {actions && <div className="console-page-actions">{actions}</div>}
    </header>
  )
}
