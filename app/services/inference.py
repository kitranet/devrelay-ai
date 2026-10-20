"""Application service coordinating validated inference requests."""

from app.integrations.nebius import NebiusClient
from app.models.inference import InferenceRequest, InferenceResponse


class InferenceService:
    def __init__(self, model_client: NebiusClient) -> None:
        self._model_client = model_client

    async def generate(self, request: InferenceRequest) -> InferenceResponse:
        return await self._model_client.complete(request.messages, max_tokens=request.max_tokens)
