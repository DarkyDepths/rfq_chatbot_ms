"""Thin Azure OpenAI chat-completions connector for Phase 3."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from openai import APIError, APITimeoutError, AzureOpenAI
from openai import RateLimitError as OpenAIRateLimitError

from src.config.settings import get_settings
from src.utils.errors import (
    RateLimitError,
    UpstreamServiceError,
    UpstreamTimeoutError,
)


@dataclass
class ChatCompletionResult:
    """Minimal typed result returned by the connector."""

    assistant_text: str


class AzureOpenAIConnector:
    """Sync Azure OpenAI chat-completions wrapper with thin retry handling."""

    max_rate_limit_retries = 2
    base_backoff_seconds = 0.5

    def __init__(
        self,
        client: AzureOpenAI | None = None,
        *,
        sleep_fn: Callable[[float], None] = time.sleep,
        deployment_name: str | None = None,
        timeout_seconds: float | None = None,
    ):
        settings = get_settings()

        self._client = client
        self._sleep_fn = sleep_fn
        self._deployment_name = deployment_name or settings.AZURE_OPENAI_CHAT_DEPLOYMENT
        self._timeout_seconds = timeout_seconds or settings.AZURE_OPENAI_TIMEOUT_SECONDS
        self._api_key = settings.AZURE_OPENAI_API_KEY
        self._api_version = settings.AZURE_OPENAI_API_VERSION
        self._endpoint = settings.AZURE_OPENAI_ENDPOINT

    def create_chat_completion(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatCompletionResult:
        """Generate one assistant message from the final prompt messages."""

        for attempt in range(self.max_rate_limit_retries + 1):
            try:
                payload: dict[str, Any] = {
                    "model": self._deployment_name,
                    "messages": messages,
                    "timeout": self._timeout_seconds,
                }
                if tools:
                    payload["tools"] = tools

                response = self._get_client().chat.completions.create(**payload)
            except OpenAIRateLimitError as exc:
                if attempt == self.max_rate_limit_retries:
                    raise RateLimitError(
                        "Azure OpenAI rate limit exceeded after retries"
                    ) from exc
                self._sleep_fn(self.base_backoff_seconds * (2**attempt))
            except APITimeoutError as exc:
                raise UpstreamTimeoutError("Azure OpenAI request timed out") from exc
            except APIError as exc:
                raise UpstreamServiceError("Azure OpenAI request failed") from exc
            else:
                assistant_text = (response.choices[0].message.content or "").strip()
                if not assistant_text:
                    raise UpstreamServiceError(
                        "Azure OpenAI returned an empty assistant response"
                    )

                return ChatCompletionResult(assistant_text=assistant_text)

        raise RateLimitError("Azure OpenAI rate limit exceeded after retries")

    def _get_client(self) -> AzureOpenAI:
        if self._client is None:
            if not self._endpoint or not self._api_key or not self._deployment_name:
                raise UpstreamServiceError(
                    "Azure OpenAI is not configured for chat completions"
                )

            self._client = AzureOpenAI(
                api_key=self._api_key,
                api_version=self._api_version,
                azure_endpoint=self._endpoint,
                timeout=self._timeout_seconds,
                max_retries=0,
            )

        return self._client
