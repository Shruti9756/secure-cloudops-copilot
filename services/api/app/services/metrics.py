from typing import Literal

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)

type RAGRequestStatus = Literal[
    "grounded",
    "insufficient_evidence",
    "citation_validation_failed",
    "safety_validation_failed",
    "invalid_question",
    "rate_limited",
    "rate_limit_unavailable",
    "model_provider_unavailable",
]

type RAGCacheStatus = Literal["HIT", "MISS", "BYPASS", "NOT_CHECKED"]

# A dedicated registry exposes only SecureCloudOps application metrics.
# It avoids accidentally publishing unrelated runtime/process details.
METRICS_REGISTRY = CollectorRegistry()

HTTP_REQUESTS_TOTAL = Counter(
    "secure_cloudops_http_requests_total",
    "Total HTTP requests handled by the SecureCloudOps API.",
    labelnames=("method", "route", "status_code"),
    registry=METRICS_REGISTRY,
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "secure_cloudops_http_request_duration_seconds",
    "Time spent handling SecureCloudOps API HTTP requests.",
    labelnames=("method", "route", "status_code"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=METRICS_REGISTRY,
)

RAG_REQUESTS_TOTAL = Counter(
    "secure_cloudops_rag_requests_total",
    "Total guarded RAG request outcomes grouped by bounded status and cache labels.",
    labelnames=("status", "cache_status"),
    registry=METRICS_REGISTRY,
)


def observe_http_request(
    *,
    method: str,
    route: str,
    status_code: int,
    duration_seconds: float,
) -> None:
    """Record one finished request using only bounded, non-sensitive labels."""
    labels = {
        "method": method,
        "route": route,
        "status_code": str(status_code),
    }

    # Never add question text, request IDs, tenant IDs, filenames, or source paths
    # as metric labels. Those values can leak data and create too many time series.
    HTTP_REQUESTS_TOTAL.labels(**labels).inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(**labels).observe(duration_seconds)


def observe_rag_request(
    *,
    status: RAGRequestStatus,
    cache_status: RAGCacheStatus,
) -> None:
    """Record one guarded RAG outcome without retaining AI request content."""
    RAG_REQUESTS_TOTAL.labels(
        status=status,
        cache_status=cache_status,
    ).inc()


def render_metrics() -> bytes:
    """Return the current Prometheus-compatible metrics document."""
    return generate_latest(METRICS_REGISTRY)


def metrics_content_type() -> str:
    """Return the standard Prometheus HTTP content type."""
    return CONTENT_TYPE_LATEST
