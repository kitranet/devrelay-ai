"""Local, unverified human review for in-memory proposals."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from uuid import uuid4

from app.core.config import Settings
from app.core.errors import (
    PlanReviewConflictError,
    ProposalNotFoundError,
    ProposalVersionConflictError,
    ProposalSourceConflictError,
    ReviewTransitionConflictError,
)
from app.models.review import (
    AuditEvent, PlanReviewDecisionRequest, PlanReviewHistory, PlanReviewRecord,
    ReviewDecisionRequest, ReviewHistoryResponse, ReviewRecord,
)
from app.services.proposal_generation import verify_current_source_revision
from app.services.proposal_store import InMemoryProposalStore, InMemoryReviewStore
from app.services.proposal_store import InMemoryTaskPlanStore
from app.services.repository_analysis import RepositoryScanner
from app.services.validated_plan import load_current_validated_plan, plan_evidence_references

_DECISION_STATE = {
    "approve": "review_approved",
    "reject": "rejected",
    "request_changes": "changes_requested",
}


class ReviewWorkflowService:
    def __init__(
        self,
        settings: Settings,
        proposals: InMemoryProposalStore,
        reviews: InMemoryReviewStore,
        plans: InMemoryTaskPlanStore,
        scanner: RepositoryScanner,
    ) -> None:
        self.settings = settings
        self.proposals = proposals
        self.reviews = reviews
        self.plans = plans
        self.scanner = scanner

    def submit(self, request: ReviewDecisionRequest) -> ReviewRecord:
        proposal = self.proposals.get(request.proposal_id)
        if proposal is None:
            raise ProposalNotFoundError()
        if proposal.version != request.proposal_version:
            self._record_failure(proposal, request, "The submitted proposal version is stale.")
            raise ProposalVersionConflictError()
        proposal_source_hashes = {target.original_sha256 for target in proposal.target_files}
        diff_hash = hashlib.sha256(proposal.unified_diff.encode("utf-8")).hexdigest()
        if request.source_sha256 not in proposal_source_hashes or request.diff_sha256 != diff_hash or request.diff_sha256 != proposal.diff_sha256:
            self._record_failure(proposal, request, "The submitted source or diff hash does not match the current proposal.")
            raise ProposalVersionConflictError()
        try:
            verify_current_source_revision(self.settings, proposal)
        except ProposalSourceConflictError:
            self._record_failure(proposal, request, "The authorized source revision is stale.")
            raise
        if proposal.lifecycle_state != "awaiting_review":
            self._record_failure(proposal, request, "The proposal already has a review decision.")
            raise ReviewTransitionConflictError()

        now = datetime.now(timezone.utc)
        new_state = _DECISION_STATE[request.decision]
        references = [target.source_reference for target in proposal.target_files]
        record = ReviewRecord(
            review_id=uuid4(),
            proposal_id=proposal.proposal_id,
            task_id=proposal.originating_task_id,
            repository_id=proposal.repository_id,
            decision=request.decision,
            reviewer_identifier=request.reviewer_identifier,
            justification=request.justification,
            timestamp=now,
            proposal_version=proposal.version,
            source_sha256=request.source_sha256,
            diff_sha256=request.diff_sha256,
            proposal_lifecycle_state=new_state,
            evidence_references=references,
            static_validation_status=proposal.static_validation_status,
            runtime_validation_status="not_run",
            outstanding_questions=request.outstanding_questions,
        )
        event = AuditEvent(
            event_id=uuid4(),
            timestamp=now,
            event_type="review_decision_recorded",
            outcome="accepted",
            proposal_id=proposal.proposal_id,
            task_id=proposal.originating_task_id,
            reviewer_identifier=request.reviewer_identifier,
            previous_state=proposal.lifecycle_state,
            new_state=new_state,
            decision=request.decision,
            justification=request.justification,
            source_sha256=request.source_sha256,
            diff_sha256=request.diff_sha256,
            validation_evidence=proposal.validation_findings,
            failure_reason=request.justification if request.decision == "reject" else None,
        )
        try:
            self.reviews.decide(
                self.proposals,
                proposal.proposal_id,
                request.proposal_version,
                record,
                event,
            )
        except (ProposalVersionConflictError, ReviewTransitionConflictError):
            current = self.proposals.get(proposal.proposal_id) or proposal
            self._record_failure(current, request, "The proposal changed during review submission; refresh before retrying.")
            raise
        return record

    def _record_failure(self, proposal, request: ReviewDecisionRequest, reason: str) -> None:
        self.reviews.record_event(AuditEvent(
            event_id=uuid4(),
            timestamp=datetime.now(timezone.utc),
            event_type="review_submission_rejected",
            outcome="rejected",
            proposal_id=proposal.proposal_id,
            task_id=proposal.originating_task_id,
            reviewer_identifier=request.reviewer_identifier,
            previous_state=proposal.lifecycle_state,
            new_state=proposal.lifecycle_state,
            decision=request.decision,
            justification=request.justification,
            source_sha256=request.source_sha256,
            diff_sha256=request.diff_sha256,
            validation_evidence=proposal.validation_findings,
            failure_reason=reason,
        ))

    def history(self, proposal_id) -> ReviewHistoryResponse:
        proposal = self.proposals.get(proposal_id)
        if proposal is None:
            raise ProposalNotFoundError()
        return ReviewHistoryResponse(
            proposal_id=proposal_id,
            current_lifecycle_state=proposal.lifecycle_state,
            current_proposal_version=proposal.version,
            reviews=self.reviews.history(proposal_id),
            audit_events=self.reviews.audit_events(proposal_id),
        )

    def submit_plan(self, request: PlanReviewDecisionRequest) -> PlanReviewRecord:
        stored, _ = load_current_validated_plan(request.task_id, self.plans, self.scanner)
        if request.plan_sha256 != stored.plan_digest:
            raise PlanReviewConflictError()
        if self.reviews.plan_history(request.task_id):
            raise PlanReviewConflictError()
        review_state = {
            "acknowledge": "reviewed",
            "request_changes": "changes_requested",
            "reject": "rejected",
        }[request.decision]
        record = PlanReviewRecord(
            review_id=uuid4(),
            task_id=stored.plan.task_id,
            repository_id=stored.plan.repository_id,
            decision=request.decision,
            review_state=review_state,
            reviewer_identifier=request.reviewer_identifier,
            justification=request.justification,
            timestamp=datetime.now(timezone.utc),
            plan_sha256=stored.plan_digest,
            analysis_snapshot_id=stored.analysis_snapshot_id,
            evidence_references=plan_evidence_references(stored.plan),
            unresolved_questions=request.unresolved_questions or stored.plan.unresolved_questions,
        )
        return self.reviews.decide_plan(request.task_id, stored.plan_digest, record)

    def plan_history(self, task_id) -> PlanReviewHistory:
        stored, _ = load_current_validated_plan(task_id, self.plans, self.scanner)
        records = self.reviews.plan_history(task_id)
        return PlanReviewHistory(
            task_id=stored.plan.task_id,
            review_state=records[-1].review_state if records else "awaiting_review",
            reviews=records,
        )
