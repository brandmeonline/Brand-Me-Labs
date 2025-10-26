# Brand.Me v7 — Stable Integrity Spine
# Prometheus metrics collection utilities
# brandme_core/metrics.py

import time
from typing import Dict, Optional
from prometheus_client import Counter, Histogram, Gauge, generate_latest
from .logging import get_logger

logger = get_logger("metrics")


# HTTP Request Metrics
http_requests_total = Counter(
    'http_requests_total',
    'Total number of HTTP requests',
    ['method', 'endpoint', 'status_code', 'service']
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint', 'service'],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
)

# Database Metrics
db_connections_active = Gauge(
    'db_connections_active',
    'Number of active database connections',
    ['service']
)

db_query_duration_seconds = Histogram(
    'db_query_duration_seconds',
    'Database query duration in seconds',
    ['service', 'operation'],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)
)

# Service Call Metrics
service_calls_total = Counter(
    'service_calls_total',
    'Total number of service-to-service calls',
    ['from_service', 'to_service', 'status']
)

service_call_duration_seconds = Histogram(
    'service_call_duration_seconds',
    'Service-to-service call duration in seconds',
    ['from_service', 'to_service'],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
)

# Business Metrics
scans_total = Counter(
    'scans_total',
    'Total number of garment scans',
    ['service', 'status']
)

policy_decisions_total = Counter(
    'policy_decisions_total',
    'Total number of policy decisions',
    ['decision', 'service']
)

escalations_total = Counter(
    'escalations_total',
    'Total number of escalations',
    ['service', 'reason']
)

# Error Metrics
errors_total = Counter(
    'errors_total',
    'Total number of errors',
    ['service', 'error_type']
)

# Health Metrics
health_check_status = Gauge(
    'health_check_status',
    'Health check status (1 = healthy, 0 = unhealthy)',
    ['service', 'component']
)


class MetricsCollector:
    """Utility class for collecting metrics in services."""
    
    def __init__(self, service_name: str):
        self.service_name = service_name
    
    def record_http_request(
        self,
        method: str,
        endpoint: str,
        status_code: int,
        duration: float
    ):
        """Record HTTP request metrics."""
        http_requests_total.labels(
            method=method,
            endpoint=endpoint,
            status_code=status_code,
            service=self.service_name
        ).inc()
        
        http_request_duration_seconds.labels(
            method=method,
            endpoint=endpoint,
            service=self.service_name
        ).observe(duration)
    
    def record_db_operation(self, operation: str, duration: float):
        """Record database operation metrics."""
        db_query_duration_seconds.labels(
            service=self.service_name,
            operation=operation
        ).observe(duration)
    
    def record_service_call(
        self,
        to_service: str,
        duration: float,
        success: bool
    ):
        """Record service-to-service call metrics."""
        status = 'success' if success else 'failure'
        service_calls_total.labels(
            from_service=self.service_name,
            to_service=to_service,
            status=status
        ).inc()
        
        service_call_duration_seconds.labels(
            from_service=self.service_name,
            to_service=to_service
        ).observe(duration)
    
    def record_scan(self, status: str):
        """Record scan event."""
        scans_total.labels(
            service=self.service_name,
            status=status
        ).inc()
    
    def record_policy_decision(self, decision: str):
        """Record policy decision."""
        policy_decisions_total.labels(
            decision=decision,
            service=self.service_name
        ).inc()
    
    def record_escalation(self, reason: str):
        """Record escalation event."""
        escalations_total.labels(
            service=self.service_name,
            reason=reason
        ).inc()
    
    def record_error(self, error_type: str):
        """Record error occurrence."""
        errors_total.labels(
            service=self.service_name,
            error_type=error_type
        ).inc()
    
    def update_health(self, component: str, healthy: bool):
        """Update health check status."""
        health_check_status.labels(
            service=self.service_name,
            component=component
        ).set(1 if healthy else 0)


def get_metrics_collector(service_name: str) -> MetricsCollector:
    """Get a metrics collector for the given service."""
    return MetricsCollector(service_name)


def generate_metrics() -> bytes:
    """Generate Prometheus metrics in text format."""
    return generate_latest()

