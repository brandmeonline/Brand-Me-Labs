/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Page header with the shell's `console-page-header` markup (contract v1 §3
 * makes importing `@/components/console-page-header` optional). Kept local so
 * these pages build whether or not the shell component is present yet.
 */

export function OpsPageHeader({ eyebrow, title, description }: { eyebrow: string; title: string; description: string }) {
  return (
    <header className="console-page-header">
      <div>
        <p className="console-eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
    </header>
  )
}
