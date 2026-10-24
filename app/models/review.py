"""Local-only human review and non-durable audit schemas."""

from datetime import datetime
import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.models.proposal import ProposalValidationFinding
from app.models.repository import SourceReference


ReviewDecision = Literal["approve", "reject", "request_changes"]
ProposalReviewState = Literal["awaiting_review", "review_approved", "changes_requested", "rejected"]
_SECRET_LIKE = re.compile(
    r"(?i)(?:-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"(?:api[_-]?key|access[_-]?token|password|secret)\s*[:=]\s*\S+|"
    r"nvapi-[A-Za-z0-9_-]{16,}|sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,})"
)


class ReviewDecisionRequest(BaseModel):
    proposal_id: UUID
    decision: ReviewDecision
    reviewer_identifier: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    justification: str = Field(min_length=1, max_length=2_000)
    proposal_version: int = Field(ge=1)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    diff_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    outstanding_questions: list[str] = Field(default_factory=list, max_length=12)

    @field_validator("reviewer_identifier")
    @classmethod
    def reject_credential_like_reviewer_labels(cls, value: str) -> str:
        if _SECRET_LIKE.search(value):
            raise ValueError("Reviewer identifiers cannot contain credential-like values.")
        return value

    @field_validator("justification")
    @classmethod
    def require_non_whitespace_justification(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Review justification cannot be blank.")
        if _SECRET_LIKE.search(normalized):
            raise ValueError("Review justification cannot contain credential-like values.")
        return normalized

    @field_validator("outstanding_questions")
    @classmethod
    def normalize_questions(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized) or any(len(value) > 300 for value in normalized):
            raise ValueError("Outstanding questions must be non-empty and at most 300 characters.")
        if any(_SECRET_LIKE.search(value) for value in normalized):
            raise ValueError("Outstanding questions cannot contain credential-like values.")
        return normalized


class ReviewRecord(BaseModel):
    review_id: UUID
    proposal_id: UUID
    task_id: str
    repository_id: str
    decision: ReviewDecision
    reviewer_identifier: str
    reviewer_identity_status: Literal["unverified_local_development"] = "unverified_local_development"
    justification: str
    timestamp: datetime
    proposal_version: int = Field(ge=1)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    diff_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal_lifecycle_state: ProposalReviewState
    evidence_references: list[SourceReference] = Field(max_length=20)
    static_validation_status: Literal["passed", "failed"]
    runtime_validation_status: Literal["not_run"] = "not_run"
    outstanding_questions: list[str] = Field(max_length=12)


class AuditEvent(BaseModel):
    event_id: UUID
    timestamp: datetime
    event_type: Literal["review_decision_recorded", "review_submission_rejected"]
    outcome: Literal["accepted", "rejected"]
    proposal_id: UUID
    task_id: str
    reviewer_identifier: str
    reviewer_identity_status: Literal["unverified_local_development"] = "unverified_local_development"
    previous_state: str
    new_state: str
    decision: ReviewDecision | None
    justification: str = Field(max_length=2_000)
    source_sha256: str
    diff_sha256: str
    validation_evidence: list[ProposalValidationFinding]
    failure_reason: str | None = None


class ReviewHistoryResponse(BaseModel):
    proposal_id: UUID
    current_lifecycle_state: str
    current_proposal_version: int
    reviews: list[ReviewRecord]
    audit_events: list[AuditEvent]


class LocalReviewStatus(BaseModel):
    enabled: bool
    environment: str
    identity_status: Literal["unverified_local_development"] = "unverified_local_development"


PlanReviewDecision = Literal["acknowledge", "request_changes", "reject"]
PlanReviewState = Literal["awaiting_review", "reviewed", "changes_requested", "rejected"]


class PlanReviewDecisionRequest(BaseModel):
    task_id: UUID
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: PlanReviewDecision
    reviewer_identifier: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    justification: str = Field(min_length=1, max_length=2_000)
    unresolved_questions: list[str] = Field(default_factory=list, max_length=12)

    @field_validator("reviewer_identifier")
    @classmethod
    def reject_credential_like_reviewer_labels(cls, value: str) -> str:
        if _SECRET_LIKE.search(value):
            raise ValueError("Reviewer identifiers cannot contain credential-like values.")
        return value

    @field_validator("justification")
    @classmethod
    def require_non_whitespace_justification(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or _SECRET_LIKE.search(normalized):
            raise ValueError("Review justification is empty or contains credential-like values.")
        return normalized

    @field_validator("unresolved_questions")
    @classmethod
    def normalize_questions(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not item or len(item) > 300 or _SECRET_LIKE.search(item) for item in normalized):
            raise ValueError("Unresolved questions must be non-empty, bounded, and free of credential-like values.")
        return normalized


class PlanReviewRecord(BaseModel):
    review_id: UUID
    task_id: str
    repository_id: str
    decision: PlanReviewDecision
    review_state: Literal["reviewed", "changes_requested", "rejected"]
    reviewer_identifier: str
    reviewer_identity_status: Literal["unverified_local_development"] = "unverified_local_development"
    justification: str
    timestamp: datetime
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    analysis_snapshot_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_references: list[SourceReference] = Field(max_length=20)
    unresolved_questions: list[str] = Field(max_length=12)


class PlanReviewHistory(BaseModel):
    task_id: str
    review_state: PlanReviewState
    reviews: list[PlanReviewRecord]
