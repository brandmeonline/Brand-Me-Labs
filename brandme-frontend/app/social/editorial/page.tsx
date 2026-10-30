import type { Metadata } from 'next'
import { SocialHorizon } from '@/features/social/horizons'
export const metadata: Metadata = { title: 'Editorial' }
export default function EditorialPage() { return <SocialHorizon active="editorial" /> }
