/**
 * Mock backend response data for development and testing
 */
import catalog from '../features/spatial/generated-catalog.json'

export interface GarmentPassport {
  garment_id: string
  scan_id: string
  status: 'verified' | 'pending' | 'denied'
  escalated: boolean
  cardano_hash?: string
  midnight_hash?: string
  // backward-compatible aliases used by scan page
  cardano_tx_hash?: string
  midnight_tx_hash?: string
  request_id?: string
  region_code?: string
  resolved_scope?: string
  facets: Array<{
    facet_type: string
    facet_payload_preview: Record<string, any>
  }>
  created_at: string
}

export interface GarmentFeedItem {
  imageUrl: string
  href: string
  title: string
  subtitle: string
  integrityStatus: 'verified' | 'pending' | 'demo'
}

export interface EscalationItem {
  scan_id: string
  garment_tag: string
  user_id_redacted: string
  reason: string
  created_at: string
  status: 'pending' | 'approved' | 'denied'
  region_code?: string
}

/**
 * Fetch garment passport after scan (mock)
 */
export async function resolveScanAndFetchPassport(): Promise<GarmentPassport> {
  // In production, this would call the Brain service /intent/resolve
  // followed by orchestrator scan flow
  return {
    garment_id: 'GRMT_001',
    scan_id: 'SCAN_ABC123',
    status: 'verified',
    escalated: false,
    cardano_hash: 'tx_cardano_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6',
    midnight_hash: 'tx_midnight_z9y8x7w6v5u4t3s2r1q0p9o8n7m6l5k4',
    facets: [
      {
        facet_type: 'ESG',
        facet_payload_preview: {
          summary: 'Climate neutral production facility with renewable energy sourcing',
          rating: 'A+',
          carbon_offset_kg: 12.5,
        },
      },
      {
        facet_type: 'ORIGIN',
        facet_payload_preview: {
          designer: 'Stella McCartney',
          cut_and_sewn: 'Italy',
          fabric_sourced: 'Portugal',
          ethical_certification: 'Fair Trade Certified',
        },
      },
      {
        facet_type: 'MATERIALS',
        facet_payload_preview: {
          composition: '95% Organic Cotton, 5% Elastane',
          sourcing: 'GOTS-certified organic cotton from regenerative farms in Turkey',
          recyclability: 'Fully biodegradable',
        },
      },
    ],
    created_at: '2025-10-26T14:32:00Z',
  }
}

/**
 * Fetch discovery feed (mock)
 */
export async function getDiscoveryFeed(): Promise<GarmentFeedItem[]> {
  return ['tee', 'jacket', 'dress', 'knit', 'overshirt', 'trousers'].map(demoGarment)
}

// Keep demo titles, posters and preview destinations tied to the same original asset.
function demoGarment(slug: string): GarmentFeedItem {
  const garment = catalog.products.find(product => product.slug === slug)
  if (!garment) throw new Error(`Missing demo garment: ${slug}`)
  return {
    imageUrl: garment.poster,
    href: `/try/${garment.slug}`,
    title: garment.title,
    subtitle: 'Explore the original garment image and approximate 3D preview.',
    integrityStatus: 'demo',
  }
}

/**
 * Fetch user's stash collection (mock)
 */
export async function getMyStash(): Promise<GarmentFeedItem[]> {
  return ['knit', 'trousers', 'bag'].map(demoGarment)
}

/**
 * Fetch governance escalations (mock)
 */
export async function getEscalations(): Promise<EscalationItem[]> {
  return [
    {
      scan_id: 'SCAN_ESC001',
      garment_tag: 'TAG_ABC123',
      user_id_redacted: 'user_a1b2****',
      reason: 'Policy flag: cross-region scan from restricted location',
      created_at: '2025-10-26T12:00:00Z',
      status: 'pending',
    },
    {
      scan_id: 'SCAN_ESC002',
      garment_tag: 'TAG_XYZ789',
      user_id_redacted: 'user_c3d4****',
      reason: 'Sensitive facet detected: requires manual review',
      created_at: '2025-10-26T11:30:00Z',
      status: 'pending',
    },
    {
      scan_id: 'SCAN_ESC003',
      garment_tag: 'TAG_DEF456',
      user_id_redacted: 'user_e5f6****',
      reason: 'User consent version mismatch',
      created_at: '2025-10-26T10:15:00Z',
      status: 'approved',
    },
  ]
}
