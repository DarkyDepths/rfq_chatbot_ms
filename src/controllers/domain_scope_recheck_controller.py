"""Fallback semantic recheck for unresolved knowledge-like turns."""

from __future__ import annotations

import re
from typing import Literal

from src.connectors.azure_openai_connector import AzureOpenAIConnector
from src.utils.errors import RateLimitError, UpstreamServiceError, UpstreamTimeoutError


DomainRecheckLabel = Literal[
    "definitely_relevant",
    "possibly_relevant",
    "not_relevant",
]


class DomainScopeRecheckController:
    """Runs a narrow classification-only semantic recheck."""

    valid_labels = (
        "definitely_relevant",
        "possibly_relevant",
        "not_relevant",
    )

    def __init__(self, azure_openai_connector: AzureOpenAIConnector):
        self.azure_openai_connector = azure_openai_connector

    def classify_domain_relevance(self, user_content: str) -> DomainRecheckLabel:
        try:
            completion = self.azure_openai_connector.create_chat_completion(
                self._build_messages(user_content)
            )
        except (RateLimitError, UpstreamServiceError, UpstreamTimeoutError):
            return "not_relevant"

        return self._parse_label(completion.assistant_text)

    @classmethod
    def _parse_label(cls, assistant_text: str) -> DomainRecheckLabel:
        normalized_text = assistant_text.strip().lower()
        matched_labels = [
            label
            for label in cls.valid_labels
            if re.search(rf"\b{re.escape(label)}\b", normalized_text)
        ]
        if len(matched_labels) != 1:
            return "not_relevant"
        return matched_labels[0]

    @staticmethod
    def _build_messages(user_content: str) -> list[dict[str, str]]:
        return [
            {
                "role": "system",
                "content": (
                    "Domain scope recheck mode: classification only.\n"
                    "You classify whether a user turn belongs to the allowed assistant domain.\n"
                    "Relevant domain: RFQ lifecycle, industrial estimation, fabrication, "
                    "procurement, compliance, EPC, and oil-and-gas or heavy-industry context.\n"
                    "Return exactly one lowercase label and nothing else:\n"
                    "- definitely_relevant\n"
                    "- possibly_relevant\n"
                    "- not_relevant"
                ),
            },
            {
                "role": "user",
                "content": f"User turn:\n{user_content}",
            },
        ]
