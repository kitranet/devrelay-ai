"""Inference API schemas."""

from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(system|user|assistant)$")
    content: str = Field(min_length=1, max_length=100_000)


class InferenceRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=100)
    max_tokens: int = Field(default=1024, ge=1, le=8192)


class InferenceUsage(BaseModel):
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)


class InferenceResponse(BaseModel):
    model: str
    content: str
    provider: Literal["nebius", "mock"] = "nebius"
    is_mock: bool = False
    completion_status: Literal["completed", "incomplete"] = "completed"
    finish_reason: str | None = None
    model_reported_by_provider: bool = False
    latency_ms: int | None = Field(default=None, ge=0)
    usage: InferenceUsage | None = None


class InferenceDiagnostics(BaseModel):
    """Safe, non-content inference metadata suitable for API responses."""

    provider: Literal["nebius", "mock"]
    model: str
    is_mock: bool
    completion_status: Literal["completed"]
    finish_reason: str | None = None
    model_reported_by_provider: bool = False
    latency_ms: int | None = Field(default=None, ge=0)
    usage: InferenceUsage | None = None


def diagnostics_for(response: InferenceResponse) -> InferenceDiagnostics:
    return InferenceDiagnostics(
        provider=response.provider,
        model=response.model,
        is_mock=response.is_mock,
        completion_status="completed",
        finish_reason=response.finish_reason,
        model_reported_by_provider=response.model_reported_by_provider,
        latency_ms=response.latency_ms,
        usage=response.usage,
    )
