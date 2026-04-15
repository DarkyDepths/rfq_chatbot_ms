from types import SimpleNamespace

from src.controllers.context_builder import ContextBuilder
from src.models.prompt import PromptEnvelope


def test_context_builder_returns_prompt_envelope():
    builder = ContextBuilder()

    prompt = builder.build(
        [
            SimpleNamespace(role="user", content="Hello"),
            SimpleNamespace(role="assistant", content="Hi there"),
        ]
    )

    assert isinstance(prompt, PromptEnvelope)
    assert prompt.total_budget == 4000
    assert prompt.stable_prefix == builder.system_prompt
    assert "user: Hello" in prompt.variable_suffix
    assert "assistant: Hi there" in prompt.variable_suffix


def test_context_builder_keeps_system_prompt_in_stable_prefix():
    builder = ContextBuilder()

    prompt = builder.build([SimpleNamespace(role="user", content="Need help")])

    assert prompt.stable_prefix == builder.system_prompt
    assert prompt.variable_suffix.splitlines()[0] == "Conversation history:"


def test_context_builder_includes_retrieved_facts_after_history():
    builder = ContextBuilder()

    prompt = builder.build(
        [SimpleNamespace(role="user", content="Need help")],
        ["Tool: get_rfq_profile\nValue:\n{\"owner\": \"Sarah\"}"],
    )

    assert "Retrieved facts:" in prompt.variable_suffix
    assert "Tool: get_rfq_profile" in prompt.variable_suffix
