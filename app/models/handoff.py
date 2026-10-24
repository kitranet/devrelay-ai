"""Structured, evidence-grounded engineering handoff report schemas."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.proposal import ProposalTargetFile, ProposalValidationFinding
from app.models.repository import RepositoryModule, RepositorySummary, SourceReference
from app.models.review import PlanReviewRecord, PlanReviewState, ReviewRecord
from app.models.runtime_validation import RuntimeValidationStatus
from app.models.task import PlanFinding, PlanStep


class HandoffTaskContext(BaseModel):
    task_id: str
    objective: str
    current_progress: str
    task_status: str
    planning_provider: Literal["nebius", "mock"]
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
    originating_plan_provider: Literal["nebius", "mock"]
    transformation_id: Literal["calculator-zero-denominator-value-error-v1"]
    source_revision_status: Literal["current", "stale"]


class HandoffValidationRisk(BaseModel):
    static_checks: list[ProposalValidationFinding]
    runtime_tests_status: RuntimeValidationStatus | Literal["not_run"]
    runtime_tests_reason: str
    risks: list[str]
    assumptions: list[str]
    unresolved_dependencies: list[str]
    unsupported_evidence: list[str]


class HandoffRuntimeExecution(BaseModel):
    status: RuntimeValidationStatus | Literal["not_run"] = "not_run"
    sandbox_summary: str
    evidence_id: UUID | None = None
    test_case: str = "calculator_unit_tests"
    test_command_id: str = "calculator_pytest_suite_v1"
    exit_code: int | None = None
    duration_ms: int | None = Field(default=None, ge=0, le=600_000)
    test_results: list[str]
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    diff_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    remaining_work: list[str]


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
    runtime_execution: HandoffRuntimeExecution
    next_engineer_actions: list[HandoffNextAction]
    provenance_note: str = Field(min_length=1, max_length=500)
    provider: Literal["mock"]
    is_mock: Literal[True]


class PlanHandoffReportRequest(BaseModel):
    task_id: UUID


class PlanHandoffEvidence(BaseModel):
    path: str
    line: int = Field(ge=1)
    end_line: int | None = Field(default=None, ge=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class PlanOnlyHandoffReport(BaseModel):
    handoff_type: Literal["plan_only"] = "plan_only"
    report_id: UUID
    generated_at: datetime
    repository_id: str
    task_id: str
    objective: str
    plan_status: Literal["planned"]
    planning_provider: Literal["nebius", "mock"]
    planning_is_mock: bool
    planning_model: str | None = None
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    analysis_snapshot_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence: list[PlanHandoffEvidence] = Field(max_length=20)
    findings: list[PlanFinding] = Field(max_length=6)
    unresolved_questions: list[str] = Field(max_length=6)
    proposed_next_steps: list[PlanStep] = Field(max_length=4)
    validation_requirements: list[str] = Field(max_length=4)
    risks: list[str] = Field(max_length=4)
    assumptions: list[str] = Field(max_length=3)
    dependencies: list[str] = Field(max_length=4)
    review_state: PlanReviewState
    human_decisions: list[PlanReviewRecord] = Field(max_length=1)
    human_approval_required: Literal[True] = True
    execution_status: Literal["not_started"] = "not_started"
    runtime_validation_status: Literal["not_run"] = "not_run"
    provenance_note: str = Field(min_length=1, max_length=500)
