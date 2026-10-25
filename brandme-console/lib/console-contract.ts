/**
 * Public console layout contract. Import via @/components/console-contract.
 * Semver: markup/landmark ownership changes require a major version;
 * additive slots/routes a minor version; compatible corrections a patch.
 * Presentation only: every domain must authorize its own reads and commands.
 */
import type { ReactNode } from 'react'

export const CONSOLE_SHELL_CONTRACT = {
  version: '1.1.0',
  mainId: 'console-content',
  pageRoot: 'app/(ops)',
  headerClass: 'console-page-header',
  tableClass: 'console-table-region',
  navigation: [
    { href: '/', label: 'Overview' },
    { href: '/providers', label: 'Providers' },
    { href: '/ingestion', label: 'Catalog ingestion' },
    { href: '/commerce/operations', label: 'Commerce operations' },
    { href: '/chain/operations', label: 'Chain operations' },
    { href: '/rights/issuers', label: 'Rights & issuers' },
    { href: '/manufacturing/jobs', label: 'Manufacturing' },
    { href: '/moderation', label: 'Moderation' },
    { href: '/rewards-disputes', label: 'Reward disputes' },
    { href: '/capabilities', label: 'Capabilities' },
  ],
  legacyRoots: ['/dashboard', '/proof'],
} as const

export interface ConsolePageHeaderProps {
  eyebrow?: string
  title: string
  description?: string
  actions?: ReactNode
}

export function isLegacyConsolePath(pathname: string): boolean {
  return CONSOLE_SHELL_CONTRACT.legacyRoots.some(
    (root) => pathname === root || pathname.startsWith(`${root}/`),
  )
}
