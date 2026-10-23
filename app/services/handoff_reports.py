"""Generate traceable local handoff reports from stored structured evidence."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.core.config import Settings
from app.core.errors import HandoffReportNotFoundError, ProposalNotFoundError, ProposalSourceConflictError, TaskPlanNotFoundError
from app.models.handoff import (
    HandoffNextAction,
    HandoffProposedChange,
    HandoffReport,
    HandoffRuntimeExecution,
    HandoffTaskContext,
    HandoffTechnicalUnderstanding,
    HandoffValidationRisk,
)
from app.services.proposal_generation import verify_current_source_revision
from app.services.proposal_store import (
    InMemoryHandoffStore,
    InMemoryProposalStore,
    InMemoryReviewStore,
    InMemoryRuntimeValidationStore,
    InMemoryTaskPlanStore,
)
from app.services.repository_analysis import RepositoryScanner


class HandoffReportService:
    def __init__(
        self,
        scanner: RepositoryScanner,
        proposals: InMemoryProposalStore,
        plans: InMemoryTaskPlanStore,
        reviews: InMemoryReviewStore,
        runtime_validations: InMemoryRuntimeValidationStore,
        reports: InMemoryHandoffStore,
        settings: Settings,
    ) -> None:
        self.scanner = scanner
        self.proposals = proposals
        self.plans = plans
        self.reviews = reviews
        self.runtime_validations = runtime_validations
        self.reports = reports
        self.settings = settings

    def generate(self, proposal_id) -> HandoffReport:
        proposal = self.proposals.get(proposal_id)
        if proposal is None:
            raise ProposalNotFoundError()
        stored_plan = self.plans.get(proposal.originating_task_id)
        if stored_plan is None:
            raise TaskPlanNotFoundError()
        plan = stored_plan.plan
        if plan.repository_id != proposal.repository_id:
            raise ProposalNotFoundError()

        analysis = self.scanner.analyze(proposal.repository_id)
        relevant_paths = set(plan.relevant_files)
        relevant_functions = [
            f"{item.qualified_name} ({item.source.path}:{item.source.line})"
            for item in analysis.functions if item.source.path in relevant_paths
        ]
        relevant_classes = [
            f"{item.qualified_name} ({item.source.path}:{item.source.line})"
            for item in analysis.classes if item.source.path in relevant_paths
        ]
        relevant_imports = [
            f"{item.source_path}:{item.line} imports {item.imported_module}"
            for item in analysis.imports if item.source_path in relevant_paths
        ]
        dependency_manifests = [
            f"{manifest.path}: {', '.join(manifest.dependencies) if manifest.dependencies else 'no dependencies listed'}"
            for manifest in analysis.dependency_manifests
        ]
        current_revision = True
        try:
            verify_current_source_revision(self.settings, proposal)
        except ProposalSourceConflictError:
            current_revision = False

        history = self.reviews.history(proposal_id)
        runtime = self.runtime_validations.latest_for_proposal(proposal_id)
        outstanding_questions = [
            question for record in history for question in record.outstanding_questions
        ]
        risks = list(plan.risks)
        if not current_revision:
            risks.append("The proposal source hash no longer matches the authorized repository; do not proceed with this proposal.")
        warnings = [f"{warning.code}: {warning.message}" for warning in analysis.warnings]
        unsupported = list(plan.unsupported_references) + warnings
        actions = self._next_actions(proposal.lifecycle_state, plan.validation_requirements)
        runtime_status = runtime.status if runtime else "not_run"
        runtime_reason = runtime.failure_reason if runtime and runtime.failure_reason else (
            "No runtime-validation authorization has been submitted." if runtime is None else
            "The isolated test command completed successfully." if runtime.status == "passed" else
            "The isolated test command completed with a non-zero exit." if runtime.status == "failed" else
            "The isolated test command exceeded its wall-clock timeout." if runtime.status == "timed_out" else
            "No trusted isolated sandbox was available; no test code was run." if runtime.status == "sandbox_unavailable" else
            "Runtime validation is in progress."
        )
        remaining_runtime_work = (
            ["Configure and verify a hardened Linux sandbox with a pinned local image before any runtime tests can execute."]
            if runtime_status in {"not_run", "sandbox_unavailable"} else
            ["Review the captured runtime evidence and decide separately whether any implementation work should proceed."]
            if runtime_status == "passed" else
            ["Inspect the isolated test failure or timeout and create a revised proposal before requesting a new authorization."]
        )
        if not current_revision:
            actions.insert(0, HandoffNextAction(
                action="Do not use this stale proposal; generate a new task plan and proposal from the current source revision.",
                required_approval=True,
            ))

        report = HandoffReport(
            report_id=uuid4(),
            generated_at=datetime.now(timezone.utc),
            repository_id=proposal.repository_id,
            task=HandoffTaskContext(
                task_id=plan.task_id,
                objective=plan.task_description,
                current_progress=(
                    "A review decision is recorded; the proposal remains unapplied and unexecuted."
                    if history else "A plan and static proposal are available; no review decision has been recorded."
                ),
                task_status=plan.status,
                planning_provider=plan.provider,
                proposal_lifecycle_state=proposal.lifecycle_state,
                proposal_version=proposal.version,
                relevant_files=plan.relevant_files,
                source_references=plan.source_references,
                planned_steps=[f"{step.step}. {step.description}" for step in plan.implementation_steps],
                planned_validation_requirements=plan.validation_requirements,
            ),
            technical_understanding=HandoffTechnicalUnderstanding(
                analysis_summary=analysis.summary,
                relevant_modules=[module for module in analysis.modules if module.path in relevant_paths],
                relevant_functions=relevant_functions,
                relevant_classes=relevant_classes,
                relevant_imports=relevant_imports,
                dependency_manifests=dependency_manifests,
                verified_context=[
                    f"Current static scan found {analysis.summary.module_count} Python modules, {analysis.summary.function_count} functions, and {analysis.summary.class_count} classes.",
                    "Module and import references come from current static repository analysis; runtime behavior was not examined.",
                ],
                analysis_warnings=warnings,
            ),
            proposed_change=HandoffProposedChange(
                summary=proposal.proposed_change_summary,
                target_files=proposal.target_files,
                diff_sha256=proposal.diff_sha256,
                static_validation_status=proposal.static_validation_status,
                validation_findings=proposal.validation_findings,
                provider="mock",
                is_mock=True,
                originating_plan_provider=plan.provider,
                transformation_id=proposal.transformation_id,
                source_revision_status="current" if current_revision else "stale",
            ),
            human_decisions=history,
            outstanding_questions=outstanding_questions,
            validation_and_risks=HandoffValidationRisk(
                static_checks=proposal.validation_findings,
                runtime_tests_status=runtime_status,
                runtime_tests_reason=runtime_reason,
                risks=risks,
                assumptions=plan.assumptions,
                unresolved_dependencies=plan.dependencies,
                unsupported_evidence=unsupported,
            ),
            runtime_execution=HandoffRuntimeExecution(
                status=runtime_status,
                sandbox_summary=runtime.sandbox_summary if runtime else "No runtime validation has been authorized or executed.",
                evidence_id=runtime.evidence_id if runtime else None,
                test_case=runtime.test_case if runtime else "calculator_unit_tests",
                test_command_id=runtime.test_command_id if runtime else "calculator_pytest_suite_v1",
                exit_code=runtime.exit_code if runtime else None,
                duration_ms=runtime.duration_ms if runtime else None,
                test_results=runtime.test_results if runtime else [],
                source_sha256=proposal.target_files[0].original_sha256,
                diff_sha256=proposal.diff_sha256,
                remaining_work=remaining_runtime_work,
            ),
            next_engineer_actions=actions,
            provenance_note=(
                f"Repository facts are from static analysis; the originating plan provider was {plan.provider}; "
                "the proposal diff is the fixed deterministic allowlisted transformation; reviewer identifiers "
                "are unverified local-development labels. No code was changed or executed."
            ),
            provider="mock",
            is_mock=True,
        )
        self.reports.put(report)
        return report

    def get(self, report_id):
        report = self.reports.get(report_id)
        if report is None:
            raise HandoffReportNotFoundError()
        return report

    @staticmethod
    def _next_actions(state: str, test_requirements: list[str]) -> list[HandoffNextAction]:
        actions = {
            "awaiting_review": [HandoffNextAction(action="A local reviewer should inspect the proposal and record a justified decision.", required_approval=True)],
            "review_approved": [HandoffNextAction(action="An engineer must separately decide whether to implement this proposal and run the required tests.", required_approval=True)],
            "changes_requested": [HandoffNextAction(action="Address the review questions and create a revised plan/proposal in a later workflow.", required_approval=True)],
            "rejected": [HandoffNextAction(action="Do not proceed with this proposal; create a new task if the scope changes.", required_approval=False)],
            "proposed": [HandoffNextAction(action="Complete static validation before requesting review.", required_approval=True)],
            "validated": [HandoffNextAction(action="Request local human review; validation does not authorize execution.", required_approval=True)],
        }
        result = actions.get(state, actions["awaiting_review"])
        if test_requirements:
            result.append(HandoffNextAction(
                action="Runtime tests still need to be run in a trusted environment: " + "; ".join(test_requirements[:5]),
                required_approval=True,
            ))
        return result
