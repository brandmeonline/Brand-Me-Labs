// Local stand-in for the shell's `ConsolePageHeader` (lane: opus-commerce-agents).
// Same props, markup and shell classes as console shell contract 1.1.0
// (console-page-header / console-eyebrow / console-page-actions), kept lane-owned so these
// pages build on branches where the shell has not merged yet. Renders the page's single <h1>.
// Import it through ./shell, never directly, so retiring it is a one-line change there.
import type { ReactNode } from 'react'

export interface ConsolePageHeaderProps {
  eyebrow?: string
  title: string
  description?: string
  actions?: ReactNode
}

export function PageHeader({ eyebrow, title, description, actions }: ConsolePageHeaderProps) {
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
