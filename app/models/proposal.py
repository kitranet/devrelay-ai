"""Schemas for read-only, human-reviewed code-change proposals."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.repository import SourceReference


class CreateProposalRequest(BaseModel):
    repository_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
    task_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


class ProposalTargetFile(BaseModel):
    path: str = Field(min_length=1, max_length=300)
    original_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_reference: SourceReference


class ProposalValidationFinding(BaseModel):
    check: Literal[
        "authorized_scope",
        "source_revision",
        "patch_format",
        "change_size",
        "python_syntax",
        "acceptance_criterion",
        "runtime_isolation",
    ]
    status: Literal["passed", "failed", "not_run"]
    detail: str = Field(min_length=1, max_length=500)


class CodeChangeProposal(BaseModel):
    proposal_id: UUID
    repository_id: str
    originating_task_id: str
    task_description: str = Field(min_length=1, max_length=4_000)
    target_files: list[ProposalTargetFile] = Field(min_length=1, max_length=5)
    proposed_change_summary: str = Field(min_length=1, max_length=1_000)
    unified_diff: str = Field(min_length=1, max_length=16_384)
    risk_classification: Literal["low", "medium", "high"]
    validation_findings: list[ProposalValidationFinding] = Field(max_length=20)
    static_validation_status: Literal["passed", "failed"]
    runtime_validation_status: Literal["not_run"] = "not_run"
    runtime_validation_reason: str = Field(min_length=1, max_length=500)
    provider: Literal["mock"] = "mock"
    is_mock: Literal[True] = True
    created_at: datetime
    lifecycle_state: Literal[
        "proposed", "validated", "awaiting_review", "approved", "applied", "rejected"
    ]
    human_approval_required: Literal[True] = True


