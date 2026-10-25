// Shell-contract seam for this lane's operator pages (lane: opus-commerce-agents).
// Pages import the page header from this module only. When console shell contract 1.1.0
// (`@/components/console-contract`) is on the branch these pages build on, the swap is
// this one export line:
//   export { ConsolePageHeader as PageHeader, type ConsolePageHeaderProps } from '@/components/console-contract'
// after which ./page-header.tsx can be deleted. The contract is presentation only: every
// page still authorizes its own reads through the gateway.
export { PageHeader, type ConsolePageHeaderProps } from './page-header'

// Contract version the local header mirrors (markup, classes and props).
export const SHELL_CONTRACT_TARGET = '1.1.0'
