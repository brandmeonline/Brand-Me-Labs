# Brand.Me v7 — Stable Integrity Spine
# OpenTelemetry tracing utilities
# brandme_core/telemetry.py

from functools import wraps
import time
from typing import Callable, Any
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource
from .logging import get_logger

logger = get_logger("telemetry")


class TelemetrySetup:
    """OpenTelemetry setup and configuration."""
    
    def __init__(self, service_name: str, service_version: str = "v7"):
        self.service_name = service_name
        self.service_version = service_version
        self._configured = False
    
    def configure(
        self,
        otlp_endpoint: str = None,
        enable_tracing: bool = True
    ):
        """Configure OpenTelemetry for the service."""
        if self._configured:
            logger.warning({"event": "telemetry_already_configured"})
            return
        
        if not enable_tracing:
            logger.info({"event": "telemetry_disabled"})
            return
        
        try:
            # Create resource
            resource = Resource.create({
                "service.name": self.service_name,
                "service.version": self.service_version,
            })
            
            # Create tracer provider
            provider = TracerProvider(resource=resource)
            
            # Add OTLP exporter if endpoint provided
            if otlp_endpoint:
                otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
                provider.add_span_processor(
                    BatchSpanProcessor(otlp_exporter)
                )
                logger.info({
                    "event": "telemetry_configured",
                    "service": self.service_name,
                    "endpoint": otlp_endpoint,
                })
            else:
                logger.info({
                    "event": "telemetry_configured_no_endpoint",
                    "service": self.service_name,
                })
            
            # Set the global tracer provider
            trace.set_tracer_provider(provider)
            
            # Instrument HTTP clients
            HTTPXClientInstrumentor().instrument()
            
            self._configured = True
            
        except Exception as e:
            logger.error({
                "event": "telemetry_configure_failed",
                "error": str(e),
            })
    
    def get_tracer(self):
        """Get tracer instance for this service."""
        if not self._configured:
            return trace.NoOpTracer()
        return trace.get_tracer(self.service_name)


def trace_function(name: str = None):
    """Decorator to trace a function with OpenTelemetry."""
    def decorator(func: Callable) -> Callable:
        span_name = name or f"{func.__module__}.{func.__name__}"
        
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            tracer = trace.get_tracer(__name__)
            with tracer.start_as_current_span(span_name) as span:
                span.set_attribute("function.name", func.__name__)
                span.set_attribute("function.module", func.__module__)
                
                start_time = time.time()
                try:
                    result = await func(*args, **kwargs)
                    duration = time.time() - start_time
                    span.set_attribute("duration", duration)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    duration = time.time() - start_time
                    span.set_attribute("duration", duration)
                    span.set_status(Status(StatusCode.ERROR))
                    span.record_exception(e)
                    raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            tracer = trace.get_tracer(__name__)
            with tracer.start_as_current_span(span_name) as span:
                span.set_attribute("function.name", func.__name__)
                span.set_attribute("function.module", func.__module__)
                
                start_time = time.time()
                try:
                    result = func(*args, **kwargs)
                    duration = time.time() - start_time
                    span.set_attribute("duration", duration)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    duration = time.time() - start_time
                    span.set_attribute("duration", duration)
                    span.set_status(Status(StatusCode.ERROR))
                    span.record_exception(e)
                    raise
        
        # Return async wrapper if function is async, sync otherwise
        import inspect
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator
