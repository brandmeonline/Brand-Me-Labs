'use client'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { Menu, X, SunMoon } from 'lucide-react'
import { useExperiencePreferences } from '../../brandme-frontend/lib/client/experience-preferences'

import { consoleNavigation } from '@/lib/navigation'

export function ConsoleShell({
  children,
  environment,
}: {
  children: ReactNode
  environment: string
}) {
  const pathname = usePathname() || '/'
  const [open, setOpen] = useState(false)
  const main = useRef<HTMLElement>(null)
  const menuNavigation = useRef(false)
  const lastPath = useRef(pathname)
  const { preferences, update } = useExperiencePreferences()
  useEffect(() => {
    if (lastPath.current !== pathname) {
      setOpen(false)
      main.current?.focus({ preventScroll: true })
      lastPath.current = pathname
    }
  }, [pathname])
  // Preserve legacy public proof and dashboard layout contracts, without nesting main/nav.
  if (
    pathname === '/dashboard' ||
    pathname.startsWith('/dashboard/') ||
    pathname === '/proof' ||
    pathname.startsWith('/proof/')
  )
    return <>{children}</>
  const links = consoleNavigation.map(({ href, label }) => (
    <Link
      key={href}
      href={href}
      aria-current={
        (
          href === '/'
            ? pathname === '/'
            : pathname === href || pathname.startsWith(`${href}/`)
        )
          ? 'page'
          : undefined
      }
      onClick={() => {
        if (open) menuNavigation.current = true
        setOpen(false)
      }}
    >
      {label}
    </Link>
  ))
  const nextTheme =
    preferences.theme === 'system'
      ? 'light'
      : preferences.theme === 'light'
        ? 'dark'
        : 'system'
  return (
    <div className="console-shell">
      <a className="console-skip" href="#console-content">
        Skip to content
      </a>
      <aside className="console-rail">
        <Link className="console-wordmark" href="/">
          Brand.Me<span>OPERATIONS</span>
        </Link>
        <nav aria-label="Operations">{links}</nav>
        <p>
          Scoped access.
          <br />
          Accountable actions.
        </p>
      </aside>
      <div className="console-workspace">
        <header className="console-topbar">
          <div className="console-mobile-menu">
            <Dialog.Root open={open} onOpenChange={setOpen}>
              <Dialog.Trigger
                className="console-icon-button"
                aria-label="Open operations menu"
              >
                <Menu size={20} aria-hidden="true" />
              </Dialog.Trigger>
              <Dialog.Portal>
                <Dialog.Overlay className="console-overlay" />
                <Dialog.Content
                  className="console-drawer"
                  onCloseAutoFocus={(event) => {
                    if (menuNavigation.current) {
                      event.preventDefault()
                      main.current?.focus({ preventScroll: true })
                      menuNavigation.current = false
                    }
                  }}
                >
                  <div className="console-drawer-heading">
                    <Dialog.Title>Operations</Dialog.Title>
                    <Dialog.Close
                      className="console-icon-button"
                      aria-label="Close operations menu"
                    >
                      <X size={20} aria-hidden="true" />
                    </Dialog.Close>
                  </div>
                  <Dialog.Description>
                    Navigate operational areas. Access is checked separately for
                    each action.
                  </Dialog.Description>
                  <nav aria-label="Mobile operations">{links}</nav>
                </Dialog.Content>
              </Dialog.Portal>
            </Dialog.Root>
          </div>
          <span className="console-topbar-label">Brand.Me / Operations</span>
          <span className="console-environment">{environment}</span>
          <button
            className="console-icon-button"
            aria-label={`Appearance: ${preferences.theme}. Switch to ${nextTheme}`}
            onClick={() => update({ theme: nextTheme })}
          >
            <SunMoon size={20} aria-hidden="true" />
          </button>
        </header>
        <main id="console-content" ref={main} tabIndex={-1}>
          {children}
        </main>
      </div>
    </div>
  )
}
