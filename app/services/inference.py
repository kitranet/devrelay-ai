"""Application service and explicit provider selection for model inference."""

import asyncio
import logging
import time
import uuid
from typing import Protocol

from app.core.config import Settings
from app.core.errors import ApplicationError, InferenceTelemetryUnavailableError
from app.integrations.nebius import NebiusClient
from app.models.inference import ChatMessage, InferenceRequest, InferenceResponse
from app.services.mock_inference import MockModelProvider
from app.services.inference_quota import InferenceQuota, SQLiteInferenceQuota
from app.services.inference_telemetry import SQLiteInferenceTelemetry, current_attempt_scope

logger = logging.getLogger(__name__)


class InferenceProvider(Protocol):
    async def complete(
        self,
        messages: list[ChatMessage],
        max_tokens: int = 1024,
        *,
        disable_thinking: bool = False,
        json_mode: bool = False,
    ) -> InferenceResponse: ...


class InferenceService:
    def __init__(self, provider: InferenceProvider, *, telemetry: SQLiteInferenceTelemetry | None = None,
                 provider_name: str = "mock", model_name: str = "devrelay-mock-v1") -> None:
        self._provider = provider
        self._telemetry = telemetry
        self._provider_name = provider_name
        self._model_name = model_name

    async def generate(self, request: InferenceRequest) -> InferenceResponse:
        run_id = request.run_id or (str(uuid.uuid4()) if self._telemetry else None)
        started = time.perf_counter()
        if self._telemetry and run_id:
            self._telemetry.create_attempt(
                run_id=run_id, repository_id=request.repository_id or "unknown",
                task_id=request.task_id or run_id, provider=self._provider_name, model=self._model_name,
            )
        options = {}
        if request.disable_thinking:
            options["disable_thinking"] = True
        if request.json_mode:
            options["json_mode"] = True
        try:
            if self._telemetry and run_id:
                with current_attempt_scope(self._telemetry, run_id):
                    response = await self._provider.complete(request.messages, max_tokens=request.max_tokens, **options)
            else:
                response = await self._provider.complete(request.messages, max_tokens=request.max_tokens, **options)
            if self._telemetry:
                try:
                    self._telemetry.finish_attempt(
                        run_id, request_status="completed", provider_http_status=getattr(response, "provider_http_status", None),
                        duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
                        usage=response.usage, finish_reason=response.finish_reason,
                        provider_reported_model=(response.model if response.provider == "nebius" and response.model_reported_by_provider else None),
                    )
                except InferenceTelemetryUnavailableError:
                    logger.error("Inference attempt finalization failed; run_id=%s", run_id)
                    raise
            return response.model_copy(update={"run_id": run_id}) if run_id else response
        except asyncio.CancelledError:
            if self._telemetry and run_id:
                try:
                    self._telemetry.finish_attempt(run_id, request_status="cancelled", duration_ms=max(0, int((time.perf_counter() - started) * 1000)))
                except InferenceTelemetryUnavailableError:
                    logger.error("Inference cancellation could not be finalized; run_id=%s", run_id)
            raise
        except ApplicationError as exc:
            if self._telemetry and run_id:
                try:
                    status = "timeout" if exc.code == "model_timeout" else "blocked" if exc.code in {
                        "missing_credentials", "live_inference_disabled", "inference_quota_exhausted",
                        "inference_quota_unavailable", "inference_limit_exceeded",
                    } else "provider_error"
                    self._telemetry.finish_attempt(
                        run_id, request_status=status, error_code=exc.code,
                        provider_http_status=getattr(exc, "provider_http_status", None),
                        duration_ms=getattr(exc, "latency_ms", None) or max(0, int((time.perf_counter() - started) * 1000)),
                        usage=getattr(exc, "usage", None), finish_reason=getattr(exc, "finish_reason", None),
                        provider_reported_model=getattr(exc, "provider_reported_model", None),
                    )
                except InferenceTelemetryUnavailableError:
                    logger.error("Failed inference attempt could not be finalized; run_id=%s", run_id)
                    raise
            raise


def build_inference_service(settings: Settings, quota: InferenceQuota | None = None,
                            telemetry: SQLiteInferenceTelemetry | None = None) -> InferenceService:
    """Select exactly one configured provider; provider failures never fall back."""
    if settings.inference_provider == "mock":
        return InferenceService(MockModelProvider(), telemetry=telemetry, provider_name="mock", model_name="devrelay-mock-v1")
    return InferenceService(NebiusClient(settings, quota=quota or SQLiteInferenceQuota(settings.nebius_quota_db_path, settings.nebius_total_inference_quota)),
                            telemetry=telemetry, provider_name="nebius", model_name=settings.nebius_model)
