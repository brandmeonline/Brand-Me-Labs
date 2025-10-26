# Copyright (c) Brand.Me, Inc. All rights reserved.
#
# Dockerfile for Brand.Me Agent Services
# =======================================
# Includes: Identity, Knowledge, Compliance

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
  CMD curl -f http://localhost:${PORT:-8100}/health || exit 1

# Expose port
EXPOSE ${PORT:-8100}

# Default command
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "${PORT:-8100}"]


# Identity service stage
FROM base as identity
WORKDIR /app/identity
ENV SERVICE_NAME=identity
ENV PORT=8100
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8100", "--reload"]


# Knowledge service stage
FROM base as knowledge
WORKDIR /app/knowledge
ENV SERVICE_NAME=knowledge
ENV PORT=8101
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8101", "--reload"]


# Compliance service stage
FROM base as compliance
WORKDIR /app/compliance
ENV SERVICE_NAME=compliance
ENV PORT=8102
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8102", "--reload"]


# Agentic orchestrator stage
FROM base as agentic
WORKDIR /app/agentic
ENV SERVICE_NAME=agentic
ENV PORT=8200
COPY agentic/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
CMD ["python", "orchestrator/main.py"]
