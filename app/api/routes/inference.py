"""Safe inference configuration status; never returns secret values."""

from fastapi import APIRouter, Request

from app.core.errors import InferenceQuotaUnavailableError
from app.models.inference import InferenceStatusResponse

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
