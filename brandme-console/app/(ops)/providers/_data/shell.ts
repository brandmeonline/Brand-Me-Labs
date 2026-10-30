// Shell-contract seam for this lane's operator pages (lane: opus-commerce-agents).
// Pages import the page header from this module only. It is the published console shell
// contract's own component (`@/components/console-contract`), so the markup, classes and
// props are the shell's. The contract is presentation only: every page still authorizes
// its own reads through the gateway.
export {
  ConsolePageHeader as PageHeader,
  CONSOLE_SHELL_CONTRACT,
  type ConsolePageHeaderProps,
} from '@/components/console-contract'
