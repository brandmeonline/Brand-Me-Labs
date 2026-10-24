/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Shell contract adapter (consumer-ui console shell contract v1 §3). Every
 * opus-consumer-domains ops page imports ConsolePageHeader from here and
 * nowhere else. The props and markup are the contract's exactly. The shell's
 * own component is not on this lane's base branch, so it is rendered locally.
 *
 * Swap to the published shell in one change: replace this file's body with
 *   export { ConsolePageHeader, type ConsolePageHeaderProps } from '@/components/console-page-header'
 * (or re-export the function alone if the shell does not export its props type).
 */

import type { ReactNode } from 'react'

export interface ConsolePageHeaderProps {
  eyebrow?: string
  title: string
  description?: string
  actions?: ReactNode
}

export function ConsolePageHeader({ eyebrow, title, description, actions }: ConsolePageHeaderProps) {
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
