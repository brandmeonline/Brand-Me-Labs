# Brand.Me Frontend

Next.js 14 frontend for the Brand.Me platform - bringing integrity and provenance to fashion through blockchain-anchored garment passports.

## Stack

- **Framework**: Next.js 14 (App Router)
- **Language**: TypeScript 5.3
- **Styling**: Tailwind CSS
- **Components**: shadcn/ui + lucide-react
- **Design**: Editorial high-contrast dark theme

## Routes

- `/shop` - Discovery feed of verified garments
- `/stash` - User's saved collection
- `/scan` - Garment passport view after NFC scan
- `/governance` - Admin console for reviewing escalated scans

## Key Components

### IntegrityBadge
Displays blockchain verification status with truncated transaction hashes from Cardano (public) and Midnight (private) chains.

### GarmentCard
Fashion story card with 3:4 aspect ratio, hover effects, and verification badge.

### FacetList
Renders garment facets (ESG, ORIGIN, MATERIALS) with custom preview layouts.

### Header
Global navigation with integrity signaling badge.

## Architecture

### Request ID Tracing
All backend calls propagate `X-Request-Id` header for distributed tracing across microservices.

```typescript
import { BrandMeClient } from '@/lib/api'

const client = new BrandMeClient()
const passport = await client.get('/garment/GRMT_001/passport')
```

### Mock Data
Development mode uses realistic mock responses matching backend API contracts:
- `lib/demoData.ts` - Mock backend responses
- `lib/api.ts` - Request ID handling utilities

## Development

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000)

## Environment Variables

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Backend Integration

In production, frontend calls:
- Brain service: `/intent/resolve` for scan flow
- Orchestrator: `/scan/commit` for passport retrieval
- Identity: `/identity/{user_id}/profile` for user data
- Governance: `/governance/escalations` for admin console

## Design Philosophy

**Editorial, not e-commerce**: High-contrast monochrome palette with accent colors for trust signals (green for verified, yellow for pending, red for denied).

**Integrity-first**: Every touchpoint reinforces blockchain verification - from the global header badge to individual garment cards.

**Provenance storytelling**: Garment passports tell the full story of origin, materials, and sustainability through structured facets.

## Security & Privacy

- PII redaction in all user-facing displays
- Request ID propagation for audit trail
- Escalation handling for sensitive content
- Human governance review for edge cases
