# Copyright (c) Brand.Me, Inc. All rights reserved.
"""
OpenTelemetry Tracing and Metrics
==================================

Distributed tracing and metrics collection for Brand.Me platform.

Features:
- Automatic span creation for HTTP requests
- Custom instrumentation for database queries
- Metrics export to Prometheus
- Trace export to OTLP collector
"""

import os
from typing import Optional
from contextlib import contextmanager

from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from prometheus_client import start_http_server


# Global configuration
OTEL_ENABLED = os.getenv("OTEL_ENABLED", "true").lower() == "true"
OTEL_ENDPOINT = os.getenv("OTEL_ENDPOINT", "http://otel-collector:4317")
SERVICE_NAME_VAR = os.getenv("SERVICE_NAME", "brandme-unknown")
SERVICE_VERSION_VAR = os.getenv("SERVICE_VERSION", "0.1.0")
PROMETHEUS_PORT = int(os.getenv("PROMETHEUS_PORT", "8000"))


def setup_telemetry(service_name: Optional[str] = None) -> None:
    """
    Initialize OpenTelemetry tracing and metrics.

    Args:
        service_name: Override service name (defaults to SERVICE_NAME env var)
    """
    if not OTEL_ENABLED:
        return

    _service_name = service_name or SERVICE_NAME_VAR

    # Create resource with service information
    resource = Resource.create({
        SERVICE_NAME: _service_name,
        SERVICE_VERSION: SERVICE_VERSION_VAR,
        "deployment.environment": os.getenv("ENVIRONMENT", "development"),
        "service.namespace": "brandme",
    })

    # Setup tracing
    tracer_provider = TracerProvider(resource=resource)

    # Add OTLP span exporter
    otlp_exporter = OTLPSpanExporter(endpoint=OTEL_ENDPOINT, insecure=True)
    span_processor = BatchSpanProcessor(otlp_exporter)
    tracer_provider.add_span_processor(span_processor)

    trace.set_tracer_provider(tracer_provider)

    # Setup metrics
    prometheus_reader = PrometheusMetricReader()
    otlp_metric_exporter = OTLPMetricExporter(endpoint=OTEL_ENDPOINT, insecure=True)
    otlp_metric_reader = PeriodicExportingMetricReader(otlp_metric_exporter, export_interval_millis=60000)

    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[prometheus_reader, otlp_metric_reader],
    )
    metrics.set_meter_provider(meter_provider)

    # Auto-instrument libraries
    AsyncPGInstrumentor().instrument()
    HTTPXClientInstrumentor().instrument()
    RedisInstrumentor().instrument()

    # Start Prometheus HTTP server
    try:
        start_http_server(port=PROMETHEUS_PORT, addr="0.0.0.0")
    except OSError:
        pass  # Port already in use, likely already started


def instrument_fastapi(app):
    """
    Instrument FastAPI application with OpenTelemetry.

    Args:
        app: FastAPI application instance
    """
    if OTEL_ENABLED:
        FastAPIInstrumentor.instrument_app(app)


def get_tracer(name: str):
    """Get a tracer instance."""
    return trace.get_tracer(name)


def get_meter(name: str):
    """Get a meter instance for custom metrics."""
    return metrics.get_meter(name)


@contextmanager
def trace_span(name: str, attributes: Optional[dict] = None):
    """
    Context manager for creating custom spans.

    Usage:
        with trace_span("fetch_garment", {"garment_id": garment_id}):
            result = await fetch_garment(garment_id)
    """
    tracer = get_tracer(__name__)
    with tracer.start_as_current_span(name) as span:
        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, value)
        yield span


# Custom metrics
class BrandMeMetrics:
    """Custom metrics for Brand.Me platform."""

    def __init__(self):
        self.meter = get_meter("brandme.metrics")

        # Counters
        self.scan_counter = self.meter.create_counter(
            name="brandme.scans.total",
            description="Total number of scans processed",
            unit="1",
        )

        self.scan_errors = self.meter.create_counter(
            name="brandme.scans.errors",
            description="Total number of scan errors",
            unit="1",
        )

        self.blockchain_tx_counter = self.meter.create_counter(
            name="brandme.blockchain.transactions",
            description="Total blockchain transactions submitted",
            unit="1",
        )

        self.audit_log_counter = self.meter.create_counter(
            name="brandme.audit.entries",
            description="Total audit log entries created",
            unit="1",
        )

        # Histograms
        self.scan_duration = self.meter.create_histogram(
            name="brandme.scans.duration",
            description="Duration of scan processing",
            unit="ms",
        )

        self.db_query_duration = self.meter.create_histogram(
            name="brandme.db.query_duration",
            description="Database query duration",
            unit="ms",
        )

        self.http_request_duration = self.meter.create_histogram(
            name="brandme.http.request_duration",
            description="HTTP request duration",
            unit="ms",
        )

        # UpDown Counters
        self.active_scans = self.meter.create_up_down_counter(
            name="brandme.scans.active",
            description="Number of scans currently being processed",
            unit="1",
        )

        self.celery_queue_size = self.meter.create_up_down_counter(
            name="brandme.celery.queue_size",
            description="Number of tasks in Celery queues",
            unit="1",
        )

    def record_scan(self, scope: str, region: str, success: bool = True):
        """Record a scan event."""
        attributes = {"scope": scope, "region": region, "success": success}
        self.scan_counter.add(1, attributes)
        if not success:
            self.scan_errors.add(1, attributes)

    def record_scan_duration(self, duration_ms: float, scope: str):
        """Record scan processing duration."""
        self.scan_duration.record(duration_ms, {"scope": scope})

    def record_blockchain_tx(self, network: str, success: bool = True):
        """Record blockchain transaction."""
        self.blockchain_tx_counter.add(1, {"network": network, "success": success})

    def record_audit_entry(self, escalated: bool = False):
        """Record audit log entry."""
        self.audit_log_counter.add(1, {"escalated": escalated})

    def record_db_query(self, duration_ms: float, table: str):
        """Record database query duration."""
        self.db_query_duration.record(duration_ms, {"table": table})

    def record_http_request(self, duration_ms: float, service: str, status: int):
        """Record HTTP request duration."""
        self.http_request_duration.record(
            duration_ms,
            {"service": service, "status_code": status}
        )


# Global metrics instance
_metrics: Optional[BrandMeMetrics] = None


def get_metrics() -> BrandMeMetrics:
    """Get global metrics instance."""
    global _metrics
    if _metrics is None:
        _metrics = BrandMeMetrics()
    return _metrics
