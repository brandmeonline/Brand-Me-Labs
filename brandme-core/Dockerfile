# Copyright (c) Brand.Me, Inc. All rights reserved.
#
# Dockerfile for Brand.Me Core Services
# ======================================
# Includes: Brain, Policy, Orchestrator

FROM python:3.11-slim as base

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared brandme_core module
COPY ../brandme_core /app/brandme_core

# Copy application code
COPY . /app

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
FROM base as brain
WORKDIR /app/brain
ENV SERVICE_NAME=brain
ENV PORT=8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]


# Policy service stage
FROM base as policy
WORKDIR /app/policy
ENV SERVICE_NAME=policy
ENV PORT=8001
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", "--reload"]


# Orchestrator worker stage
FROM base as orchestrator
WORKDIR /app/orchestrator
ENV SERVICE_NAME=orchestrator
ENV PORT=8002
CMD ["uvicorn", "worker:app", "--host", "0.0.0.0", "--port", "8002", "--reload"]


# Orchestrator beat scheduler stage (kept for compatibility, not used in new arch)
FROM base as orchestrator-beat
WORKDIR /app/orchestrator
ENV SERVICE_NAME=orchestrator-beat
ENV C_FORCE_ROOT=true
CMD ["celery", "-A", "celery_app", "beat", "--loglevel=info"]
