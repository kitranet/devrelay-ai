"""Bounded Nebius Token Factory chat-completions client."""

from __future__ import annotations

import json
import logging
import math
import re
import threading
import time
from typing import Any

import httpx

from app.core.config import Settings
from app.core.errors import (
    InferenceLimitError,
    LiveInferenceDisabledError,
    MalformedModelResponseError,
    MissingCredentialsError,
    ModelEmptyResponseError,
    ModelIncompleteResponseError,
    ModelProviderError,
    ModelTimeoutError,
)
from app.models.inference import ChatMessage, InferenceResponse, InferenceUsage
from app.services.inference_quota import InferenceQuota, SQLiteInferenceQuota
from app.services.inference_telemetry import mark_current_attempt_quota_reserved

logger = logging.getLogger(__name__)
MAX_PROVIDER_RESPONSE_BYTES = 1_000_000
_SAFE_MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")
_SECRET_LIKE = re.compile(
    r"(?i)(?:-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"(?:api[_-]?key|access[_-]?token|password|secret)\s*[:=]\s*\S+|"
    r"nvapi-[A-Za-z0-9_-]{16,}|sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,})"
)
_INTERNAL_REASONING = re.compile(r"(?is)<think\b[^>]*>.*?</think\s*>")


def estimate_prompt_tokens(messages: list[ChatMessage], model: str) -> int:
    """Return a conservative character/byte heuristic, not a provider tokenizer count."""
    payload = {
        "model": model,
        "messages": [message.model_dump() for message in messages],
    }
    serialized_bytes = len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    # One estimated token per three UTF-8 bytes is deliberately conservative for
    # ordinary prose. The independent character/context caps remain authoritative.
    return max(1, math.ceil(serialized_bytes / 3))


