"""Inference API schemas."""

from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(system|user|assistant)$")
    content: str = Field(min_length=1, max_length=100_000)


class InferenceRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=100)
    max_tokens: int = Field(default=1024, ge=1, le=8192)


class InferenceResponse(BaseModel):
    model: str
    content: str
    provider: Literal["nebius", "mock"] = "nebius"
    is_mock: bool = False
