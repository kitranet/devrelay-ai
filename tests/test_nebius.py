import asyncio
import json

import httpx
import pytest

from app.core.config import Settings
from app.core.errors import (
    InferenceLimitError,
    LiveInferenceDisabledError,
    MalformedModelResponseError,
    MissingCredentialsError,
    ModelEmptyResponseError,
    ModelIncompleteResponseError,
    ModelProviderError,
    ModelTimeoutError,
)
from app.integrations.nebius import NebiusClient, estimate_prompt_tokens
from app.models.inference import ChatMessage


def _settings(**values):
    return Settings(_env_file=None, nebius_api_key="unit-test-key", inference_provider="nebius", **values)


def _response(*, content="{\"status\":\"unsupported\"}", finish_reason="stop", model="nvidia/Nemotron-3_5-Lightning", usage=None):
    return httpx.Response(200, json={
        "model": model,
        "choices": [{"message": {"content": content}, "finish_reason": finish_reason}],
        "usage": usage,
    })


def test_successful_response_uses_configured_endpoint_model_and_safe_metadata():
    async def run():
        seen = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            assert str(request.url) == "https://api.tokenfactory.nebius.com/v1/chat/completions"
            assert request.headers["Authorization"] == "Bearer unit-test-key"
            payload = json.loads(request.content)
            assert payload == {
                "model": "nvidia/Nemotron-3_5-Lightning",
                "messages": [{"role": "user", "content": "hello"}],
                "max_tokens": 1024,
            }
            return _response(usage={
                "prompt_tokens": 28,
                "completion_tokens": 128,
                "completion_tokens_details": {"reasoning_tokens": 64},
                "total_tokens": 156,
            })

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            result = await NebiusClient(_settings(), http_client).complete([ChatMessage(role="user", content="hello")])
        return result, seen

    result, seen = asyncio.run(run())
    assert len(seen) == 1
    assert result.provider == "nebius" and result.is_mock is False
    assert result.model == "nvidia/Nemotron-3_5-Lightning"
    assert result.model_reported_by_provider is True
    assert result.completion_status == "completed" and result.finish_reason == "stop"
    assert result.usage.model_dump() == {
        "input_tokens": 28, "output_tokens": 128, "reasoning_tokens": 64, "total_tokens": 156,
    }
    assert result.latency_ms is not None and result.latency_ms >= 0


def test_provider_default_does_not_make_paid_calls_and_missing_key_is_rejected(monkeypatch):
    monkeypatch.delenv("INFERENCE_PROVIDER", raising=False)
    async def run():
        client = NebiusClient(Settings(_env_file=None, nebius_api_key="unit-test-key"))
        assert client.settings.inference_provider == "mock"
        with pytest.raises(LiveInferenceDisabledError):
            await client.complete([ChatMessage(role="user", content="hello")])
        missing = NebiusClient(Settings(_env_file=None, inference_provider="nebius"))
        with pytest.raises(MissingCredentialsError):
            await missing.complete([ChatMessage(role="user", content="hello")])

    asyncio.run(run())


def test_truncated_response_is_rejected_without_exposing_partial_content(caplog):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: _response(
            content='{"secret partial answer":', finish_reason="length",
            usage={"prompt_tokens": 28, "completion_tokens": 128, "reasoning_tokens": 128, "total_tokens": 156},
        ))) as http_client:
            return await NebiusClient(_settings(), http_client).complete([ChatMessage(role="user", content="hello")])

    with pytest.raises(ModelIncompleteResponseError):
        asyncio.run(run())
    assert "secret partial answer" not in caplog.text
    assert "unit-test-key" not in caplog.text
    assert "reasoning_tokens=128" in caplog.text


@pytest.mark.parametrize("body", [
    {},
    {"choices": []},
    {"choices": [{"message": {"content": "ok"}}]},
    {"choices": [{"message": {"content": "ok"}, "finish_reason": None}]},
])
def test_missing_or_malformed_provider_fields_are_sanitized(body):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body))) as http_client:
            await NebiusClient(_settings(), http_client).complete([ChatMessage(role="user", content="hello")])

    with pytest.raises(MalformedModelResponseError):
        asyncio.run(run())