class NebiusClient:
    def __init__(self, settings: Settings, http_client: httpx.AsyncClient | None = None, quota: InferenceQuota | None = None) -> None:
        self.settings = settings
        self._http_client = http_client
        self._in_flight = threading.BoundedSemaphore(settings.nebius_max_in_flight_requests)
        self._quota = quota or SQLiteInferenceQuota(settings.nebius_quota_db_path, settings.nebius_total_inference_quota)

    async def complete(
        self,
        messages: list[ChatMessage],
        max_tokens: int | None = None,
        *,
        disable_thinking: bool = False,
        json_mode: bool = False,
    ) -> InferenceResponse:
        if self.settings.inference_provider != "nebius":
            raise LiveInferenceDisabledError()
        if not self.settings.nebius_live_inference_enabled:
            raise LiveInferenceDisabledError()
        if self.settings.nebius_api_key is None or not self.settings.nebius_api_key.get_secret_value():
            raise MissingCredentialsError("NEBIUS_API_KEY is required for model inference.")
        api_key = self.settings.nebius_api_key.get_secret_value()
        if not _is_safe_model_id(self.settings.nebius_model, api_key):
            raise ModelProviderError("The configured Nebius model identifier is invalid.")
        if disable_thinking and self.settings.nebius_model != "nvidia/Nemotron-3_5-Lightning":
            raise ModelProviderError("Thinking control is only enabled for the configured Nemotron 3.5 Lightning model.")

        output_tokens = self.settings.nebius_max_output_tokens if max_tokens is None else max_tokens
        if output_tokens < 1 or output_tokens > self.settings.nebius_max_output_tokens:
            raise InferenceLimitError("Requested output tokens exceed NEBIUS_MAX_OUTPUT_TOKENS.")
        prompt_estimate = estimate_prompt_tokens(messages, self.settings.nebius_model)
        if prompt_estimate > self.settings.nebius_max_prompt_tokens:
            raise InferenceLimitError("Estimated prompt size exceeds NEBIUS_MAX_PROMPT_TOKENS.")
        if not self._in_flight.acquire(blocking=False):
            raise InferenceLimitError("The configured maximum number of paid inference requests is already in flight.")

        try:
            self._quota.reserve()
            mark_current_attempt_quota_reserved()
        except Exception:
            self._in_flight.release()
            raise

        endpoint = f"{self.settings.nebius_base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": self.settings.nebius_model,
            "messages": [message.model_dump() for message in messages],
            "max_tokens": output_tokens,
        }
        if disable_thinking:
            payload["extra_body"] = {
                "chat_template_kwargs": {"enable_thinking": False}
            }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {self.settings.nebius_api_key.get_secret_value()}"}
        started = time.perf_counter()
        try:
            if self._http_client is None:
                async with httpx.AsyncClient(timeout=self.settings.nebius_timeout_seconds) as client:
                    response = await client.post(endpoint, json=payload, headers=headers)
            else:
                response = await self._http_client.post(
                    endpoint,
                    json=payload,
                    headers=headers,
                    timeout=self.settings.nebius_timeout_seconds,
                )
            latency_ms = max(0, int((time.perf_counter() - started) * 1000))
            provider_http_status = response.status_code
            response.raise_for_status()
            if len(response.content) > MAX_PROVIDER_RESPONSE_BYTES:
                logger.warning("Nebius response exceeded the local response-size limit; latency_ms=%d", latency_ms)
                error = MalformedModelResponseError()
                _attach_diagnostics(error, latency_ms=latency_ms, provider_http_status=provider_http_status)
                raise error
            body: Any = None
            usage: InferenceUsage | None = None
            finish_reason: Any = None
            reported_model: str | None = None
            try:
                body = response.json()
                usage = _parse_usage(body.get("usage")) if isinstance(body, dict) else None
                if isinstance(body, dict):
                    candidate, provider_reported = _reported_model(body.get("model"), self.settings.nebius_model, api_key)
                    reported_model = candidate if provider_reported else None
                choice = body["choices"][0]
                message = choice["message"]
                content = message["content"]
                finish_reason = choice["finish_reason"]
            except (ValueError, KeyError, IndexError, TypeError):
                logger.warning(
                    "Nebius returned a malformed completion; model=%s latency_ms=%d prompt_tokens_estimate=%d",
                    self.settings.nebius_model, latency_ms, prompt_estimate,
                )
                error = MalformedModelResponseError()
                _attach_diagnostics(error, usage=usage, finish_reason=finish_reason, latency_ms=latency_ms,
                                    provider_http_status=provider_http_status, provider_reported_model=reported_model)
                raise error from None

            if not isinstance(body, dict) or not isinstance(message, dict):
                raise MalformedModelResponseError()
            if not isinstance(finish_reason, str) or not finish_reason:
                raise MalformedModelResponseError()
            if finish_reason == "length":
                logger.warning(
                    "Nebius completion was truncated; model=%s latency_ms=%d finish_reason=length input_tokens=%s output_tokens=%s reasoning_tokens=%s total_tokens=%s",
                    _reported_model(
                        body.get("model"), self.settings.nebius_model,
                        self.settings.nebius_api_key.get_secret_value(),
                    )[0], latency_ms,
                    usage.input_tokens, usage.output_tokens, usage.reasoning_tokens, usage.total_tokens,
                )
                error = ModelIncompleteResponseError()
                _attach_diagnostics(error, usage=usage, finish_reason=finish_reason, latency_ms=latency_ms,
                                    provider_http_status=provider_http_status, provider_reported_model=reported_model)
                raise error
            if not isinstance(content, str) or not content.strip():
                logger.warning(
                    "Nebius returned an empty completion; model=%s latency_ms=%d finish_reason=%s",
                    self.settings.nebius_model, latency_ms, _safe_finish_reason(finish_reason),
                )
                error = ModelEmptyResponseError()
                _attach_diagnostics(error, usage=usage, finish_reason=finish_reason, latency_ms=latency_ms,
                                    provider_http_status=provider_http_status, provider_reported_model=reported_model)
                raise error
            if (api_key and api_key in content) or _SECRET_LIKE.search(content) or _INTERNAL_REASONING.search(content):
                logger.warning("Nebius completion was rejected by the sensitive-content filter; model=%s latency_ms=%d", self.settings.nebius_model, latency_ms)
                error = MalformedModelResponseError()
                _attach_diagnostics(error, usage=usage, finish_reason=finish_reason, latency_ms=latency_ms,
                                    provider_http_status=provider_http_status, provider_reported_model=reported_model)
                raise error
            if finish_reason != "stop":
                logger.warning(
                    "Nebius completion did not report a successful stop; model=%s latency_ms=%d finish_reason=%s",
                    self.settings.nebius_model, latency_ms, _safe_finish_reason(finish_reason),
                )
                error = ModelProviderError("Nebius inference did not report a successfully completed answer.")
                _attach_diagnostics(error, usage=usage, finish_reason=finish_reason, latency_ms=latency_ms,
                                    provider_http_status=provider_http_status, provider_reported_model=reported_model)
                raise error

            model_name, model_reported = _reported_model(
                body.get("model"), self.settings.nebius_model,
                self.settings.nebius_api_key.get_secret_value(),
            )
            usage = _parse_usage(body.get("usage"))
            log_usage = usage or InferenceUsage()
            logger.info(
                "Nebius inference completed; model=%s model_reported=%s latency_ms=%d prompt_tokens_estimate=%d input_tokens=%s output_tokens=%s reasoning_tokens=%s total_tokens=%s finish_reason=stop",
                model_name, model_reported, latency_ms, prompt_estimate,
                log_usage.input_tokens, log_usage.output_tokens, log_usage.reasoning_tokens, log_usage.total_tokens,
            )
            return InferenceResponse(
                provider_http_status=provider_http_status,
                model=model_name,
                content=content,
                provider="nebius",
                is_mock=False,
                completion_status="completed",
                finish_reason="stop",
                model_reported_by_provider=model_reported,
                latency_ms=latency_ms,
                usage=usage,
            )
        except httpx.TimeoutException as exc:
            latency_ms = max(0, int((time.perf_counter() - started) * 1000))
            logger.warning("Nebius inference timed out; model=%s latency_ms=%d", self.settings.nebius_model, latency_ms)
            error = ModelTimeoutError("Nebius inference request timed out.")
            _attach_diagnostics(error, latency_ms=latency_ms)
            raise error from exc
        except httpx.HTTPStatusError as exc:
            latency_ms = max(0, int((time.perf_counter() - started) * 1000))
            logger.warning(
                "Nebius inference returned HTTP %s; model=%s latency_ms=%d",
                exc.response.status_code, self.settings.nebius_model, latency_ms,
            )
            error = ModelProviderError(f"Nebius inference request failed with HTTP {exc.response.status_code}.")
            _attach_diagnostics(error, latency_ms=latency_ms, provider_http_status=exc.response.status_code)
            raise error from exc
        except httpx.RequestError as exc:
            latency_ms = max(0, int((time.perf_counter() - started) * 1000))
            logger.warning("Nebius inference request failed; model=%s latency_ms=%d error_type=%s", self.settings.nebius_model, latency_ms, type(exc).__name__)
            error = ModelProviderError("Nebius inference failed or returned an invalid response.")
            _attach_diagnostics(error, latency_ms=latency_ms)
            raise error from exc
        finally:
            self._in_flight.release()


