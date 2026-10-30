import type { ConsolePageHeaderProps } from '../lib/console-contract'
export function ConsolePageHeader({
  eyebrow,
  title,
  description,
  actions,
}: ConsolePageHeaderProps) {
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
