'use client'
import Link from 'next/link'
import type { components } from '@brandme/contracts'
import { useResource } from '@/lib/client/use-resource'
import { ResourceState } from '@/components/ui/resource-state'
import { AXES, type Persona } from './types'

type Me = components['schemas']['Me']
type WardrobeItem = components['schemas']['WardrobeItem']
type Badges = { badges: { badge_id: string; title: string; criteria: string; earned: boolean }[] }

/** This is the signed-in member's own card. It is never a public profile projection. */
export function PersonaCard() {
  const identity = useResource<Me>('/me')
  if (identity.error?.status === 401) return <section className="bm-identity-note" aria-label="Your account">
    <div><h2 className="bm-section-title">Make yourself at home.</h2>
      <p>You’re exploring without a signed-in account. Sign in to see your saved style.</p>
      <Link className="bm-text-link" href="/me/connections">Review account connection</Link>
    </div>
  </section>
  return <>
    <ResourceState {...identity} retry={identity.reload} />
    {identity.data && <PrivatePersona key={identity.data.member.id} member={identity.data.member} />}
  </>
}

function PrivatePersona({ member }: { member: Me['member'] }) {
  const persona = useResource<Persona>('/me/persona')
  const rewards = useResource<Badges>('/rewards')
  const wardrobe = useResource<{ items: WardrobeItem[] }>('/wardrobe/items?collection=owned&limit=3')
  const profile = persona.data?.profile.member_id === member.id ? persona.data : null
  const visibleAxes = profile?.axes.filter(axis => !axis.hidden && (axis.declared !== null || axis.inferred !== null)) ?? []
  const earnedBadges = rewards.data?.badges.filter(badge => badge.earned) ?? []
  const owned = wardrobe.data?.items.filter(item => item.member_id === member.id) ?? []
  return <section className="bm-persona-card bm-flow-stack" aria-label="Your private style card">
    <header>
      <p className="bm-eyebrow">Only you · Your style card</p>
      <h2 className="bm-editorial-title">{member.display_name || 'Your style, in your words.'}</h2>
      {member.handle && <p>@{member.handle}</p>}
      <p>This card shows your own saved preferences and earned badges. It is not a public profile.</p>
    </header>
    <section aria-labelledby="card-preferences">
      <h3 id="card-preferences" className="bm-section-title">Your taste</h3>
      <ResourceState {...persona} retry={persona.reload} />
      {persona.data && !profile && <p role="alert">Your account changed. Refresh your style card before continuing.</p>}
      {profile && <>
        {visibleAxes.length ? <dl className="bm-persona-axes">
          {visibleAxes.map(axis => {
            const labels = AXES.find(([key]) => key === axis.axis)
            if (!labels) return null
            return <div key={axis.axis}>
              <dt>{labels[1]}</dt>
              <dd>{labels[2]} ↔ {labels[3]}</dd>
              <dd>You chose: {axis.declared ?? 'Not set'}{axis.locked ? ' · Locked' : ''}</dd>
              <dd>Inferred: {axis.inferred ?? 'Unknown'}</dd>
              <dd>Used for recommendations: {axis.effective ?? 'Not set'}</dd>
            </div>
          })}
        </dl> : <p>No visible style preferences yet. Your choices are yours to shape.</p>}
        <p className="bm-support">Saved revision {profile.profile.version}. Hidden preferences stay out of this card.</p>
      </>}
      <Link className="bm-text-link" href="/me/style">Shape my style</Link>
    </section>
    <section aria-labelledby="card-badges">
      <h3 id="card-badges" className="bm-section-title">Earned badges</h3>
      <ResourceState {...rewards} retry={rewards.reload} />
      {rewards.data && (earnedBadges.length ? <ul className="bm-card-list">{earnedBadges.map(badge =>
        <li key={badge.badge_id}><strong>{badge.title}</strong><p>{badge.criteria}</p></li>)}</ul>
        : <p>No badges earned yet. Useful contributions will be recognized here.</p>)}
      <Link className="bm-text-link" href="/rewards">View rewards and evidence</Link>
    </section>
    <section aria-labelledby="card-wardrobe">
      <h3 id="card-wardrobe" className="bm-section-title">From your saved wardrobe</h3>
      <ResourceState {...wardrobe} retry={wardrobe.reload} />
      {wardrobe.data && (owned.length ? <ul className="bm-card-list">{owned.map(item =>
        <li key={item.id}>{item.title}</li>)}</ul> : <p>No saved owned pieces to show.</p>)}
      <p className="bm-support">Visible only to you. Public profiles, house standings and curated highlights are not available yet.</p>
    </section>
  </section>
}
