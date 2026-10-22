"""Local, unverified human review for in-memory proposals."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from uuid import uuid4

from app.core.config import Settings
from app.core.errors import (
    ProposalNotFoundError,
    ProposalVersionConflictError,
    ProposalSourceConflictError,
    ReviewTransitionConflictError,
)
from app.models.review import AuditEvent, ReviewDecisionRequest, ReviewHistoryResponse, ReviewRecord
from app.services.proposal_generation import verify_current_source_revision
from app.services.proposal_store import InMemoryProposalStore, InMemoryReviewStore

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
    ) -> None:
        self.settings = settings
        self.proposals = proposals
        self.reviews = reviews

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
