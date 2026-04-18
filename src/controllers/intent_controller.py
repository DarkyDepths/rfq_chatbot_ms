"""Intent classification controller for Phase 6 deterministic routing."""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.config.disambiguation_config import (
    DISAMBIGUATION_DETECTION_PATTERNS,
    MAX_RESOLUTION_WORD_COUNT,
    RFQ_REFERENCE_PATTERNS,
)
from src.config.intent_patterns import FALLBACK_INTENT, INTENT_PATTERNS
from src.models.session import ChatbotSession, SessionMode


@dataclass(frozen=True)
class IntentClassification:
    """Deterministic intent decision result for one turn."""

    intent: str
    disambiguation_resolved: bool
    resolved_rfq_reference: str | None
    disambiguation_abandoned: bool


class IntentController:
    """Classifies user turns using deterministic patterns and session context."""

    def classify_intent(
        self,
        user_content: str,
        session: ChatbotSession,
        last_assistant_content: str | None,
    ) -> IntentClassification:
        """Classify one user turn into the frozen 5-intent taxonomy."""

        normalized_content = self._normalize(user_content)

        if self._is_phase5_legacy_rfq_greeting(normalized_content, session):
            return IntentClassification(
                intent="rfq_specific",
                disambiguation_resolved=False,
                resolved_rfq_reference=None,
                disambiguation_abandoned=False,
            )

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
                abandoned = classified_intent in {"conversational", "general_knowledge"}
                return IntentClassification(
                    intent=classified_intent,
                    disambiguation_resolved=False,
                    resolved_rfq_reference=None,
                    disambiguation_abandoned=abandoned,
                )

            classified_intent = self._classify_normal(
                normalized_content=normalized_content,
                session=session,
            )
            return IntentClassification(
                intent=classified_intent,
                disambiguation_resolved=False,
                resolved_rfq_reference=None,
                disambiguation_abandoned=True,
            )

        classified_intent = self._classify_normal(
            normalized_content=normalized_content,
            session=session,
        )
        return IntentClassification(
            intent=classified_intent,
            disambiguation_resolved=False,
            resolved_rfq_reference=None,
            disambiguation_abandoned=False,
        )

    def _classify_normal(
        self,
        *,
        normalized_content: str,
        session: ChatbotSession,
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
            intent="general_knowledge",
        ):
            return "general_knowledge"

        return FALLBACK_INTENT

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

    def _is_phase5_legacy_rfq_greeting(
        self,
        normalized_content: str,
        session: ChatbotSession,
    ) -> bool:
        # Retained intentionally to preserve approved Phase 5 regression safety.
        return (
            normalized_content == "hello copilot"
            and self._session_mode_value(session) == SessionMode.RFQ_BOUND.value
        )
