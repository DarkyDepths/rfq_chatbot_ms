"""Phase 6 structural output guardrail checks."""

from __future__ import annotations

import logging

from src.config.intent_patterns import response_contains_off_domain_content
from src.controllers.tool_controller import CapabilityStatusHit


logger = logging.getLogger(__name__)


class OutputGuardrail:
    """Evaluates post-generation structural guardrail checks."""

    def evaluate(
        self,
        intent: str,
        assistant_text: str,
        source_refs: list,
        grounding_gap_injected: bool,
        capability_status_hit: CapabilityStatusHit | None = None,
        conversational_subtype: str | None = None,
    ) -> str:
        """Return pass or one violation type for the given turn."""

        # Out-of-scope: should never reach here (deterministic refusal), but safety net
        if intent == "out_of_scope":
            return "pass"

        # Domain knowledge: check for off-domain content leak
        if intent == "domain_knowledge":
            if response_contains_off_domain_content(assistant_text):
                logger.warning(
                    "phase6_5.guardrail_domain_leak_detected",
                    extra={"intent": intent, "response_preview": assistant_text[:100]},
                )
                return "domain_leak"
            return "pass"

        # Conversational: soft length checks
        if intent == "conversational":
            if conversational_subtype == "greeting" and len(assistant_text) > 500:
                logger.warning(
                    "phase6_5.guardrail_verbose_greeting",
                    extra={"response_length": len(assistant_text)},
                )
                return "verbose_greeting_warning"  # Warning only, don't block
            if conversational_subtype in ("thanks", "goodbye") and len(assistant_text) > 300:
                logger.warning(
                    "phase6_5.guardrail_verbose_conversational",
                    extra={
                        "response_length": len(assistant_text),
                        "subtype": conversational_subtype,
                    },
                )
                return "verbose_conversational_warning"  # Warning only
            return "pass"

        # rfq_specific: existing checks (unchanged)
        if intent == "rfq_specific":
            if not source_refs and not grounding_gap_injected:
                return "grounding_violation"
            return "pass"

        # disambiguation: existing checks (unchanged)
        if intent == "disambiguation":
            normalized = assistant_text.lower()
            if "?" not in assistant_text and "which" not in normalized and "rfq" not in normalized:
                return "disambiguation_shape_violation"
            return "pass"

        # unsupported: existing checks (unchanged)
        if intent == "unsupported":
            if (
                capability_status_hit is not None
                and capability_status_hit.capability_name not in assistant_text
            ):
                return "unsupported_routing_violation"
            return "pass"

        return "pass"
