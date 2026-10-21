"""Bounded, process-local storage for generated plans and proposals."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from threading import RLock
from uuid import UUID

from app.models.proposal import CodeChangeProposal
from app.models.task import TaskPlan


@dataclass(frozen=True)
class StoredTaskPlan:
    plan: TaskPlan
    source_hashes: dict[str, str]


class InMemoryTaskPlanStore:
    """Keeps only recent server-generated task plans; never accepts plan data from clients."""

    def __init__(self, max_records: int = 256) -> None:
        self._max_records = max_records
        self._records: OrderedDict[str, StoredTaskPlan] = OrderedDict()
        self._lock = RLock()

    def put(self, plan: TaskPlan, source_hashes: dict[str, str] | None = None) -> None:
        record = StoredTaskPlan(plan=plan.model_copy(deep=True), source_hashes=dict(source_hashes or {}))
        with self._lock:
            self._records[plan.task_id] = record
            self._records.move_to_end(plan.task_id)
            while len(self._records) > self._max_records:
                self._records.popitem(last=False)

    def get(self, task_id: str) -> StoredTaskPlan | None:
        with self._lock:
            record = self._records.get(task_id)
            if record is None:
                return None
            self._records.move_to_end(task_id)
            return StoredTaskPlan(
                plan=record.plan.model_copy(deep=True),
                source_hashes=dict(record.source_hashes),
            )


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
