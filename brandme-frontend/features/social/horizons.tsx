import Link from 'next/link'
import type { ReactNode } from 'react'
import { PageHeading } from '../../components/shell/page-heading'

const horizons = [
  { id: 'now', label: 'Now' },
  { id: 'flow', label: 'Flow' },
  { id: 'editorial', label: 'Editorial' },
] as const
export type Horizon = typeof horizons[number]['id']

export function SocialHorizon({ active, children }: { active: Horizon; children?: ReactNode }) {
  return <>
    <PageHeading eyebrow="Social" title="Good taste, shared."
      description="A moment to help a friend. A place for the houses and ideas you care about." />
    <nav className="bm-horizon-nav" aria-label="Social horizons">
      {horizons.map(horizon => <Link key={horizon.id} href={`/social/${horizon.id}`}
        aria-current={active === horizon.id ? 'page' : undefined}>{horizon.label}</Link>)}
    </nav>
    <div className="bm-social-stream-container"><div className="bm-social-streams">
      <section aria-labelledby={`horizon-${active}`} className="bm-flow-stack">
        <h2 id={`horizon-${active}`} className="bm-editorial-title">{horizons.find(horizon => horizon.id === active)!.label}</h2>
        {children ?? <div className="bm-horizon-unavailable">
          <p className="bm-eyebrow">Not available yet</p>
          <h3 className="bm-section-title">{active === 'flow' ? 'Your houses, in one place.' : 'A considered point of view.'}</h3>
          <p>{active === 'flow'
            ? 'Flow is not available in this preview. Updates from your houses and your circle are not connected yet.'
            : 'Editorial is not available in this preview. Curated stories and runway imagery are not connected yet.'}</p>
          <Link className="bm-text-link" href="/social/now">See decisions in Now</Link>
        </div>}
      </section>
      <aside className="bm-brand-stream" aria-labelledby="brand-stream-heading">
        <p className="bm-eyebrow">Alongside your circle</p>
        <h2 id="brand-stream-heading" className="bm-section-title">Brands &amp; designers</h2>
        <p>This separate stream is not available in the preview yet.</p>
        <Link className="bm-text-link" href="/discover">Explore Shops</Link>
      </aside>
    </div></div>
  </>
}
