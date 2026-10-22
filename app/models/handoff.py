"""Structured, evidence-grounded engineering handoff report schemas."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.proposal import ProposalTargetFile, ProposalValidationFinding
from app.models.repository import RepositoryModule, RepositorySummary, SourceReference
from app.models.review import ReviewRecord


class HandoffTaskContext(BaseModel):
    task_id: str
    objective: str
    current_progress: str
    task_status: str
    proposal_lifecycle_state: str
    proposal_version: int
    relevant_files: list[str]
    source_references: list[SourceReference]
    planned_steps: list[str]
    planned_validation_requirements: list[str]


class HandoffTechnicalUnderstanding(BaseModel):
    analysis_summary: RepositorySummary
    relevant_modules: list[RepositoryModule]
    relevant_functions: list[str]
    relevant_classes: list[str]
    relevant_imports: list[str]
    dependency_manifests: list[str]
    verified_context: list[str]
    analysis_warnings: list[str]


class HandoffReportRequest(BaseModel):
    proposal_id: UUID


class HandoffProposedChange(BaseModel):
    summary: str
    target_files: list[ProposalTargetFile]
    diff_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    static_validation_status: Literal["passed", "failed"]
    validation_findings: list[ProposalValidationFinding]
    provider: Literal["mock"]
    is_mock: Literal[True]
    source_revision_status: Literal["current", "stale"]


class HandoffValidationRisk(BaseModel):
    static_checks: list[ProposalValidationFinding]
    runtime_tests_status: Literal["not_run"]
    runtime_tests_reason: str
    risks: list[str]
    assumptions: list[str]
    unresolved_dependencies: list[str]
    unsupported_evidence: list[str]


class HandoffNextAction(BaseModel):
    action: str
    required_approval: bool
    status: Literal["pending"] = "pending"


class HandoffReport(BaseModel):
    report_id: UUID
    generated_at: datetime
    repository_id: str
    task: HandoffTaskContext
    technical_understanding: HandoffTechnicalUnderstanding
    proposed_change: HandoffProposedChange
    human_decisions: list[ReviewRecord]
    outstanding_questions: list[str]
    validation_and_risks: HandoffValidationRisk
    next_engineer_actions: list[HandoffNextAction]
    provenance_note: str = Field(min_length=1, max_length=500)
    provider: Literal["mock"]
    is_mock: Literal[True]
