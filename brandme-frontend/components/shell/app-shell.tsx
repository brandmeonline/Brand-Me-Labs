'use client'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import {
  ArrowUpRight,
  Bell,
  Menu,
  Plus,
  SlidersHorizontal,
  WifiOff,
} from 'lucide-react'
import {
  primaryNavigation,
  secondaryNavigation,
  isActiveRoute,
} from './navigation'
import { Wordmark } from './wordmark'
import { Sheet } from './sheet'
import { ExperienceSettings } from './experience-settings'

function ContextContent({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <div className="bm-context-content">
      <p className="bm-eyebrow">Always in your hands</p>
      <h2 className="bm-editorial-title">
        A little more
        <br />
        <em>you.</em>
      </h2>
      <p>Your style can change with your day. Your preferences should, too.</p>
      <Link className="bm-text-link" href="/me" onClick={onNavigate}>
        Explore your space <ArrowUpRight size={17} aria-hidden="true" />
      </Link>
      <div className="bm-context-divider" />
      <h3 className="bm-small-heading">Make yourself comfortable</h3>
      <ExperienceSettings />
      <div className="bm-context-note">
        <span aria-hidden="true">✳</span>
        <p>You can explore without connecting a wallet, camera, or contacts.</p>
      </div>
    </div>
  )
}
export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname() || '/'
  const [menuOpen, setMenuOpen] = useState(false)
  const [contextOpen, setContextOpen] = useState(false)
  const sheetNavigation = useRef(false)
  const [offline, setOffline] = useState(false)
  const previousPath = useRef(pathname)
  const mainRef = useRef<HTMLElement>(null)
  const publicPage =
    pathname === '/' || pathname === '/start' || pathname.startsWith('/share/')
  useEffect(() => {
    const update = () => setOffline(!navigator.onLine)
    update()
    addEventListener('online', update)
    addEventListener('offline', update)
    return () => {
      removeEventListener('online', update)
      removeEventListener('offline', update)
    }
  }, [])
  useEffect(() => {
    if (previousPath.current !== pathname) {
      setMenuOpen(false)
      setContextOpen(false)
      mainRef.current?.focus({ preventScroll: true })
      previousPath.current = pathname
    }
  }, [pathname])
  function navigateFromSheet() {
    sheetNavigation.current = true
    setMenuOpen(false)
    setContextOpen(false)
  }
  function restoreSheetFocus(event: Event) {
    if (sheetNavigation.current) {
      event.preventDefault()
      mainRef.current?.focus({ preventScroll: true })
      sheetNavigation.current = false
    }
  }
  const current = [...secondaryNavigation, ...primaryNavigation].find((item) =>
    isActiveRoute(pathname, item.href),
  )
  const links = (kind: 'primary' | 'secondary', close = false) =>
    (kind === 'primary' ? primaryNavigation : secondaryNavigation).map(
      ({ href, label, icon: Icon }) => (
        <Link
          key={href}
          href={href}
          className="bm-nav-link"
          aria-current={isActiveRoute(pathname, href) ? 'page' : undefined}
          title={label}
          onClick={() => close && navigateFromSheet()}
        >
          <Icon size={21} strokeWidth={1.65} aria-hidden="true" />
          <span>{label}</span>
        </Link>
      ),
    )
  return (
    <div className={`bm-shell${publicPage ? ' bm-shell-public' : ''}`}>
      <a className="bm-skip-link" href="#main-content">
        Skip to content
      </a>
      {!publicPage && (
        <aside className="bm-rail" aria-label="Main navigation">
          <Wordmark />
          <span className="bm-rail-motto">Be More U.</span>
          <nav aria-label="Primary" className="bm-primary-nav">
            {links('primary')}
          </nav>
          <div className="bm-nav-rule" />
          <nav aria-label="Explore" className="bm-secondary-nav">
            {links('secondary')}
          </nav>
          <div className="bm-rail-foot">
            <span className="bm-avatar" aria-hidden="true">
              U
            </span>
            <div>
              Explore first
              <span className="bm-support">No account connected</span>
            </div>
          </div>
        </aside>
      )}
      <div className="bm-workspace">
        <header className="bm-topbar">
          <div className="bm-mobile-wordmark">
            <Wordmark />
          </div>
          {!publicPage && (
            <p className="bm-breadcrumb">
              Your world <span aria-hidden="true">/</span>{' '}
              <strong>{current?.label || 'Explore'}</strong>
            </p>
          )}
          {publicPage && (
            <p className="bm-topbar-tagline">A wardrobe that feels like you.</p>
          )}
          <div className="bm-header-actions">
            {!publicPage && (
              <Link
                href="/add"
                className="bm-icon-button bm-add-button"
                aria-label="Add an item"
              >
                <Plus size={20} aria-hidden="true" />
                <span>Add item</span>
              </Link>
            )}
            {!publicPage && (
              <Link href="/inbox" className="bm-icon-button" aria-label="Inbox">
                <Bell size={20} aria-hidden="true" />
              </Link>
            )}
            <Sheet
              title="Your space"
              description="Explore Brand.Me and adjust your display preferences."
              open={menuOpen}
              onOpenChange={setMenuOpen}
              onCloseAutoFocus={restoreSheetFocus}
              trigger={
                <button
                  className="bm-icon-button bm-menu-trigger"
                  aria-label="Open menu"
                >
                  <Menu size={21} aria-hidden="true" />
                </button>
              }
            >
              <nav aria-label="Menu navigation" className="bm-sheet-nav">
                {links('primary', true)}
                {links('secondary', true)}
              </nav>
              <ExperienceSettings />
            </Sheet>
            <Sheet
              title="Your experience"
              description="Display preferences stay on this device. Your device’s reduced-motion preference always applies."
              open={contextOpen}
              onOpenChange={setContextOpen}
              onCloseAutoFocus={restoreSheetFocus}
              trigger={
                <button
                  className="bm-icon-button bm-context-trigger"
                  aria-label="Customize your experience"
                >
                  <SlidersHorizontal size={19} aria-hidden="true" />
                </button>
              }
            >
              <ContextContent onNavigate={navigateFromSheet} />
            </Sheet>
            {publicPage && (
              <Link className="bm-button bm-button-small" href="/today">
                Explore first <ArrowUpRight size={16} aria-hidden="true" />
              </Link>
            )}
          </div>
        </header>
        {offline && (
          <div className="bm-network-notice" role="status">
            <WifiOff size={18} aria-hidden="true" /> You’re offline. Display
            settings still work; connected actions need a connection.
          </div>
        )}
        {(pathname === '/scan' || pathname === '/governance') && (
          <div className="bm-network-notice" role="note">
            Legacy demo · simulated claims and records; no authenticity or
            ownership verification.
          </div>
        )}
        <div className="bm-workspace-body">
          <main
            id="main-content"
            tabIndex={-1}
            ref={mainRef}
            className="bm-main"
          >
            <div className="bm-route-content" key={pathname}>
              {children}
            </div>
          </main>
          {!publicPage && (
            <aside className="bm-inspector" aria-label="Your experience">
              <ContextContent />
            </aside>
          )}
        </div>
      </div>
      {!publicPage && (
        <nav className="bm-bottom-nav" aria-label="Primary mobile navigation">
          {links('primary')}
        </nav>
      )}
    </div>
  )
}