def test_empty_response_is_distinct_and_null_usage_is_safe():
    async def run_empty():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: _response(content="   "))) as http_client:
            await NebiusClient(_settings(), http_client).complete([ChatMessage(role="user", content="hello")])

    async def run_null_usage():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: _response(model="unit-test-key", usage=None))) as http_client:
            return await NebiusClient(_settings(), http_client).complete([ChatMessage(role="user", content="hello")])

    with pytest.raises(ModelEmptyResponseError):
        asyncio.run(run_empty())
    response = asyncio.run(run_null_usage())
    assert response.usage is None
    assert response.model == "nvidia/Nemotron-3_5-Lightning"
    assert response.model_reported_by_provider is False


def test_provider_echo_of_key_is_never_returned_or_logged(caplog):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: _response(
            content='{"status":"planned","risks":["unit-test-key"]}',
        ))) as http_client:
            await NebiusClient(_settings(), http_client).complete([ChatMessage(role="user", content="hello")])

    with pytest.raises(MalformedModelResponseError):
        asyncio.run(run())
    assert "unit-test-key" not in caplog.text


def test_credential_like_configured_model_is_rejected_before_request_or_logging(caplog):
    async def run():
        sent = False

        def handler(_: httpx.Request) -> httpx.Response:
            nonlocal sent
            sent = True
            return _response()

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = NebiusClient(_settings(nebius_model="unit-test-key"), http_client)
            with pytest.raises(ModelProviderError, match="model identifier is invalid"):
                await client.complete([ChatMessage(role="user", content="hello")])
        assert not sent

    asyncio.run(run())
    assert "unit-test-key" not in caplog.text


def test_tagged_internal_reasoning_is_rejected_and_not_returned(caplog):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: _response(
            content='{"status":"unsupported","risks":["<think>private internal reasoning</think>"]}',
        ))) as http_client:
            await NebiusClient(_settings(), http_client).complete([ChatMessage(role="user", content="hello")])

    with pytest.raises(MalformedModelResponseError):
        asyncio.run(run())
    assert "private internal reasoning" not in caplog.text


def test_timeout_and_http_error_are_distinct_and_never_retry(caplog):
    async def run_timeout():
        count = 0

        def handler(_: httpx.Request) -> httpx.Response:
            nonlocal count
            count += 1
            raise httpx.ReadTimeout("unit timeout")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            with pytest.raises(ModelTimeoutError):
                await NebiusClient(_settings(), http_client).complete([ChatMessage(role="user", content="hello")])
        assert count == 1

    async def run_http_error():
        count = 0

        def handler(_: httpx.Request) -> httpx.Response:
            nonlocal count
            count += 1
            return httpx.Response(429, text="provider body unit-test-key must not escape")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            with pytest.raises(ModelProviderError, match="HTTP 429") as error:
                await NebiusClient(_settings(), http_client).complete([ChatMessage(role="user", content="hello")])
        assert count == 1
        assert "provider body" not in str(error.value)
        assert "unit-test-key" not in str(error.value)
        assert "unit-test-key" not in caplog.text

    asyncio.run(run_timeout())
    asyncio.run(run_http_error())


def test_prompt_output_and_in_flight_limits_reject_before_sending():
    async def run():
        count = 0

        def handler(_: httpx.Request) -> httpx.Response:
            nonlocal count
            count += 1
            return _response()

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = NebiusClient(_settings(nebius_max_prompt_tokens=256), http_client)
            large = [ChatMessage(role="user", content="x" * 2_000)]
            assert estimate_prompt_tokens(large, client.settings.nebius_model) > 256
            with pytest.raises(InferenceLimitError, match="prompt"):
                await client.complete(large)
            with pytest.raises(InferenceLimitError, match="output"):
                await client.complete([ChatMessage(role="user", content="hello")], max_tokens=1025)
            assert client._in_flight.acquire(blocking=False)
            try:
                with pytest.raises(InferenceLimitError, match="in flight"):
                    await client.complete([ChatMessage(role="user", content="hello")])
            finally:
                client._in_flight.release()
        assert count == 0

    asyncio.run(run())


def test_unexpected_finish_reason_is_not_accepted():
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: _response(finish_reason="content_filter"))) as http_client:
            await NebiusClient(_settings(), http_client).complete([ChatMessage(role="user", content="hello")])

    with pytest.raises(ModelProviderError, match="successfully completed"):
        asyncio.run(run())
