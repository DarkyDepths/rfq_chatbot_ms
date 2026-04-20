"""Prometheus metrics for chatbot observability."""

from __future__ import annotations

from prometheus_client import Counter, Histogram


turns_total = Counter(
    "rfq_chatbot_turns_total",
    "Total number of chat turns processed.",
)

tool_calls_total = Counter(
    "rfq_chatbot_tool_calls_total",
    "Total number of tool calls executed by tool name.",
    ["tool_name"],
)

intent_classifications_total = Counter(
    "rfq_chatbot_intent_classifications_total",
    "Total number of intent classifications by intent.",
    ["intent"],
)

grounding_gaps_total = Counter(
    "rfq_chatbot_grounding_gaps_total",
    "Total number of turns where grounding gap handling was injected.",
)

upstream_errors_total = Counter(
    "rfq_chatbot_upstream_errors_total",
    "Total number of upstream errors by service and type.",
    ["service", "error_type"],
)

response_latency_seconds = Histogram(
    "rfq_chatbot_response_latency_seconds",
    "End-to-end chat turn latency in seconds.",
)


def record_tool_calls(tool_names: list[str]) -> None:
    """Increment per-tool call counters for current turn."""

    for tool_name in tool_names:
        tool_calls_total.labels(tool_name=tool_name).inc()


def record_intent(intent: str) -> None:
    """Increment intent classification counter."""

    intent_classifications_total.labels(intent=intent).inc()


def record_upstream_error(service: str, error_type: str) -> None:
    """Increment upstream error counter."""

    upstream_errors_total.labels(service=service, error_type=error_type).inc()
