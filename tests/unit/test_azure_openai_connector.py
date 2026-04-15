from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from openai import APIError, APITimeoutError
from openai import RateLimitError as OpenAIRateLimitError

from src.connectors.azure_openai_connector import AzureOpenAIConnector
from src.config.settings import get_settings
from src.utils.errors import RateLimitError, UpstreamServiceError, UpstreamTimeoutError


def _build_mock_client(side_effect):
    if isinstance(side_effect, list) or isinstance(side_effect, Exception):
        create = MagicMock(side_effect=side_effect)
    else:
        create = MagicMock(return_value=side_effect)
    return SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )


def test_azure_openai_connector_returns_assistant_text():
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="Hello from Azure"))]
    )
    connector = AzureOpenAIConnector(
        client=_build_mock_client(response),
        deployment_name="chat-deployment",
        timeout_seconds=3.0,
    )

    result = connector.create_chat_completion([{"role": "system", "content": "x"}])

    assert result.assistant_text == "Hello from Azure"


def test_azure_openai_connector_maps_timeout():
    request = httpx.Request("POST", "https://example.test")
    connector = AzureOpenAIConnector(
        client=_build_mock_client(APITimeoutError(request=request)),
        deployment_name="chat-deployment",
        timeout_seconds=3.0,
    )

    with pytest.raises(UpstreamTimeoutError) as exc:
        connector.create_chat_completion([{"role": "system", "content": "x"}])

    assert str(exc.value) == "Azure OpenAI request timed out"


def test_azure_openai_connector_retries_rate_limit_then_fails():
    request = httpx.Request("POST", "https://example.test")
    response = httpx.Response(429, request=request)
    error = OpenAIRateLimitError("rate limited", response=response, body=None)
    sleep_calls = []
    connector = AzureOpenAIConnector(
        client=_build_mock_client([error, error, error]),
        sleep_fn=sleep_calls.append,
        deployment_name="chat-deployment",
        timeout_seconds=3.0,
    )

    with pytest.raises(RateLimitError) as exc:
        connector.create_chat_completion([{"role": "system", "content": "x"}])

    assert str(exc.value) == "Azure OpenAI rate limit exceeded after retries"
    assert sleep_calls == [0.5, 1.0]


def test_azure_openai_connector_maps_generic_failure():
    request = httpx.Request("POST", "https://example.test")
    connector = AzureOpenAIConnector(
        client=_build_mock_client(APIError("boom", request=request, body=None)),
        deployment_name="chat-deployment",
        timeout_seconds=3.0,
    )

    with pytest.raises(UpstreamServiceError) as exc:
        connector.create_chat_completion([{"role": "system", "content": "x"}])

    assert str(exc.value) == "Azure OpenAI request failed"


def test_azure_openai_connector_requires_configuration(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "")
    monkeypatch.setenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "")
    get_settings.cache_clear()

    connector = AzureOpenAIConnector()

    with pytest.raises(UpstreamServiceError) as exc:
        connector.create_chat_completion([{"role": "system", "content": "x"}])

    assert str(exc.value) == "Azure OpenAI is not configured for chat completions"
    get_settings.cache_clear()


def test_azure_openai_connector_builds_azure_client_from_settings(monkeypatch):
    captured = {}
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="Hello from Azure"))]
    )

    def _fake_azure_openai(**kwargs):
        captured.update(kwargs)
        return _build_mock_client(response)

    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example-resource.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
    monkeypatch.setenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-5-nano")
    monkeypatch.setattr(
        "src.connectors.azure_openai_connector.AzureOpenAI",
        _fake_azure_openai,
    )
    get_settings.cache_clear()

    connector = AzureOpenAIConnector()
    result = connector.create_chat_completion([{"role": "system", "content": "x"}])

    assert result.assistant_text == "Hello from Azure"
    assert captured == {
        "api_key": "test-key",
        "api_version": "2024-12-01-preview",
        "azure_endpoint": "https://example-resource.openai.azure.com/",
        "timeout": 30.0,
        "max_retries": 0,
    }
    get_settings.cache_clear()
