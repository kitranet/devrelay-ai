"""Deterministic, offline provider for tests and local development."""

from app.models.inference import ChatMessage, InferenceResponse

_SCENARIOS = {
    "mock://health": "MOCK RESPONSE: inference provider is ready.",
    "mock://repository-summary": "MOCK RESPONSE: repository analysis summary scenario.",
    "mock://handoff-summary": "MOCK RESPONSE: engineering handoff summary scenario.",
}


class MockModelProvider:
    async def complete(
        self, messages: list[ChatMessage], max_tokens: int = 1024
    ) -> InferenceResponse:
        del max_tokens  # Kept for protocol compatibility; mock outputs are fixed.
        scenario = next((message.content for message in reversed(messages) if message.role == "user"), "")
        content = _SCENARIOS.get(scenario, "MOCK RESPONSE: no matching inference scenario.")
        return InferenceResponse(
            model="devrelay-mock-v1",
            content=content,
            provider="mock",
            is_mock=True,
        )
