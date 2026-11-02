import type { Metadata } from 'next'
import { SocialHorizon } from '@/features/social/horizons'
export const metadata: Metadata = { title: 'Flow' }
export default function FlowPage() { return <SocialHorizon active="flow" /> }
