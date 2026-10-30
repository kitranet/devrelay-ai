"""Inference API schemas."""

from typing import Literal

from pydantic import BaseModel, Field

PlanValidationFailureCategory = Literal[
    "provider_metadata_mismatch", "sensitive_content_rejected", "incomplete_response",
    "empty_model_content", "invalid_json_syntax", "incorrect_json_root_type",
    "schema_missing_required_field", "schema_incorrect_field_type", "schema_invalid_enum_value",
    "schema_excessive_item_count", "schema_validation_failed", "model_identity_unverified",
]


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(system|user|assistant)$")
    content: str = Field(min_length=1, max_length=100_000)


class InferenceRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=100)
    max_tokens: int = Field(default=1024, ge=1, le=8192)
    disable_thinking: bool = False
    json_mode: bool = False
    run_id: str | None = Field(default=None, pattern=r"^[0-9a-f-]{36}$")
    repository_id: str | None = Field(default=None, max_length=64)
    task_id: str | None = Field(default=None, pattern=r"^[0-9a-f-]{36}$")


class InferenceUsage(BaseModel):
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)


class InferenceResponse(BaseModel):
    run_id: str | None = None
    provider_http_status: int | None = Field(default=None, ge=100, le=599)
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
    run_id: str | None = None
    provider_http_status: int | None = Field(default=None, ge=100, le=599)
    model: str
    provider_reported_model: str | None = None
    is_mock: bool
    completion_status: Literal["completed"]
    finish_reason: str | None = None
    model_reported_by_provider: bool = False
    latency_ms: int | None = Field(default=None, ge=0)
    usage: InferenceUsage | None = None


class InferenceStatusResponse(BaseModel):
    provider: Literal["nebius", "mock"]
    live_inference_enabled: bool
    credentials_configured: bool
    quota_status: Literal["not_applicable", "available", "exhausted", "unavailable"]
    quota_total: int | None = Field(default=None, ge=0)
    quota_used: int | None = Field(default=None, ge=0)
    quota_remaining: int | None = Field(default=None, ge=0)


class InferenceAttemptRecordResponse(BaseModel):
    run_id: str
    timestamp: str
    repository_id: str
    task_id: str
    provider: Literal["nebius", "mock"]
    model: str
    provider_reported_model: str | None = None
    request_status: Literal["in_progress", "completed", "provider_error", "timeout", "cancelled", "blocked", "interrupted"]
    provider_http_status: int | None = None
    error_code: str | None = None
    started_at: str
    ended_at: str | None = None
    duration_ms: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    total_tokens: int | None = None
    finish_reason: str | None = None
    pricing_model: str | None = None
    price_per_million_input_tokens: str | None = None
    price_per_million_output_tokens: str | None = None
    estimated_cost_usd: str | None = None
    actual_billed_cost_usd: str | None = None
    billing_status: Literal["unavailable", "not_applicable"]
    pricing_source: str | None = None
    pricing_as_of: str | None = None
    pricing_registry_version: str | None = None
    citation_validation_status: Literal["not_run", "passed", "failed"]
    plan_validation_status: Literal["not_run", "passed", "failed"]
    plan_validation_failure_category: PlanValidationFailureCategory | None = None
    verified_reference_count: int | None = None
    unsupported_reference_count: int | None = None
    provider_usage_received: bool
    quota_reservation_status: Literal["not_required", "not_reserved", "reserved", "unknown"]


class InferenceAttemptHistoryResponse(BaseModel):
    records: list[InferenceAttemptRecordResponse]
    retention_days: int
    maximum_records: int
    billing_information: Literal["unavailable"] = "unavailable"


def diagnostics_for(response: InferenceResponse) -> InferenceDiagnostics:
    return InferenceDiagnostics(
        provider=response.provider,
        run_id=response.run_id,
        provider_http_status=response.provider_http_status,
        model=response.model,
        provider_reported_model=response.model if response.provider == "nebius" and response.model_reported_by_provider else None,
        is_mock=response.is_mock,
        completion_status="completed",
        finish_reason=response.finish_reason,
        model_reported_by_provider=response.model_reported_by_provider,
        latency_ms=response.latency_ms,
        usage=response.usage,
    )
