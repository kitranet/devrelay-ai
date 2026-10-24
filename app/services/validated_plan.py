"""Server-side integrity and current-source checks for stored validated plans."""

from uuid import UUID

from app.core.errors import TaskPlanNotFoundError, TaskPlanSourceConflictError
from app.services.proposal_store import InMemoryTaskPlanStore, StoredTaskPlan
from app.services.repository_analysis import RepositoryScanner
from app.models.repository import RepositoryAnalysisResponse
from app.models.repository import SourceReference
from app.models.task import TaskPlan


def plan_evidence_references(plan: TaskPlan, limit: int = 20) -> list[SourceReference]:
    candidates = [
        *plan.source_references,
        *(reference for finding in plan.findings for reference in finding.source_references),
    ]
    unique = []
    seen = set()
    for reference in candidates:
        key = (reference.path, reference.line, reference.end_line)
        if key not in seen:
            unique.append(reference)
            seen.add(key)
        if len(unique) >= limit:
            break
    return unique


def load_current_validated_plan(
    task_id: UUID,
    plans: InMemoryTaskPlanStore,
    scanner: RepositoryScanner,
) -> tuple[StoredTaskPlan, RepositoryAnalysisResponse]:
    stored = plans.get(str(task_id))
    if stored is None:
        raise TaskPlanNotFoundError()
    plan = stored.plan
    if (
        stored.plan_digest != plans.digest_plan(plan)
        or plan.plan_sha256 != stored.plan_digest
        or plan.status != "planned"
        or not plan.human_approval_required
        or plan.execution_status != "not_started"
        or plan.unsupported_references
        or plan.repository_id == ""
        or plan.is_mock != stored.validated_is_mock
        or plan.provider != stored.validated_provider
        or any(
            path not in stored.source_hashes
            for path in (
                set(plan.relevant_files)
                | {reference.path for reference in plan.source_references}
                | {reference.path for finding in plan.findings for reference in finding.source_references}
                | {excerpt.path for excerpt in plan.source_excerpts}
            )
        )
    ):
        raise TaskPlanNotFoundError()
    diagnostics = plan.inference_diagnostics
    if plan.provider == "mock":
        if not plan.is_mock or not diagnostics or diagnostics.provider != "mock" or not diagnostics.is_mock:
            raise TaskPlanNotFoundError()
    elif (
        plan.is_mock or not diagnostics or diagnostics.provider != "nebius"
        or not stored.provider_model_verified or not diagnostics.model_reported_by_provider
        or diagnostics.model != stored.validated_model
    ):
        raise TaskPlanNotFoundError()
    analysis = scanner.analyze(plan.repository_id)
    if analysis.snapshot_id != stored.analysis_snapshot_id:
        raise TaskPlanSourceConflictError()
    if any(analysis.content_hashes.get(path) != digest for path, digest in stored.source_hashes.items()):
        raise TaskPlanSourceConflictError()
    return stored, analysis
