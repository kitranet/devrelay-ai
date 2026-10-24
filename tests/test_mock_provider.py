import asyncio
import pytest

from app.core.config import Settings
from app.core.errors import MissingCredentialsError
from app.models.inference import ChatMessage, InferenceRequest
from app.services.inference import build_inference_service
from app.services.mock_inference import MockModelProvider


def test_mock_provider_is_selected_explicitly_and_is_deterministic_without_credentials():
    service = build_inference_service(Settings(_env_file=None, inference_provider="mock", nebius_api_key=None))
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
    service = build_inference_service(Settings(
        _env_file=None, inference_provider="nebius", nebius_api_key=None,
        nebius_live_inference_enabled=True,
    ))
    request = InferenceRequest(messages=[ChatMessage(role="user", content="mock://health")])

    async def generate():
        with pytest.raises(MissingCredentialsError):
            await service.generate(request)

    asyncio.run(generate())


def test_default_provider_stays_mock_even_when_a_key_is_configured(monkeypatch):
    monkeypatch.delenv("INFERENCE_PROVIDER", raising=False)
    settings = Settings(nebius_api_key="unit-test-key", _env_file=None)
    service = build_inference_service(settings)
    assert settings.inference_provider == "mock"
    assert isinstance(service._provider, MockModelProvider)

    request = InferenceRequest(messages=[ChatMessage(role="user", content="mock://health")])
    response = asyncio.run(service.generate(request))
    assert response.provider == "mock" and response.is_mock is True


def test_planning_thinking_option_does_not_change_mock_output():
    service = build_inference_service(Settings(_env_file=None, inference_provider="mock", nebius_api_key=None))
    message = ChatMessage(role="user", content="mock://health")

    async def compare():
        normal = await service.generate(InferenceRequest(messages=[message]))
        flagged = await service.generate(InferenceRequest(messages=[message], disable_thinking=True))
        return normal, flagged

    normal, flagged = asyncio.run(compare())
    assert normal == flagged
