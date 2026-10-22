"""Scoped local authorization, sandbox readiness, and runtime evidence schemas."""

import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


RuntimeValidationStatus = Literal[
    "authorized", "running", "passed", "failed", "timed_out", "sandbox_unavailable"
]
RuntimeTestCase = Literal["calculator_unit_tests"]
RUNTIME_TEST_COMMAND_ID = "calculator_pytest_suite_v1"
_LABEL_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_SECRET_LIKE = re.compile(
    r"(?i)(?:-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"(?:api[_-]?key|access[_-]?token|password|secret)\s*[:=]\s*\S+|"
    r"nvapi-[A-Za-z0-9_-]{16,}|sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,})"
)


class SandboxReadinessCheck(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    status: Literal["passed", "failed", "not_checked"]
    detail: str = Field(min_length=1, max_length=300)


class SandboxReadiness(BaseModel):
    enabled: bool
    environment: str
    available: bool
    status: Literal["disabled", "ready", "sandbox_unavailable"]
    test_case: RuntimeTestCase = "calculator_unit_tests"
    test_command_id: str = RUNTIME_TEST_COMMAND_ID
    checks: list[SandboxReadinessCheck] = Field(max_length=12)
    limitations: list[str] = Field(max_length=12)


class ExecutionAuthorization(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authorizer_identifier: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    purpose: str = Field(min_length=10, max_length=300)

    @field_validator("authorizer_identifier")
    @classmethod
    def reject_credential_like_identity(cls, value: str) -> str:
        if _SECRET_LIKE.search(value):
            raise ValueError("Execution authorizer labels cannot contain credential-like values.")
        return value

    @field_validator("purpose")
    @classmethod
    def normalize_purpose(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 10:
            raise ValueError("Execution authorization purpose must contain at least 10 non-space characters.")
        if _SECRET_LIKE.search(normalized):
            raise ValueError("Execution authorization purpose cannot contain credential-like values.")
        return normalized


class RuntimeValidationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: UUID
    proposal_version: int = Field(ge=1)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    diff_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    test_case: RuntimeTestCase
    authorization: ExecutionAuthorization


class RuntimeValidationEvidence(BaseModel):
    evidence_id: UUID
    proposal_id: UUID
    repository_id: str
    status: RuntimeValidationStatus
    requested_at: datetime
    completed_at: datetime | None = None
    proposal_version: int = Field(ge=1)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    diff_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    test_case: RuntimeTestCase
    test_command_id: str = RUNTIME_TEST_COMMAND_ID
    authorizer_identifier: str
    authorizer_identity_status: Literal["unverified_local_development"] = "unverified_local_development"
    authorization_purpose: str = Field(min_length=10, max_length=300)
    sandbox_summary: str = Field(min_length=1, max_length=500)
    readiness_checks: list[SandboxReadinessCheck] = Field(max_length=12)
    exit_code: int | None = None
    duration_ms: int | None = Field(default=None, ge=0, le=600_000)
    stdout: str = Field(default="", max_length=8_192)
    stderr: str = Field(default="", max_length=8_192)
    test_results: list[str] = Field(default_factory=list, max_length=100)
    failure_reason: str | None = Field(default=None, max_length=500)
    original_repository_modified: Literal[False] = False
    code_applied_to_original: Literal[False] = False


class SandboxExecutionResult(BaseModel):
    """Internal executor response. Production code only has a fail-closed executor today."""

    status: Literal["passed", "failed", "timed_out", "sandbox_unavailable"]
    exit_code: int | None = None
    duration_ms: int | None = Field(default=None, ge=0, le=600_000)
    stdout: str = ""
    stderr: str = ""
    test_results: list[str] = Field(default_factory=list, max_length=100)
    failure_reason: str | None = Field(default=None, max_length=500)
    sandbox_summary: str = Field(default="Isolated sandbox unavailable.", max_length=500)