def _safe_finish_reason(value: Any) -> str:
    if value in {"stop", "length", "content_filter", "tool_calls", "function_call"}:
        return value
    return "other"


def _attach_diagnostics(error: Exception, *, usage: InferenceUsage | None = None,
                        finish_reason: Any = None, latency_ms: int | None = None,
                        provider_http_status: int | None = None,
                        provider_reported_model: str | None = None) -> None:
    """Attach sanitized metadata only; never retain provider text or headers."""
    error.usage = usage
    error.finish_reason = _safe_finish_reason(finish_reason) if finish_reason else None
    error.latency_ms = latency_ms
    error.provider_http_status = provider_http_status
    error.provider_reported_model = provider_reported_model


def _reported_model(value: Any, requested: str, api_key: str | None = None) -> tuple[str, bool]:
    if _is_safe_model_id(value, api_key):
        return value.strip(), True
    if _is_safe_model_id(requested, api_key):
        return requested.strip(), False
    return "unknown-model", False


def _is_safe_model_id(value: Any, api_key: str | None) -> bool:
    return bool(
        isinstance(value, str)
        and _SAFE_MODEL_ID.fullmatch(value.strip())
        and not (api_key and api_key in value)
        and not _SECRET_LIKE.search(value)
    )


def _token_count(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _parse_usage(value: Any) -> InferenceUsage | None:
    if not isinstance(value, dict):
        return None
    details = value.get("completion_tokens_details")
    reasoning = value.get("reasoning_tokens")
    if reasoning is None and isinstance(details, dict):
        reasoning = details.get("reasoning_tokens")
    parsed = InferenceUsage(
        input_tokens=_token_count(value.get("prompt_tokens")),
        output_tokens=_token_count(value.get("completion_tokens")),
        reasoning_tokens=_token_count(reasoning),
        total_tokens=_token_count(value.get("total_tokens")),
    )
    return parsed if any(item is not None for item in parsed.model_dump().values()) else None
