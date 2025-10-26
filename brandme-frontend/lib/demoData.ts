/**
 * Mock backend response data for development and testing
 */

export interface GarmentPassport {
  garment_id: string
  scan_id: string
  status: 'verified' | 'pending' | 'denied'
  escalated: boolean
  cardano_hash?: string
  midnight_hash?: string
  facets: Array<{
    facet_type: string
    facet_payload_preview: Record<string, any>
  }>
  created_at: string
}

export interface GarmentFeedItem {
  imageUrl: string
  title: string
  subtitle: string
  integrityStatus: 'verified' | 'pending'
}

export interface EscalationItem {
  scan_id: string
  garment_tag: string
  user_id_redacted: string
  reason: string
  created_at: string
  status: 'pending' | 'approved' | 'denied'
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
  return [
    {
      imageUrl: '/placeholder-garment-1.jpg',
      title: 'Organic Cotton Tee',
      subtitle: 'Climate-neutral production with ethical sourcing',
      integrityStatus: 'verified',
    },
    {
      imageUrl: '/placeholder-garment-2.jpg',
      title: 'Recycled Denim Jacket',
      subtitle: 'Made from 100% post-consumer denim waste',
      integrityStatus: 'verified',
    },
    {
      imageUrl: '/placeholder-garment-3.jpg',
      title: 'Hemp Linen Dress',
      subtitle: 'Regenerative agriculture with zero pesticides',
      integrityStatus: 'pending',
    },
    {
      imageUrl: '/placeholder-garment-4.jpg',
      title: 'Upcycled Wool Coat',
      subtitle: 'Deadstock fabric transformed by Italian artisans',
      integrityStatus: 'verified',
    },
    {
      imageUrl: '/placeholder-garment-5.jpg',
      title: 'Bamboo Silk Blouse',
      subtitle: 'Closed-loop water recycling in production',
      integrityStatus: 'verified',
    },
    {
      imageUrl: '/placeholder-garment-6.jpg',
      title: 'Tencel Trousers',
      subtitle: 'FSC-certified wood pulp with circular design',
      integrityStatus: 'verified',
    },
  ]
}

/**
 * Fetch user's stash collection (mock)
 */
export async function getMyStash(): Promise<GarmentFeedItem[]> {
  return [
    {
      imageUrl: '/placeholder-stash-1.jpg',
      title: 'Archive Wool Sweater',
      subtitle: 'Vintage 1990s sourced from Copenhagen',
      integrityStatus: 'verified',
    },
    {
      imageUrl: '/placeholder-stash-2.jpg',
      title: 'Japanese Selvedge Jeans',
      subtitle: 'Hand-loomed denim with natural indigo dye',
      integrityStatus: 'verified',
    },
    {
      imageUrl: '/placeholder-stash-3.jpg',
      title: 'Ethical Cashmere Scarf',
      subtitle: 'Mongolian cashmere with traceable supply chain',
      integrityStatus: 'verified',
    },
  ]
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
