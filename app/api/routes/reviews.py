"""Disabled-by-default, loopback-only local proposal review routes."""

from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import ValidationError

from app.core.errors import (
    LocalReviewDisabledError, ProposalValidationError, ReviewPayloadTooLargeError,
)
from app.core.local_access import require_loopback
from app.models.review import (
    LocalReviewStatus, PlanReviewDecisionRequest, PlanReviewHistory, PlanReviewRecord,
    ReviewDecisionRequest, ReviewHistoryResponse, ReviewRecord,
)
from app.services.review_workflow import ReviewWorkflowService

router = APIRouter(prefix="/api/v1/reviews", tags=["local reviews"])
MAX_REVIEW_PAYLOAD_BYTES = 16_384


def require_reviews_enabled(request: Request) -> None:
    if not request.app.state.settings.enable_local_reviews:
        raise LocalReviewDisabledError()
    if request.app.state.settings.environment.strip().lower() != "development":
        raise LocalReviewDisabledError()


def _service(request: Request) -> ReviewWorkflowService:
    return ReviewWorkflowService(
        request.app.state.settings,
        request.app.state.proposal_store,
        request.app.state.review_store,
        request.app.state.task_plan_store,
        request.app.state.repository_scanner,
    )


@router.get("/status", response_model=LocalReviewStatus)
def review_status(request: Request) -> LocalReviewStatus:
    require_loopback(request)
    return LocalReviewStatus(
        enabled=request.app.state.settings.enable_local_reviews and request.app.state.settings.environment.strip().lower() == "development",
        environment=request.app.state.settings.environment,
    )


@router.post(
    "",
    response_model=ReviewRecord,
    status_code=201,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": ReviewDecisionRequest.model_json_schema()}},
        },
    },
)
async def submit_review(request: Request) -> ReviewRecord:
    require_loopback(request)
    require_reviews_enabled(request)
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_REVIEW_PAYLOAD_BYTES:
                raise ReviewPayloadTooLargeError()
        except ValueError:
            raise ProposalValidationError("The review request has an invalid content length.") from None

    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > MAX_REVIEW_PAYLOAD_BYTES:
            raise ReviewPayloadTooLargeError()
        raw.extend(chunk)
    try:
        payload = ReviewDecisionRequest.model_validate_json(bytes(raw))
    except ValidationError:
        raise ProposalValidationError("Review request validation failed. Check the decision, identity label, hashes, and justification.") from None
    return _service(request).submit(payload)


@router.post("/plans", response_model=PlanReviewRecord, status_code=201)
async def submit_plan_review(request: Request) -> PlanReviewRecord:
    require_loopback(request)
    require_reviews_enabled(request)
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_REVIEW_PAYLOAD_BYTES:
                raise ReviewPayloadTooLargeError()
        except ValueError:
            raise ProposalValidationError("The plan review request has an invalid content length.") from None
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > MAX_REVIEW_PAYLOAD_BYTES:
            raise ReviewPayloadTooLargeError()
        raw.extend(chunk)
    try:
        payload = PlanReviewDecisionRequest.model_validate_json(bytes(raw))
    except ValidationError:
        raise ProposalValidationError("Plan review request validation failed. Check the decision, identity label, plan hash, and justification.") from None
    return _service(request).submit_plan(payload)


@router.get("/plans/{task_id}", response_model=PlanReviewHistory)
def get_plan_review_history(task_id: UUID, request: Request) -> PlanReviewHistory:
    require_loopback(request)
    require_reviews_enabled(request)
    return _service(request).plan_history(task_id)


@router.get("/{proposal_id}", response_model=ReviewHistoryResponse)
def get_review_history(proposal_id: UUID, request: Request) -> ReviewHistoryResponse:
    require_loopback(request)
    require_reviews_enabled(request)
    return _service(request).history(proposal_id)
