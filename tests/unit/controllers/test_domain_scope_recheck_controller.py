from src.connectors.azure_openai_connector import ChatCompletionResult
from src.controllers.domain_scope_recheck_controller import DomainScopeRecheckController
from src.utils.errors import UpstreamServiceError, UpstreamTimeoutError


class FakeAzureConnector:
    def __init__(self, assistant_text: str = "not_relevant", error: Exception | None = None):
        self.assistant_text = assistant_text
        self.error = error
        self.calls: list[dict] = []

    def create_chat_completion(self, messages, tools=None):
        self.calls.append({"messages": messages, "tools": tools})
        if self.error is not None:
            raise self.error
        return ChatCompletionResult(assistant_text=self.assistant_text)


def test_recheck_controller_parses_valid_label():
    connector = FakeAzureConnector(assistant_text="definitely_relevant")
    controller = DomainScopeRecheckController(azure_openai_connector=connector)

    result = controller.classify_domain_relevance("what does brown field mean?")

    assert result == "definitely_relevant"
    assert len(connector.calls) == 1


def test_recheck_controller_invalid_output_fails_closed():
    connector = FakeAzureConnector(assistant_text="This seems relevant")
    controller = DomainScopeRecheckController(azure_openai_connector=connector)

    result = controller.classify_domain_relevance("what does brown field mean?")

    assert result == "not_relevant"


def test_recheck_controller_timeout_fails_closed():
    connector = FakeAzureConnector(error=UpstreamTimeoutError("timeout"))
    controller = DomainScopeRecheckController(azure_openai_connector=connector)

    result = controller.classify_domain_relevance("what does brown field mean?")

    assert result == "not_relevant"


def test_recheck_controller_service_error_fails_closed():
    connector = FakeAzureConnector(error=UpstreamServiceError("down"))
    controller = DomainScopeRecheckController(azure_openai_connector=connector)

    result = controller.classify_domain_relevance("what does brown field mean?")

    assert result == "not_relevant"
