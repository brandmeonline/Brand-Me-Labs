import type { Metadata } from 'next'
import Link from 'next/link'
import { SocialHorizon } from '@/features/social/horizons'
import { Circle } from '@/features/social/circle'
export const metadata: Metadata = { title: 'Now' }
export default function NowPage() {
  return <SocialHorizon active="now">
    <p>Five minutes. An honest opinion from the people you choose.</p>
    <Circle showPeople={false} />
    <Link className="bm-text-link" href="/circle">Manage my circle</Link>
  </SocialHorizon>
}
