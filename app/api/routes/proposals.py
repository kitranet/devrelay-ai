"""Read-only creation and retrieval of validated code-change proposals."""

from uuid import UUID

from fastapi import APIRouter, Request

from app.models.proposal import CodeChangeProposal, CreateProposalRequest
from app.services.proposal_generation import ProposalGenerationService

router = APIRouter(prefix="/api/v1/proposals", tags=["proposals"])


@router.post("/create", response_model=CodeChangeProposal, status_code=201)
def create_proposal(payload: CreateProposalRequest, request: Request) -> CodeChangeProposal:
    service = ProposalGenerationService(
        request.app.state.settings,
        request.app.state.repository_scanner,
        request.app.state.task_plan_store,
        request.app.state.proposal_store,
    )
    return service.create(payload)


@router.get("/{proposal_id}", response_model=CodeChangeProposal)
def get_proposal(proposal_id: UUID, request: Request) -> CodeChangeProposal:
    service = ProposalGenerationService(
        request.app.state.settings,
        request.app.state.repository_scanner,
        request.app.state.task_plan_store,
        request.app.state.proposal_store,
    )
    return service.get(proposal_id)
