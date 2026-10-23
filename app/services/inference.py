"""Application service and explicit provider selection for model inference."""

from typing import Protocol

from app.core.config import Settings
from app.integrations.nebius import NebiusClient
from app.models.inference import ChatMessage, InferenceRequest, InferenceResponse
from app.services.mock_inference import MockModelProvider


class InferenceProvider(Protocol):
    async def complete(
        self, messages: list[ChatMessage], max_tokens: int = 1024, *, disable_thinking: bool = False
    ) -> InferenceResponse: ...


class InferenceService:
    def __init__(self, provider: InferenceProvider) -> None:
        self._provider = provider

    async def generate(self, request: InferenceRequest) -> InferenceResponse:
        if request.disable_thinking:
            return await self._provider.complete(
                request.messages, max_tokens=request.max_tokens, disable_thinking=True
            )
        return await self._provider.complete(request.messages, max_tokens=request.max_tokens)


def build_inference_service(settings: Settings) -> InferenceService:
    """Select exactly one configured provider; provider failures never fall back."""
    if settings.inference_provider == "mock":
        return InferenceService(MockModelProvider())
    return InferenceService(NebiusClient(settings))
