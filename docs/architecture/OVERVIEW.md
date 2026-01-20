# Brand.Me Platform - Architecture Overview (v9)

**Copyright (c) Brand.Me, Inc. All rights reserved.**

For complete architecture documentation, see [SYSTEM_ARCHITECTURE.md](./SYSTEM_ARCHITECTURE.md).

---

## Quick Reference

### v9 Core Technologies

| Technology | Purpose |
|------------|---------|
| **Google Cloud Spanner** | Native Property Graph, O(1) consent lookups, Material tracking |
| **Firestore** | Real-time wardrobe sync, AR glasses biometric sync (<100ms) |
| **Model Context Protocol** | External agent access to Style Vault (7 tools) |
| **Cardano** | Public provenance, ESG oracle verification |
| **Midnight** | Private ownership, ZK burn proofs for circular economy |

### Architecture Principles

- **Dual-Blockchain**: Public provenance on Cardano, private ownership on Midnight
- **Dual-Database**: Spanner for consistency, Firestore for real-time
- **MCP-First**: External agents access via Model Context Protocol
- **ESG Verification**: All agent transactions require Cardano oracle check
- **Human-in-the-Loop**: Escalation workflow for high-risk decisions
- **Zero-Trust**: Authentication and rate limiting throughout

### Service Ports

| Service | Port | Description |
|---------|------|-------------|
| brain | 8000 | Intent resolver, scan entrypoint |
| policy | 8001 | Consent graph & policy decisions |
| orchestrator | 8002 | Scan processing & blockchain anchoring |
| knowledge | 8003 | Safe facet retrieval |
| compliance | 8004 | Hash-chained audit, ESG verification |
| identity | 8005 | User profiles, ZK proofs |
| governance | 8006 | Human review console |
| cube | 8007 | Product Cube with real-time state |

### Key Concepts

- **Product Cube**: 7-face digital passport for physical assets
- **DPP Lifecycle**: PRODUCED → ACTIVE → REPAIR → DISSOLVE → REPRINT
- **ESG Verification**: Cardano oracle verification for ethical oversight
- **Burn Proofs**: Midnight ZK proofs for circular economy material recovery

---

## Documentation Links

- [System Architecture](./SYSTEM_ARCHITECTURE.md) - Complete v9 architecture
- [Agentic Architecture](./AGENTIC_ARCHITECTURE.md) - Agent system design
- [Deployment Guide](../deployment/DEPLOYMENT_GUIDE.md) - How to deploy
- [Current Status](../status/CURRENT_STATUS.md) - Platform status

---

**Document Version**: 9.0.0
**Last Updated**: January 2026
