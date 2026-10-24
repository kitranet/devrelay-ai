"""Bounded, process-local storage for generated plans and proposals."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import hashlib
import json
from threading import RLock
from uuid import UUID

from app.models.proposal import CodeChangeProposal
from app.models.handoff import HandoffReport
from app.models.runtime_validation import RuntimeValidationEvidence
from app.models.review import AuditEvent, PlanReviewRecord, ReviewRecord
from app.models.task import TaskPlan
from app.core.errors import PlanReviewConflictError, ProposalNotFoundError, ProposalVersionConflictError, ReviewTransitionConflictError


@dataclass(frozen=True)
class StoredTaskPlan:
    plan: TaskPlan
    source_hashes: dict[str, str]
    analysis_snapshot_id: str
    plan_digest: str
    validated_provider: str
    validated_is_mock: bool
    validated_model: str | None
    provider_model_verified: bool


class InMemoryTaskPlanStore:
    """Keeps only recent server-generated task plans; never accepts plan data from clients."""

    def __init__(self, max_records: int = 256) -> None:
        self._max_records = max_records
        self._records: OrderedDict[str, StoredTaskPlan] = OrderedDict()
        self._lock = RLock()

    def put_validated(
        self,
        plan: TaskPlan,
        *,
        source_hashes: dict[str, str],
        analysis_snapshot_id: str,
    ) -> StoredTaskPlan:
        diagnostics = plan.inference_diagnostics
        plan_digest = self.digest_plan(plan)
        plan = plan.model_copy(update={"plan_sha256": plan_digest}, deep=True)
        record = StoredTaskPlan(
            plan=plan.model_copy(deep=True),
            source_hashes=dict(source_hashes),
            analysis_snapshot_id=analysis_snapshot_id,
            plan_digest=plan_digest,
            validated_provider=plan.provider,
            validated_is_mock=plan.is_mock,
            validated_model=diagnostics.model if diagnostics else None,
            provider_model_verified=bool(diagnostics and diagnostics.model_reported_by_provider),
        )
        with self._lock:
            self._records[plan.task_id] = record
            self._records.move_to_end(plan.task_id)
            while len(self._records) > self._max_records:
                self._records.popitem(last=False)
        return self.get(plan.task_id) or record

    def get(self, task_id: str) -> StoredTaskPlan | None:
        with self._lock:
            record = self._records.get(task_id)
            if record is None:
                return None
            self._records.move_to_end(task_id)
            return StoredTaskPlan(
                plan=record.plan.model_copy(deep=True),
                source_hashes=dict(record.source_hashes),
                analysis_snapshot_id=record.analysis_snapshot_id,
                plan_digest=record.plan_digest,
                validated_provider=record.validated_provider,
                validated_is_mock=record.validated_is_mock,
                validated_model=record.validated_model,
                provider_model_verified=record.provider_model_verified,
            )

    @staticmethod
    def digest_plan(plan: TaskPlan) -> str:
        payload = plan.model_dump(exclude={"plan_sha256"})
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


class InMemoryProposalStore:
    """Bounded process-local proposal store for read-only review retrieval."""

    def __init__(self, max_records: int = 128) -> None:
        self._max_records = max_records
        self._records: OrderedDict[UUID, CodeChangeProposal] = OrderedDict()
        self._lock = RLock()

    def put(self, proposal: CodeChangeProposal) -> None:
        with self._lock:
            self._records[proposal.proposal_id] = proposal.model_copy(deep=True)
            self._records.move_to_end(proposal.proposal_id)
            while len(self._records) > self._max_records:
                self._records.popitem(last=False)

    def get(self, proposal_id: UUID) -> CodeChangeProposal | None:
        with self._lock:
            proposal = self._records.get(proposal_id)
            return proposal.model_copy(deep=True) if proposal else None


class InMemoryReviewStore:
    """Bounded process-local review and non-durable audit records."""

    def __init__(self, max_reviews: int = 512, max_events: int = 1_024) -> None:
        self._max_reviews = max_reviews
        self._max_events = max_events
        self._reviews: OrderedDict[UUID, ReviewRecord] = OrderedDict()
        self._events: OrderedDict[UUID, AuditEvent] = OrderedDict()
        self._plan_reviews: OrderedDict[UUID, PlanReviewRecord] = OrderedDict()
        self._lock = RLock()

    def decide(
        self,
        proposal_store: InMemoryProposalStore,
        proposal_id: UUID,
        expected_version: int,
        review: ReviewRecord,
        event: AuditEvent,
    ) -> CodeChangeProposal:
        with self._lock:
            proposal = proposal_store.get(proposal_id)
            if proposal is None:
                raise ProposalNotFoundError()
            if proposal.version != expected_version:
                raise ProposalVersionConflictError()
            if proposal.lifecycle_state != "awaiting_review":
                raise ReviewTransitionConflictError()
            updated = proposal.model_copy(update={
                "lifecycle_state": review.proposal_lifecycle_state,
                "version": proposal.version + 1,
            })
            proposal_store.put(updated)
            self._reviews[review.review_id] = review.model_copy(deep=True)
            self._events[event.event_id] = event.model_copy(deep=True)
            while len(self._reviews) > self._max_reviews:
                self._reviews.popitem(last=False)
            while len(self._events) > self._max_events:
                self._events.popitem(last=False)
            return updated.model_copy(deep=True)

    def history(self, proposal_id: UUID) -> list[ReviewRecord]:
        with self._lock:
            return [record.model_copy(deep=True) for record in self._reviews.values() if record.proposal_id == proposal_id]

    def record_event(self, event: AuditEvent) -> None:
        with self._lock:
            self._events[event.event_id] = event.model_copy(deep=True)
            self._events.move_to_end(event.event_id)
            while len(self._events) > self._max_events:
                self._events.popitem(last=False)

    def audit_events(self, proposal_id: UUID) -> list[AuditEvent]:
        with self._lock:
            return [event.model_copy(deep=True) for event in self._events.values() if event.proposal_id == proposal_id]

    def decide_plan(self, task_id: UUID, expected_digest: str, review: PlanReviewRecord) -> PlanReviewRecord:
        with self._lock:
            current = [item for item in self._plan_reviews.values() if item.task_id == str(task_id)]
            if current or review.plan_sha256 != expected_digest:
                raise PlanReviewConflictError()
            self._plan_reviews[review.review_id] = review.model_copy(deep=True)
            while len(self._plan_reviews) > self._max_reviews:
                self._plan_reviews.popitem(last=False)
            return review.model_copy(deep=True)

    def plan_history(self, task_id: UUID) -> list[PlanReviewRecord]:
        with self._lock:
            return [item.model_copy(deep=True) for item in self._plan_reviews.values() if item.task_id == str(task_id)]


class InMemoryHandoffStore:
    """Bounded, process-local handoff artifact storage."""

    def __init__(self, max_records: int = 128) -> None:
        self._max_records = max_records
        self._records: OrderedDict[UUID, HandoffReport] = OrderedDict()
        self._lock = RLock()

    def put(self, report: HandoffReport) -> None:
        with self._lock:
            self._records[report.report_id] = report.model_copy(deep=True)
            self._records.move_to_end(report.report_id)
            while len(self._records) > self._max_records:
                self._records.popitem(last=False)

    def get(self, report_id: UUID) -> HandoffReport | None:
        with self._lock:
            report = self._records.get(report_id)
            return report.model_copy(deep=True) if report else None

    def get_plan_only(self, report_id: UUID):
        with self._lock:
            report = self._records.get(report_id)
            if report is None or not hasattr(report, "handoff_type") or report.handoff_type != "plan_only":
                return None
            return report.model_copy(deep=True)


class InMemoryRuntimeValidationStore:
    """Bounded process-local evidence store with one authorization per proposal revision."""

    def __init__(self, max_records: int = 512) -> None:
        self._max_records = max_records
        self._records: OrderedDict[UUID, RuntimeValidationEvidence] = OrderedDict()
        self._by_revision: dict[tuple[UUID, int], UUID] = {}
        self._lock = RLock()

    def reserve(self, evidence: RuntimeValidationEvidence) -> bool:
        key = (evidence.proposal_id, evidence.proposal_version)
        with self._lock:
            if key in self._by_revision or len(self._records) >= self._max_records:
                return False
            self._records[evidence.evidence_id] = evidence.model_copy(deep=True)
            self._by_revision[key] = evidence.evidence_id
            return True

    def update(self, evidence: RuntimeValidationEvidence) -> None:
        with self._lock:
            if evidence.evidence_id not in self._records:
                return
            self._records[evidence.evidence_id] = evidence.model_copy(deep=True)

    def get(self, evidence_id: UUID) -> RuntimeValidationEvidence | None:
        with self._lock:
            evidence = self._records.get(evidence_id)
            return evidence.model_copy(deep=True) if evidence else None

    def latest_for_proposal(self, proposal_id: UUID) -> RuntimeValidationEvidence | None:
        with self._lock:
            matching = [item for item in self._records.values() if item.proposal_id == proposal_id]
            return matching[-1].model_copy(deep=True) if matching else None
