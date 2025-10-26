# Copyright (c) Brand.Me, Inc. All rights reserved.
#
# Dockerfile for Brand.Me Governance Console
# ===========================================

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
COPY governance_console/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared brandme_core module
COPY ../brandme_core /app/brandme_core

# Copy application code
COPY governance_console /app/governance_console

# Create non-root user
RUN useradd -m -u 1000 brandme && chown -R brandme:brandme /app
USER brandme

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:${PORT:-8006}/health || exit 1

# Expose port
EXPOSE ${PORT:-8006}

# Default command
CMD ["uvicorn", "governance_console.main:app", "--host", "0.0.0.0", "--port", "8006", "--reload"]


# Governance console stage
FROM base as governance
WORKDIR /app/governance_console
ENV SERVICE_NAME=governance
ENV PORT=8006
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8006", "--reload"]
