"""Safe inference configuration status; never returns secret values."""

from fastapi import APIRouter, Query, Request

from app.core.errors import InferenceQuotaUnavailableError
from app.core.local_access import require_loopback
from app.models.inference import InferenceAttemptHistoryResponse, InferenceStatusResponse

router = APIRouter(prefix="/api/v1/inference", tags=["inference"])


@router.get("/status", response_model=InferenceStatusResponse)
def inference_status(request: Request) -> InferenceStatusResponse:
    settings = request.app.state.settings
    if settings.inference_provider == "mock":
        return InferenceStatusResponse(
            provider="mock", live_inference_enabled=False, credentials_configured=False,
            quota_status="not_applicable"
        )
    if not settings.nebius_live_inference_enabled:
        return InferenceStatusResponse(
            provider="nebius", live_inference_enabled=False,
            credentials_configured=bool(settings.nebius_api_key and settings.nebius_api_key.get_secret_value()),
            quota_status="not_applicable"
        )
    try:
        snapshot = request.app.state.inference_quota.snapshot()
    except InferenceQuotaUnavailableError:
        return InferenceStatusResponse(
            provider="nebius", live_inference_enabled=True,
            credentials_configured=bool(settings.nebius_api_key and settings.nebius_api_key.get_secret_value()),
            quota_status="unavailable"
        )
    return InferenceStatusResponse(
        provider="nebius",
        live_inference_enabled=True,
        credentials_configured=bool(settings.nebius_api_key and settings.nebius_api_key.get_secret_value()),
        quota_status="exhausted" if snapshot.remaining == 0 else "available",
        quota_total=snapshot.total,
        quota_used=snapshot.used,
        quota_remaining=snapshot.remaining,
    )


@router.get("/attempts", response_model=InferenceAttemptHistoryResponse)
def inference_attempts(
    request: Request,
    limit: int = Query(default=30, ge=1, le=100),
    repository_id: str | None = Query(default=None, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"),
) -> InferenceAttemptHistoryResponse:
    require_loopback(request)
    history = request.app.state.inference_telemetry.list_recent(limit, repository_id)
    return InferenceAttemptHistoryResponse.model_validate(history.model_dump())
