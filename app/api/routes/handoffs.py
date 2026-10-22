"""Local-only generation and retrieval of evidence-grounded handoff reports."""

from uuid import UUID

from fastapi import APIRouter, Request

from app.core.local_access import require_loopback
from app.models.handoff import HandoffReport, HandoffReportRequest
from app.services.handoff_reports import HandoffReportService

router = APIRouter(prefix="/api/v1/handoffs", tags=["handoffs"])


def _service(request: Request) -> HandoffReportService:
    state = request.app.state
    return HandoffReportService(
        state.repository_scanner,
        state.proposal_store,
        state.task_plan_store,
        state.review_store,
        state.handoff_store,
        state.settings,
    )


@router.post("", response_model=HandoffReport, status_code=201)
def generate_handoff(payload: HandoffReportRequest, request: Request) -> HandoffReport:
    require_loopback(request)
    return _service(request).generate(payload.proposal_id)


@router.get("/{report_id}", response_model=HandoffReport)
def get_handoff(report_id: UUID, request: Request) -> HandoffReport:
    require_loopback(request)
    return _service(request).get(report_id)
