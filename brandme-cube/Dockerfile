# Multi-stage build for brandme-cube
FROM python:3.11-slim as base

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy shared brandme_core module
COPY brandme_core /app/brandme_core

# Install Python dependencies
COPY brandme-cube/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY brandme-cube/src /app/src

# Non-root user
RUN useradd -m -u 1000 brandme && \
    chown -R brandme:brandme /app
USER brandme

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8007/health || exit 1

# Expose port
EXPOSE 8007

# Run service
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8007"]
