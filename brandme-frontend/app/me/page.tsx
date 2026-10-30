import type { Metadata } from 'next'
import Link from 'next/link'
import {
  ArrowUpRight,
  SlidersHorizontal,
  Database,
  Link2,
  Gift,
  ShoppingBag,
  Shield,
} from 'lucide-react'
import { PageHeading } from '@/components/shell/page-heading'
export const metadata: Metadata = { title: 'Me' }
const entries = [
  {
    href: '/me/style',
    title: 'Looking Glass',
    description: 'Understand and shape your style preferences.',
    icon: SlidersHorizontal,
  },
  {
    href: '/me/data',
    title: 'My Data',
    description: 'Understand what is saved, and what is yours to change.',
    icon: Database,
  },
  {
    href: '/me/connections',
    title: 'Connections',
    description: 'Choose the services and assistants you allow in.',
    icon: Link2,
  },
  {
    href: '/rewards',
    title: 'Rewards',
    description: 'Useful contributions, meaningful recognition.',
    icon: Gift,
  },
  {
    href: '/orders',
    title: 'Orders',
    description: 'Purchases and their next chapters.',
    icon: ShoppingBag,
  },
  {
    href: '/settings',
    title: 'Settings',
    description: 'Make this space feel comfortable for you.',
    icon: Shield,
  },
]
export default function MePage() {
  return (
    <>
      <PageHeading
        eyebrow="Me / always a work in progress"
        title="You get the final say."
        description="Your taste is a starting point, never a box to fit into."
      />
      <div className="bm-identity-note">
        <span className="bm-avatar bm-avatar-large" aria-hidden="true">
          U
        </span>
        <div>
          <h2 className="bm-section-title">Make yourself at home.</h2>
          <p>
            You’re exploring without an account. No style profile has been
            inferred or saved.
          </p>
        </div>
      </div>
      <div className="bm-directory">
        {entries.map(({ href, title, description, icon: Icon }) => (
          <Link href={href} className="bm-directory-link" key={href}>
            <Icon aria-hidden="true" size={24} strokeWidth={1.4} />
            <div>
              <h2>{title}</h2>
              <p>{description}</p>
            </div>
            <ArrowUpRight aria-hidden="true" size={20} />
          </Link>
        ))}
      </div>
    </>
  )
}
