# brandme-gateway

**Copyright (c) Brand.Me, Inc. All rights reserved.**

Edge API gateway for the Brand.Me platform.

## Features

- **OAuth Authentication**: JWT-based authentication with Google OAuth
- **Rate Limiting**: Request throttling per user/IP
- **NATS Publishing**: Event-driven architecture via NATS JetStream
- **Request Logging**: Structured logging with Pino
- **Security**: Helmet.js, CORS, input validation
- **Health Checks**: Kubernetes-ready liveness/readiness probes

## API Endpoints

### POST /scan

Initiate a garment scan.

**Authentication**: Required (Bearer token)

**Request**:
```json
{
  "garment_tag": "NFC_TAG_001"
}
```

**Response** (202 Accepted):
```json
{
  "scan_id": "uuid",
  "status": "processing"
}
```

### GET /healthz

Health check endpoint.

**Response** (200 OK):
```json
{
  "status": "ok",
  "timestamp": "2025-10-25T12:00:00.000Z",
  "service": "brandme-gateway"
}
```

## Development

### Prerequisites

- Node.js 18+
- pnpm 8+
- NATS server

### Setup

```bash
# Install dependencies
pnpm install

# Copy environment variables
cp .env.example .env

# Edit .env with your configuration
```

### Running

```bash
# Development mode (with hot reload)
pnpm dev

# Build
pnpm build

# Production mode
pnpm start
```

### Testing

```bash
# Run tests
pnpm test

# Run tests with coverage
pnpm test:coverage

# Lint
pnpm lint

# Format code
pnpm format

# Type check
pnpm type-check
```

## Docker

```bash
# Build image
docker build -t brandme-gateway .

# Run container
docker run -p 3000:3000 --env-file .env brandme-gateway
```

## Environment Variables

See `.env.example` for all available configuration options.

Key variables:
- `OAUTH_CLIENT_ID`: OAuth client ID
- `OAUTH_CLIENT_SECRET`: OAuth client secret
- `JWT_SECRET`: Secret for JWT verification (min 32 chars)
- `NATS_URL`: NATS server URL
- `DEFAULT_REGION`: Default region code

## Architecture

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │ HTTPS (Bearer token)
       ▼
┌─────────────────────────────┐
│    brandme-gateway          │
│  - Auth Middleware          │
│  - Rate Limiter             │
│  - Request Logger           │
└──────┬──────────────────────┘
       │ NATS JetStream
       ▼
┌─────────────────────────────┐
│  NATS: scan.requested       │
└─────────────────────────────┘
```

## Security

- All requests must include valid JWT in `Authorization: Bearer <token>` header
- Secrets are never logged (redacted via Pino)
- Rate limiting prevents abuse
- CORS configured for trusted origins only
- Helmet.js provides additional security headers

## Deployment

### Kubernetes

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: brandme-gateway
spec:
  replicas: 3
  template:
    spec:
      containers:
      - name: gateway
        image: gcr.io/brandme/gateway:latest
        ports:
        - containerPort: 3000
        env:
        - name: OAUTH_CLIENT_ID
          valueFrom:
            secretKeyRef:
              name: oauth-secrets
              key: client-id
        livenessProbe:
          httpGet:
            path: /healthz
            port: 3000
        readinessProbe:
          httpGet:
            path: /healthz
            port: 3000
```

## License

Copyright (c) Brand.Me, Inc. All rights reserved.

Proprietary and confidential.
