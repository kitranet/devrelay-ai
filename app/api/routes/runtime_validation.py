"""Loopback-only isolated runtime validation readiness, authorization, and evidence routes."""

from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import ValidationError

from app.core.errors import ProposalValidationError, RuntimeValidationDisabledError, RuntimeValidationPayloadTooLargeError
from app.core.local_access import require_loopback
from app.models.runtime_validation import RuntimeValidationEvidence, RuntimeValidationRequest, SandboxReadiness
from app.services.runtime_validation import RuntimeValidationService

router = APIRouter(prefix="/api/v1/runtime-validation", tags=["isolated runtime validation"])
MAX_RUNTIME_REQUEST_BYTES = 8_192


def _service(request: Request) -> RuntimeValidationService:
    state = request.app.state
    return RuntimeValidationService(
        state.settings,
        state.proposal_store,
        state.task_plan_store,
        state.review_store,
        state.runtime_validation_store,
        state.runtime_validation_executor,
    )


def _require_enabled(request: Request) -> None:
    if not request.app.state.settings.enable_isolated_runtime_validation:
        raise RuntimeValidationDisabledError()
    if request.app.state.settings.environment.strip().lower() != "development":
        raise RuntimeValidationDisabledError()


@router.get("/readiness", response_model=SandboxReadiness)
def runtime_readiness(request: Request) -> SandboxReadiness:
    require_loopback(request)
    return _service(request).readiness()


@router.post(
    "",
    response_model=RuntimeValidationEvidence,
    status_code=202,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": RuntimeValidationRequest.model_json_schema()}},
        },
    },
)
async def request_runtime_validation(request: Request) -> RuntimeValidationEvidence:
    require_loopback(request)
    _require_enabled(request)
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_RUNTIME_REQUEST_BYTES:
                raise RuntimeValidationPayloadTooLargeError()
        except ValueError:
            raise ProposalValidationError("The runtime-validation request has an invalid content length.") from None
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_RUNTIME_REQUEST_BYTES:
            raise RuntimeValidationPayloadTooLargeError()
        body.extend(chunk)
    try:
        payload = RuntimeValidationRequest.model_validate_json(bytes(body))
    except ValidationError:
        raise ProposalValidationError("Runtime-validation request is invalid. Check the proposal hashes, test case, and separate execution authorization.") from None
    return _service(request).request(payload)


@router.get("/{evidence_id}", response_model=RuntimeValidationEvidence)
def get_runtime_evidence(evidence_id: UUID, request: Request) -> RuntimeValidationEvidence:
    require_loopback(request)
    return _service(request).get(evidence_id)
