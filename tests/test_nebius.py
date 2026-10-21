import asyncio
import json
import httpx
import pytest

from app.core.config import Settings
from app.core.errors import MissingCredentialsError, ModelProviderError, ModelTimeoutError
from app.integrations.nebius import NebiusClient
from app.models.inference import ChatMessage


def test_successful_mocked_inference():
    async def run():
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path.endswith("/chat/completions")
            assert request.headers["Authorization"] == "Bearer unit-test-key"
            body = json.loads(request.content)
            assert body["model"] == "nvidia/nemotron-3-super-120b-a12b"
            assert body["messages"] == [{"role": "user", "content": "hello"}]
            return httpx.Response(200, json={"model": body["model"], "choices": [{"message": {"content": "hi"}}]})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = NebiusClient(Settings(nebius_api_key="unit-test-key"), http_client=http_client)
            return await client.complete([ChatMessage(role="user", content="hello")])

    result = asyncio.run(run())
    assert result.content == "hi"


def test_missing_credentials_does_not_send_request():
    async def run():
        client = NebiusClient(Settings())
        with pytest.raises(MissingCredentialsError):
            await client.complete([ChatMessage(role="user", content="hello")])

    asyncio.run(run())


def test_timeout_maps_to_domain_error():
    async def run():
        def handler(_: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("slow")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = NebiusClient(Settings(nebius_api_key="unit-test-key"), http_client=http_client)
            with pytest.raises(ModelTimeoutError):
                await client.complete([ChatMessage(role="user", content="hello")])

    asyncio.run(run())


def test_provider_error_maps_without_leaking_response():
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(429, text="private detail"))) as http_client:
            client = NebiusClient(Settings(nebius_api_key="unit-test-key"), http_client=http_client)
            with pytest.raises(ModelProviderError, match="HTTP 429") as error:
                await client.complete([ChatMessage(role="user", content="hello")])
        assert "private detail" not in str(error.value)

    asyncio.run(run())
