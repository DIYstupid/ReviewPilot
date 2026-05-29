from reviewpilot.analyzer.llm import (
    ChatCompletionClient,
    ChatMessage,
    LLMConfigurationError,
    LLMRequest,
    request_cache_key,
)


def test_request_cache_key_is_stable_for_identical_requests() -> None:
    request = LLMRequest(
        model="deepseek-chat",
        messages=[ChatMessage(role="user", content="review this")],
        temperature=0.2,
    )

    assert request_cache_key("deepseek", request) == request_cache_key("deepseek", request)


def test_request_cache_key_changes_when_message_changes() -> None:
    first = LLMRequest(model="deepseek-chat", messages=[ChatMessage(role="user", content="a")])
    second = LLMRequest(model="deepseek-chat", messages=[ChatMessage(role="user", content="b")])

    assert request_cache_key("deepseek", first) != request_cache_key("deepseek", second)


def test_chat_client_requires_api_key() -> None:
    try:
        ChatCompletionClient(api_key="", base_url="https://api.example.com", provider="deepseek")
    except LLMConfigurationError as exc:
        assert "deepseek" in str(exc)
    else:
        raise AssertionError("Expected missing API key to fail fast")
