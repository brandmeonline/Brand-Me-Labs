# Copyright (c) Brand.Me, Inc. All rights reserved.
#
# Dockerfile for Brand.Me Chain Service
# ======================================
# Cardano and Midnight blockchain integration

FROM node:18-alpine as base

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apk add --no-cache \
    python3 \
    make \
    g++ \
    curl

# Copy package files
COPY package.json pnpm-lock.yaml ./

# Install pnpm
RUN npm install -g pnpm@8.15.0

# Install dependencies
RUN pnpm install --frozen-lockfile

# Copy application code
COPY . .

# Build TypeScript
RUN pnpm build

# Create non-root user
RUN addgroup -g 1000 brandme && \
    adduser -D -u 1000 -G brandme brandme && \
    chown -R brandme:brandme /app
USER brandme

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:${PORT:-3001}/health || exit 1

# Expose port
EXPOSE ${PORT:-3001}

# Start application
CMD ["node", "dist/index.js"]


# Production stage
FROM base as production
ENV NODE_ENV=production
RUN pnpm prune --production


# Development stage
FROM base as development
ENV NODE_ENV=development
CMD ["pnpm", "dev"]
