"""Translate persisted tool envelopes into prompt and storage payloads."""

from __future__ import annotations

import json

from pydantic import BaseModel

from src.models.conversation import ToolCallRecord


def tool_call_records_to_prompt_blocks(
    tool_call_records: list[ToolCallRecord],
) -> list[str]:
    """Render tool call records into prompt blocks for ContextBuilder."""

    blocks = []
    for tool_call in tool_call_records:
        if tool_call.result is None:
            continue

        lines = [f"Tool: {tool_call.tool_name}"]
        selection_reason = tool_call.arguments.get("selection_reason")
        if selection_reason:
            lines.append(f"Selection reason: {selection_reason}")

        lines.append(f"Confidence: {tool_call.result.confidence.value}")
        if tool_call.result.validated_against:
            lines.append(f"Validated against: {tool_call.result.validated_against}")

        if tool_call.result.source_ref:
            lines.append(
                "Source: "
                f"system={tool_call.result.source_ref.system}, "
                f"artifact={tool_call.result.source_ref.artifact}, "
                f"locator={tool_call.result.source_ref.locator}"
            )

        lines.append("Value:")
        lines.append(
            json.dumps(
                _to_jsonable(tool_call.result.value),
                indent=2,
                sort_keys=True,
            )
        )
        blocks.append("\n".join(lines))

    return blocks


def collect_source_refs(tool_call_records: list[ToolCallRecord]) -> list[dict]:
    """Flatten tool-source provenance for assistant message persistence."""

    source_refs = []
    for tool_call in tool_call_records:
        for source_ref in tool_call.source_refs:
            source_refs.append(source_ref.model_dump(mode="json"))
    return source_refs


def tool_call_records_to_storage_payload(
    tool_call_records: list[ToolCallRecord],
) -> list[dict]:
    """Serialize typed tool call records for chatbot_messages.tool_calls."""

    return [tool_call.model_dump(mode="json") for tool_call in tool_call_records]


def _to_jsonable(value):
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return value
