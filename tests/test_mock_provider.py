import asyncio
import pytest

from app.core.config import Settings
from app.core.errors import MissingCredentialsError
from app.models.inference import ChatMessage, InferenceRequest
from app.services.inference import build_inference_service


def test_mock_provider_is_selected_explicitly_and_is_deterministic_without_credentials():
    service = build_inference_service(Settings(inference_provider="mock"))
    request = InferenceRequest(messages=[ChatMessage(role="user", content="mock://handoff-summary")])

    async def generate_twice():
        return await service.generate(request), await service.generate(request)

    first, second = asyncio.run(generate_twice())
    assert first == second
    assert first.provider == "mock"
    assert first.is_mock is True
    assert first.model == "devrelay-mock-v1"
    assert first.content.startswith("MOCK RESPONSE:")


def test_nebius_failure_does_not_fall_back_to_mock():
    service = build_inference_service(Settings(inference_provider="nebius"))
    request = InferenceRequest(messages=[ChatMessage(role="user", content="mock://health")])

    async def generate():
        with pytest.raises(MissingCredentialsError):
            await service.generate(request)

    asyncio.run(generate())
