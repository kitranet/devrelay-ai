"""Evidence-backed engineering plan schemas."""

from typing import Literal

from pydantic import BaseModel, Field

from app.models.inference import InferenceDiagnostics
from app.models.repository import SourceExcerpt, SourceReference


class TaskPlanningRequest(BaseModel):
    repository_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
    task_description: str = Field(min_length=10, max_length=4_000)


class ExpectedCodeChange(BaseModel):
    path: str
    description: str = Field(min_length=1, max_length=500)


class PlanStep(BaseModel):
    step: int = Field(ge=1)
    description: str = Field(min_length=1, max_length=1_000)
    source_references: list[SourceReference] = Field(default_factory=list, max_length=20)


class PlanFinding(BaseModel):
    classification: Literal["observed", "suspected"]
    description: str = Field(min_length=1, max_length=500)
    source_references: list[SourceReference] = Field(default_factory=list, max_length=8)


class TaskPlan(BaseModel):
    task_id: str
    plan_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    repository_id: str
    task_description: str
    status: Literal["planned", "insufficient_context", "unsupported"]
    relevant_files: list[str] = Field(default_factory=list, max_length=50)
    source_references: list[SourceReference] = Field(default_factory=list, max_length=100)
    implementation_steps: list[PlanStep] = Field(default_factory=list, max_length=20)
    expected_code_changes: list[ExpectedCodeChange] = Field(default_factory=list, max_length=50)
    risks: list[str] = Field(default_factory=list, max_length=30)
    dependencies: list[str] = Field(default_factory=list, max_length=50)
    validation_requirements: list[str] = Field(default_factory=list, max_length=50)
    human_approval_required: bool = True
    execution_status: Literal["not_started"] = "not_started"
    assumptions: list[str] = Field(default_factory=list, max_length=30)
    unsupported_references: list[str] = Field(default_factory=list, max_length=50)
    source_excerpts: list[SourceExcerpt] = Field(default_factory=list, max_length=7)
    findings: list[PlanFinding] = Field(default_factory=list, max_length=6)
    unresolved_questions: list[str] = Field(default_factory=list, max_length=6)
    provider: Literal["nebius", "mock"]
    is_mock: bool
    inference_diagnostics: InferenceDiagnostics | None = None


class PlanGeneration(BaseModel):
    """Provider-authored plan payload, validated before API metadata is added."""

    status: Literal["planned", "insufficient_context", "unsupported"]
    relevant_files: list[str] = Field(max_length=5)
    source_references: list[SourceReference] = Field(max_length=5)
    implementation_steps: list[PlanStep] = Field(max_length=4)
    expected_code_changes: list[ExpectedCodeChange] = Field(max_length=5)
    risks: list[str] = Field(max_length=4)
    dependencies: list[str] = Field(max_length=4)
    validation_requirements: list[str] = Field(max_length=4)
    assumptions: list[str] = Field(max_length=3)
    findings: list[PlanFinding] = Field(default_factory=list, max_length=6)
    unresolved_questions: list[str] = Field(default_factory=list, max_length=6)
