# brandme-agents

**Copyright (c) Brand.Me, Inc. All rights reserved.**

Supporting agent services for Brand.Me platform: Identity, Knowledge/RAG, and Compliance & Audit.

## Services

### 1. Identity Service (`/identity`)

**Port**: 8100
**Endpoint**: `GET /user/{user_id}/persona`

Provides user persona data, trust scores, and DID information.

**Response**:
```json
{
  "persona_warm_cold": 0.75,
  "persona_sport_couture": 0.60,
  "trust_score": 95.50,
  "region_code": "us-east1",
  "did_cardano": "did:cardano:abc123"
}
```

### 2. Knowledge Service (`/knowledge`)

**Port**: 8101
**Endpoint**: `GET /garment/{garment_id}/passport?scope=public`

Retrieves garment passport facets based on visibility scope.

**Response**:
```json
[
  {
    "facet_type": "authenticity",
    "facet_payload_preview": { "status": "verified" }
  },
  {
    "facet_type": "esg_score",
    "facet_payload_preview": { "score": "A+" }
  }
]
```

### 3. Compliance & Audit Service (`/compliance`)

**Port**: 8102

**Endpoints**:
- `POST /audit/log` - Log audit entry
- `POST /audit/anchorChain` - Anchor chain references
- `GET /audit/{scan_id}/explain` - Get human-readable audit explanation

## Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run identity service
cd identity && uvicorn main:app --reload --port 8100

# Run knowledge service
cd knowledge && uvicorn main:app --reload --port 8101

# Run compliance service
cd compliance && uvicorn main:app --reload --port 8102
```

## Architecture

- **Identity Service**: User persona and trust management
- **Knowledge Service**: RAG-based garment metadata retrieval
- **Compliance & Audit**: Hash-chained audit logging and regulator views

## License

Copyright (c) Brand.Me, Inc. All rights reserved.
