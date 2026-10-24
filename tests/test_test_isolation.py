"""Regression tests proving developer credentials cannot make test calls live."""

import asyncio

import httpx
import pytest

from app.core.config import get_settings
from app.models.inference import ChatMessage, InferenceRequest
from app.services.inference import build_inference_service
from app.services.mock_inference import MockModelProvider


def test_fake_api_key_alone_keeps_the_default_provider_mock(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "fake-production-key-for-test-only")
    monkeypatch.setenv("INFERENCE_PROVIDER", "mock")
    get_settings.cache_clear()

    settings = get_settings()
    service = build_inference_service(settings)

    assert settings.inference_provider == "mock"
    assert isinstance(service._provider, MockModelProvider)
    result = asyncio.run(service.generate(InferenceRequest(
        messages=[ChatMessage(role="user", content="mock://health")]
    )))
    assert result.provider == "mock" and result.is_mock is True


def test_nebius_environment_override_with_fake_key_is_blocked_and_not_retried(
    monkeypatch, caplog, tmp_path
):
    monkeypatch.setenv("INFERENCE_PROVIDER", "nebius")
    monkeypatch.setenv("NEBIUS_API_KEY", "fake-production-key-for-test-only")
    monkeypatch.setenv("NEBIUS_LIVE_INFERENCE_ENABLED", "true")
    monkeypatch.setenv("NEBIUS_TOTAL_INFERENCE_QUOTA", "1")
    monkeypatch.setenv("NEBIUS_QUOTA_DB_PATH", str(tmp_path / "quota.sqlite3"))
    get_settings.cache_clear()

    settings = get_settings()
    service = build_inference_service(settings)
    assert settings.inference_provider == "nebius"

    request_count = 0
    guarded_transport = httpx.AsyncHTTPTransport.handle_async_request

    async def count_guarded_request(transport, request):
        nonlocal request_count
        request_count += 1
        return await guarded_transport(transport, request)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", count_guarded_request)

    with pytest.raises(AssertionError, match="Pytest network safety guard") as error:
        asyncio.run(service.generate(InferenceRequest(
            messages=[ChatMessage(role="user", content="a test inference request")]
        )))

    assert request_count == 1
    assert "fake-production-key-for-test-only" not in str(error.value)
    assert "fake-production-key-for-test-only" not in caplog.text
