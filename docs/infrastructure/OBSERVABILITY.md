# Brand.Me - Observability Infrastructure

**Copyright (c) Brand.Me, Inc. All rights reserved.**

---

## Overview

Brand.Me implements comprehensive observability with Prometheus metrics, OpenTelemetry tracing, and structured logging across all services.

---

## Metrics (Prometheus)

### HTTP Metrics

**Endpoint**: `/metrics` on all services

**Available Metrics**:
```prometheus
# Request counts by method, endpoint, status, service
http_requests_total{method="POST",endpoint="/intent/resolve",status_code="200",service="brain"}

# Request duration histogram
http_request_duration_seconds{method="POST",endpoint="/intent/resolve",service="brain"}
```

### Database Metrics

```prometheus
# Active database connections
db_connections_active{service="brain"}

# Query duration histogram
db_query_duration_seconds{service="brain",operation="SELECT"}
```

### Service Call Metrics

```prometheus
# Service-to-service call counts
service_calls_total{from_service="brain",to_service="policy",status="success"}

# Service call duration
service_call_duration_seconds{from_service="brain",to_service="policy"}
```

### Business Metrics

```prometheus
# Garment scans
scans_total{service="brain",status="allowed"}

# Policy decisions
policy_decisions_total{decision="allow",service="policy"}

# Escalations
escalations_total{service="compliance",reason="policy_escalate"}
```

### Health Metrics

```prometheus
# Component health (1=healthy, 0=unhealthy)
health_check_status{service="brain",component="database"}
```

### Error Metrics

```prometheus
# Error occurrences
errors_total{service="brain",error_type="database_connection"}
```

---

## Distributed Tracing (OpenTelemetry)

### Implementation

All services use OpenTelemetry for distributed tracing:

```python
from brandme_core.telemetry import trace_function

@trace_function("resolve_intent")
async def intent_resolve(...):
    # Automatically traced
    pass
```

### Trace Propagation

- **Request ID**: X-Request-Id header propagated
- **Trace Context**: OpenTelemetry headers (traceparent)
- **Spans**: Service calls create child spans
- **Error Recording**: Exceptions recorded in spans

### OTLP Export

Configure via environment variables:
```bash
OTLP_ENDPOINT=https://otel-collector:4317
ENABLE_TRACING=true
```

---

## Logging

### Structured Logging

All services use structured JSON logging:

```json
{
  "event": "intent_resolved",
  "scan_id": "abc123...",
  "service": "brain",
  "level": "info",
  "timestamp": "2025-01-27T00:00:00Z",
  "request_id": "xyz789..."
}
```

### PII Redaction

Automatic PII redaction:
- User IDs truncated to 8 chars
- Sensitive fields marked [REDACTED]
- No wallet keys, purchase history, or private data in logs

### Log Levels

- **DEBUG**: Detailed diagnostic information
- **INFO**: Normal operational messages
- **WARN**: Warning conditions
- **ERROR**: Error conditions

---

## Health Checks

### Endpoint

All services expose `/health` endpoint

### Components Checked

- Database connectivity
- Service availability
- Dependency status

### Response Codes

- `200 OK`: Service healthy
- `503 Service Unavailable`: Service degraded
- `500 Internal Server Error`: Service error

---

## Alert Rules (Planned)

### Service Availability
```yaml
- alert: ServiceDown
  expr: up{job="brandme-brain"} == 0
  for: 5m
```

### Error Rate
```yaml
- alert: HighErrorRate
  expr: rate(errors_total[5m]) > 0.1
```

### Database Issues
```yaml
- alert: DatabaseUnhealthy
  expr: health_check_status{component="database"} == 0
```

---

## Prometheus Configuration

```yaml
global:
  scrape_interval: 15s
  
scrape_configs:
  - job_name: 'brandme-core'
    static_configs:
      - targets:
        - 'brain:8000'
        - 'policy:8001'
        - 'orchestrator:8002'
  
  - job_name: 'brandme-agents'
    static_configs:
      - targets:
        - 'identity:8005'
        - 'knowledge:8003'
        - 'compliance:8004'
        - 'governance:8006'
```

---

## Grafana Dashboards (Planned)

### 1. Service Health Dashboard
- Service availability
- Request rates
- Error rates
- Health status

### 2. Request Latency Dashboard
- P50, P95, P99 latencies
- Service-to-service call times
- Database query times

### 3. Business Metrics Dashboard
- Scan volumes
- Policy decision breakdown
- Escalation trends

---

## Testing Observability

### Check Metrics Endpoint

```bash
# Any service
curl http://localhost:8000/metrics

# Expected output
# HELP http_requests_total Total number of HTTP requests
# TYPE http_requests_total counter
http_requests_total{method="GET",endpoint="/health",service="brain",status_code="200"} 1.0
```

### Test Health Endpoint

```bash
curl http://localhost:8000/health
# {"status":"ok","service":"brain"}
```

### View Logs

```bash
# Docker logs
docker logs brandme-brain

# Structured JSON output
{"event":"service_started","service":"brain","timestamp":"..."}
```

---

## Configuration

### Environment Variables

```bash
# Enable/disable tracing
ENABLE_TRACING=true
OTLP_ENDPOINT=https://otel-collector:4317

# Log level
LOG_LEVEL=INFO

# Metrics port (optional, defaults to /metrics endpoint)
METRICS_PORT=9090
```

### Service Configuration

All services automatically expose metrics when using `brandme_core.metrics`:

```python
from brandme_core.metrics import get_metrics_collector

metrics = get_metrics_collector("service_name")
```

---

## Next Steps

1. Deploy Prometheus server
2. Create Grafana dashboards
3. Configure alert rules
4. Set up log aggregation (Loki)
5. Implement APM integration

---

*Observability Infrastructure: Complete*  
*Metrics: ✅ Ready*  
*Tracing: ✅ Ready*  
*Logging: ✅ Ready*  
*Dashboards: ⬜ In Progress*

