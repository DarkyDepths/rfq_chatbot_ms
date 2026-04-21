"""Intent classification controller for Phase 6 deterministic routing."""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.config.disambiguation_config import (
    DISAMBIGUATION_DETECTION_PATTERNS,
    MAX_RESOLUTION_WORD_COUNT,
    RFQ_REFERENCE_PATTERNS,
)
from src.config.intent_patterns import (
    FALLBACK_INTENT,
    INTENT_PATTERNS,
    classify_conversational_subtype,
    message_contains_off_domain_indicator,
    message_contains_domain_term,
)
from src.models.session import ChatbotSession, SessionMode


@dataclass(frozen=True)
class IntentClassification:
    """Deterministic intent decision result for one turn."""

    intent: str
    disambiguation_resolved: bool
    resolved_rfq_reference: str | None
    disambiguation_abandoned: bool
    conversational_subtype: str | None = None


class IntentController:
    """Classifies user turns using deterministic patterns and session context."""

    continuity_max_word_count = 6
    continuity_follow_up_cues = (
        "and",
        "also",
        "what about",
        "how about",
        "this",
        "that",
        "it",
        "its",
        "same",
        "then",
        "next",
    )

    def classify_intent(
        self,
        user_content: str,
        session: ChatbotSession,
        last_assistant_content: str | None,
        last_resolved_intent: str | None = None,
    ) -> IntentClassification:
        """Classify one user turn into the frozen intent taxonomy."""

        normalized_content = self._normalize(user_content)

        if self._is_disambiguation_prompt(last_assistant_content):
            if self._word_count(user_content) <= MAX_RESOLUTION_WORD_COUNT:
                resolved_reference = self._extract_rfq_reference(user_content)
                if resolved_reference is not None:
                    return IntentClassification(
                        intent="rfq_specific",
                        disambiguation_resolved=True,
                        resolved_rfq_reference=resolved_reference,
                        disambiguation_abandoned=False,
                    )

                classified_intent = self._classify_normal(
                    normalized_content=normalized_content,
                    session=session,
                )
                abandoned = classified_intent in {"conversational", "domain_knowledge"}
                subtype = None
                if classified_intent == "conversational":
                    subtype = classify_conversational_subtype(user_content)
                return IntentClassification(
                    intent=classified_intent,
                    disambiguation_resolved=False,
                    resolved_rfq_reference=None,
                    disambiguation_abandoned=abandoned,
                    conversational_subtype=subtype,
                )

            classified_intent = self._classify_normal(
                normalized_content=normalized_content,
                session=session,
            )
            subtype = None
            if classified_intent == "conversational":
                subtype = classify_conversational_subtype(user_content)
            return IntentClassification(
                intent=classified_intent,
                disambiguation_resolved=False,
                resolved_rfq_reference=None,
                disambiguation_abandoned=True,
                conversational_subtype=subtype,
            )

        classified_intent = self._classify_normal(
            normalized_content=normalized_content,
            session=session,
            last_resolved_intent=last_resolved_intent,
        )
        subtype = None
        if classified_intent == "conversational":
            subtype = classify_conversational_subtype(user_content)
        return IntentClassification(
            intent=classified_intent,
            disambiguation_resolved=False,
            resolved_rfq_reference=None,
            disambiguation_abandoned=False,
            conversational_subtype=subtype,
        )

    def _classify_normal(
        self,
        *,
        normalized_content: str,
        session: ChatbotSession,
        last_resolved_intent: str | None = None,
    ) -> str:
        if self._matches_intent(
            normalized_content=normalized_content,
            session=session,
            intent="unsupported",
        ):
            return "unsupported"

        if self._matches_disambiguation(
            normalized_content=normalized_content,
            session=session,
        ):
            return "disambiguation"

        if self._matches_intent(
            normalized_content=normalized_content,
            session=session,
            intent="rfq_specific",
        ):
            return "rfq_specific"

        if self._matches_intent(
            normalized_content=normalized_content,
            session=session,
            intent="domain_knowledge",
        ):
            # Domain gate: check if the message actually contains domain vocabulary
            if message_contains_domain_term(normalized_content):
                return "domain_knowledge"
            else:
                # Explanatory question but no domain vocabulary → out of scope
                return "out_of_scope"

        if message_contains_off_domain_indicator(normalized_content):
            return "out_of_scope"

        if self._should_apply_rfq_continuity_tiebreaker(
            normalized_content=normalized_content,
            user_content=normalized_content,
            session=session,
            last_resolved_intent=last_resolved_intent,
        ):
            return "rfq_specific"

        return FALLBACK_INTENT

    def _should_apply_rfq_continuity_tiebreaker(
        self,
        *,
        normalized_content: str,
        user_content: str,
        session: ChatbotSession,
        last_resolved_intent: str | None,
    ) -> bool:
        if last_resolved_intent != "rfq_specific":
            return False

        if self._session_mode_value(session) != SessionMode.RFQ_BOUND.value:
            return False

        if self._word_count(user_content) == 0:
            return False

        if self._word_count(user_content) > self.continuity_max_word_count:
            return False

        return any(
            cue in normalized_content for cue in self.continuity_follow_up_cues
        )

    def _matches_disambiguation(self, *, normalized_content: str, session: ChatbotSession) -> bool:
        if self._matches_intent(
            normalized_content=normalized_content,
            session=session,
            intent="disambiguation",
        ):
            return True

        # Domain-adjacent RFQ vocabulary (deadline, owner, status, etc.) scoped to
        # rfq_bound sessions would normally trigger rfq_specific. In a portfolio
        # session, the same vocabulary indicates the user is referencing an RFQ
        # we cannot identify, so treat as disambiguation instead.
        if self._session_mode_value(session) != SessionMode.PORTFOLIO.value:
            return False

        return any(
            self._keyword_matches(normalized_content, keyword)
            for keyword in self._keywords_for_intent_with_context(
                intent="rfq_specific",
                session_context=SessionMode.RFQ_BOUND.value,
            )
        )

    def _matches_intent(
        self,
        *,
        normalized_content: str,
        session: ChatbotSession,
        intent: str,
    ) -> bool:
        for pattern in INTENT_PATTERNS:
            if pattern["intent"] != intent:
                continue
            if not self._session_context_matches(pattern["session_context"], session):
                continue
            for keyword in pattern["keywords"]:
                if self._keyword_matches(normalized_content, keyword):
                    return True
        return False

    @staticmethod
    def _keywords_for_intent_with_context(*, intent: str, session_context: str) -> list[str]:
        keywords: list[str] = []
        for pattern in INTENT_PATTERNS:
            if pattern["intent"] != intent:
                continue
            if pattern["session_context"] != session_context:
                continue
            keywords.extend(pattern["keywords"])
        return keywords

    @staticmethod
    def _session_context_matches(session_context: str, session: ChatbotSession) -> bool:
        if session_context == "any":
            return True
        return IntentController._session_mode_value(session) == session_context

    @staticmethod
    def _session_mode_value(session: ChatbotSession) -> str:
        mode = session.mode
        if isinstance(mode, SessionMode):
            return mode.value
        return str(mode).strip().lower()

    @staticmethod
    def _normalize(value: str) -> str:
        return value.strip().lower()

    @staticmethod
    def _keyword_matches(content: str, keyword: str) -> bool:
        return bool(content) and keyword in content

    @staticmethod
    def _word_count(value: str) -> int:
        stripped = value.strip()
        if not stripped:
            return 0
        return len(stripped.split())

    @staticmethod
    def _is_disambiguation_prompt(last_assistant_content: str | None) -> bool:
        if not last_assistant_content:
            return False
        lowered = last_assistant_content.strip().lower()
        return any(pattern in lowered for pattern in DISAMBIGUATION_DETECTION_PATTERNS)

    @staticmethod
    def _extract_rfq_reference(user_content: str) -> str | None:
        for pattern in RFQ_REFERENCE_PATTERNS:
            match = re.search(pattern, user_content, flags=re.IGNORECASE)
            if match is not None:
                return match.group(0)
        return None
