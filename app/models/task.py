"""Evidence-backed engineering plan schemas."""

from typing import Literal

from pydantic import BaseModel, Field

from app.models.inference import InferenceDiagnostics
from app.models.repository import SourceReference


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


class TaskPlan(BaseModel):
    task_id: str
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
    provider: Literal["nebius", "mock"]
    is_mock: bool
    inference_diagnostics: InferenceDiagnostics | None = None


class PlanGeneration(BaseModel):
    """Provider-authored plan payload, validated before API metadata is added."""

    status: Literal["planned", "insufficient_context", "unsupported"]
    relevant_files: list[str] = Field(default_factory=list, max_length=50)
    source_references: list[SourceReference] = Field(default_factory=list, max_length=100)
    implementation_steps: list[PlanStep] = Field(default_factory=list, max_length=20)
    expected_code_changes: list[ExpectedCodeChange] = Field(default_factory=list, max_length=50)
    risks: list[str] = Field(default_factory=list, max_length=30)
    dependencies: list[str] = Field(default_factory=list, max_length=50)
    validation_requirements: list[str] = Field(default_factory=list, max_length=50)
    assumptions: list[str] = Field(default_factory=list, max_length=30)
