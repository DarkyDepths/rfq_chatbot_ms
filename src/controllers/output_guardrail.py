"""Phase 6 structural output guardrail checks."""

from __future__ import annotations

from src.controllers.tool_controller import CapabilityStatusHit


class OutputGuardrail:
    """Evaluates post-generation structural guardrail checks."""

    def evaluate(
        self,
        intent: str,
        assistant_text: str,
        source_refs: list,
        grounding_gap_injected: bool,
        capability_status_hit: CapabilityStatusHit | None,
    ) -> str:
        """Return pass or one violation type for the given turn."""

        if intent in ["general_knowledge", "conversational"]:
            return "pass"

        if intent == "rfq_specific":
            if not source_refs and not grounding_gap_injected:
                return "grounding_violation"
            return "pass"

        if intent == "disambiguation":
            normalized = assistant_text.lower()
            if "?" not in assistant_text and "which" not in normalized and "rfq" not in normalized:
                return "disambiguation_shape_violation"
            return "pass"

        if intent == "unsupported":
            if (
                capability_status_hit is not None
                and capability_status_hit.capability_name not in assistant_text
            ):
                return "unsupported_routing_violation"
            return "pass"

        return "pass"
