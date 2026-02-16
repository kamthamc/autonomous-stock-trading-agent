from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

from opentelemetry import _logs
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor, ConsoleLogExporter
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter

from opentelemetry.sdk.resources import Resource
import os

def setup_telemetry(service_name: str = "trading-agent"):
    # Resource
    resource = Resource.create({"service.name": service_name})

    # 1. Tracing
    tracer_provider = TracerProvider(resource=resource)
    
    # OTLP Exporter (Sending to local collector or backend usually on localhost:4317)
    # If no collector is running, this might fail or warn. We'll add Console failure fallback if needed.
    
    otel_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    
    if otel_endpoint:
        otlp_exporter = OTLPSpanExporter() # defaults to localhost:4317 or env
        tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
    else:
        # Default to Console if no backend configured
         # tracer_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
         pass
    
    trace.set_tracer_provider(tracer_provider)
    
    # 2. Logging
    logger_provider = LoggerProvider(resource=resource)
    
    # 3. AI Review Logging
    # Create a separate logger for AI decisions that writes to .jsonl
    ai_logger = structlog.get_logger("ai_reviewer")
    # This is a simplified approach; in production, configure a specific handler
    # For now, relying on the main json log file which contains 'event=ai_signal_generated'
    # The user asked for a dedicated file. Let's add a file handler specifically for this.
    
    import logging
    ai_handler = logging.FileHandler("ai_trade_review.jsonl")
    ai_handler.setFormatter(logging.Formatter('%(message)s'))
    ai_handler.setLevel(logging.INFO)
    
    # Filter only AI events
    class AIFilter(logging.Filter):
        def filter(self, record):
            return "ai_signal_generated" in record.getMessage() or "ai_analysis_error" in record.getMessage()

    ai_handler.addFilter(AIFilter())
    logging.getLogger().addHandler(ai_handler)
    
    # 3. Instrumentations
    from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor
    AioHttpClientInstrumentor().instrument()
    
    return LoggingHandler(level=10, logger_provider=logger_provider)
