# Copyright (c) Brand.Me, Inc. All rights reserved.
#
# Dockerfile for Brand.Me Core Services
# ======================================
# Default (last) stage: runtime — read API, privacy exports, outbox worker,
# migration runner. Legacy stages: brain, policy, orchestrator, orchestrator-beat.

FROM python:3.11-slim AS base

# Set working directory
WORKDIR /app
ENV PYTHONPATH=/app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY brandme-core/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared brandme_core module
COPY brandme_core /app/brandme_core
COPY packages/contracts/generated/domain.schema.json /app/packages/contracts/generated/domain.schema.json

# Copy application code
COPY brandme-core/ /app/

# Create non-root user
RUN useradd -m -u 1000 brandme && chown -R brandme:brandme /app
USER brandme

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# Expose port
EXPOSE ${PORT:-8000}

# Default command (override in docker-compose for different services)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "${PORT:-8000}"]


# Brain service stage
FROM base AS brain
WORKDIR /app/brain
ENV SERVICE_NAME=brain
ENV PORT=8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]


# Policy service stage
FROM base AS policy
WORKDIR /app/policy
ENV SERVICE_NAME=policy
ENV PORT=8001
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", "--reload"]


# Orchestrator worker stage
FROM base AS orchestrator
WORKDIR /app/orchestrator
ENV SERVICE_NAME=orchestrator
ENV PORT=8002
CMD ["uvicorn", "worker:app", "--host", "0.0.0.0", "--port", "8002", "--reload"]


# Orchestrator beat scheduler stage (kept for compatibility, not used in new arch)
FROM base AS orchestrator-beat
WORKDIR /app/orchestrator
ENV SERVICE_NAME=orchestrator-beat
ENV C_FORCE_ROOT=true
CMD ["celery", "-A", "celery_app", "beat", "--loglevel=info"]


# Runtime stage for the strict-mode foundation processes. This is the LAST
# stage, so a build without --target (CI build-images, ci-cd.yml:253-264)
# produces it; the legacy stages above stay buildable with --target but are
# skipped by default. Build from the repository root:
#   docker build -f brandme-core/Dockerfile .
# Dependencies come only from the hash-verified lock CI tests against
# (scripts/python/requirements.lock, ci-cd.yml:142). No --reload, no celery.
# There is no default process: every manifest passes an explicit command
# (brandme-infra/helm/brandme). Running the image bare prints usage, exit 64.
FROM python:3.11.15-slim AS runtime
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY scripts/python/requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir --require-hashes -r /tmp/requirements.lock && rm /tmp/requirements.lock
# Root-owned and not writable by the runtime user. Pre-compiled so a
# read-only root filesystem needs no __pycache__ writes.
COPY brandme_core /app/brandme_core
COPY packages/contracts/generated/domain.schema.json /app/packages/contracts/generated/domain.schema.json
COPY brandme-data/spanner/migrations /app/brandme-data/spanner/migrations
RUN python -m compileall -q /app/brandme_core /app/brandme-data/spanner/migrations \
    && groupadd --system --gid 10001 brandme \
    && useradd --system --uid 10001 --gid 10001 --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin brandme
USER 10001:10001
CMD ["python", "-c", "import sys; sys.stderr.write('brandme-core runtime image has no default process. Run one of:\\n  python -m brandme_core.read_api [--check]\\n  python -m brandme_core.privacy_exports [--check | --worker [--once]]\\n  python -m brandme_core.events.worker [--check | --once]\\n  python brandme-data/spanner/migrations/runner.py {up,status,verify}\\n'); sys.exit(64)"]
