# brandme-console

**Copyright (c) Brand.Me, Inc. All rights reserved.**

Web interfaces for Brand.Me platform: Governance Console and Transparency Portal.

## Applications

### 1. Governance Console (Internal)

**Authentication**: RBAC (ROLE_GOVERNANCE, ROLE_COMPLIANCE)

**Pages**:
- `/dashboard/scans` - View all scans
- `/dashboard/scan/[scan_id]` - Detailed scan view
- `/dashboard/escalations` - Flagged scans requiring review
- `/dashboard/reveal` - Controlled Midnight facet reveal (dual approval)

**Features**:
- View policy decisions and versions
- See blockchain transaction hashes
- Perform controlled reveals with dual approval
- Audit trail visibility

### 2. Transparency Portal (Public)

**Authentication**: Public (no login required)

**Pages**:
- `/proof/[scan_id]` - Public proof view

**Output**:
- Authenticity status (real/counterfeit)
- Creator attribution
- ESG proof hash summary
- Policy version used
- **No private Midnight data**

## Tech Stack

- **Framework**: Next.js 14 (App Router)
- **UI**: React, Tailwind CSS, shadcn/ui
- **State Management**: Zustand
- **API Client**: Axios
- **Authentication**: NextAuth.js

## Development

```bash
# Install dependencies
pnpm install

# Run development server
pnpm dev

# Build
pnpm build

# Start production
pnpm start

# Lint
pnpm lint
```

## Environment Variables

```bash
# API URLs
NEXT_PUBLIC_GATEWAY_URL=http://localhost:3000
NEXT_PUBLIC_COMPLIANCE_SERVICE_URL=http://localhost:8102

# OAuth
NEXTAUTH_URL=http://localhost:3002
NEXTAUTH_SECRET=your-nextauth-secret

# Environment
NEXT_PUBLIC_ENVIRONMENT=development
```

## Architecture

```
┌────────────────────────────────────┐
│   Governance Console (Internal)    │
│   - RBAC Protected                 │
│   - Scan Management                │
│   - Escalation Handling            │
│   - Controlled Reveals             │
└────────────────────────────────────┘

┌────────────────────────────────────┐
│   Transparency Portal (Public)     │
│   - No Authentication              │
│   - Public Proof Display           │
│   - Creator Attribution            │
│   - ESG Verification               │
└────────────────────────────────────┘
```

## Deployment

### Docker

```bash
docker build -t brandme-console:latest .
docker run -p 3002:3002 brandme-console:latest
```

### Kubernetes

Helm chart available in `/brandme-infra/helm/brandme-console/`.

## License

Copyright (c) Brand.Me, Inc. All rights reserved.
