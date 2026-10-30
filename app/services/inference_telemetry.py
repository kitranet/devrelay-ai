"""Bounded local persistence for sanitized inference-attempt metadata."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.errors import InferenceTelemetryUnavailableError
from app.models.inference import InferenceUsage, PlanValidationFailureCategory
from app.services.inference_pricing import PricingRegistry, estimate_cost_usd

logger = logging.getLogger(__name__)
MAX_TELEMETRY_RECORDS = 5_000
MAX_RETENTION_DAYS = 365
_SAFE_ERROR_CODES = {
    "incomplete_model_response", "empty_model_response", "invalid_model_response",
    "model_provider_error", "model_timeout", "missing_credentials", "live_inference_disabled",
    "inference_quota_exhausted", "inference_quota_unavailable", "inference_limit_exceeded",
    "task_planning_timeout", "invalid_task_plan", "sensitive_inference_content",
    "inference_telemetry_unavailable", "inference_interrupted",
}
_PLAN_VALIDATION_FAILURE_CATEGORIES = {
    "provider_metadata_mismatch", "sensitive_content_rejected", "incomplete_response",
    "empty_model_content", "invalid_json_syntax", "incorrect_json_root_type",
    "schema_missing_required_field", "schema_incorrect_field_type", "schema_invalid_enum_value",
    "schema_excessive_item_count", "schema_validation_failed", "model_identity_unverified",
}
_CURRENT_ATTEMPT: ContextVar[tuple["SQLiteInferenceTelemetry", str] | None] = ContextVar("devrelay_inference_attempt", default=None)


def current_attempt_scope(store: "SQLiteInferenceTelemetry", run_id: str):
    """Bind the request attempt so the quota adapter can record reservation separately."""
    from contextlib import contextmanager

    @contextmanager
    def scope():
        token = _CURRENT_ATTEMPT.set((store, run_id))
        try:
            yield
        finally:
            _CURRENT_ATTEMPT.reset(token)
    return scope()


def mark_current_attempt_quota_reserved() -> None:
    current = _CURRENT_ATTEMPT.get()
    if current:
        current[0].mark_quota_reserved(current[1])


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds") if value else None


class InferenceAttemptRecord(BaseModel):
    run_id: str
    timestamp: str
    repository_id: str
    task_id: str
    provider: Literal["nebius", "mock"]
    model: str
    provider_reported_model: str | None = None
    request_status: Literal["in_progress", "completed", "provider_error", "timeout", "cancelled", "blocked", "interrupted"]
    provider_http_status: int | None = Field(default=None, ge=100, le=599)
    error_code: str | None = None
    started_at: str
    ended_at: str | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    finish_reason: str | None = None
    pricing_model: str | None = None
    price_per_million_input_tokens: str | None = None
    price_per_million_output_tokens: str | None = None
    estimated_cost_usd: str | None = None
    actual_billed_cost_usd: str | None = None
    billing_status: Literal["unavailable", "not_applicable"]
    pricing_source: str | None = None
    pricing_as_of: str | None = None
    pricing_registry_version: str | None = None
    citation_validation_status: Literal["not_run", "passed", "failed"] = "not_run"
    plan_validation_status: Literal["not_run", "passed", "failed"] = "not_run"
    plan_validation_failure_category: PlanValidationFailureCategory | None = None
    verified_reference_count: int | None = Field(default=None, ge=0)
    unsupported_reference_count: int | None = Field(default=None, ge=0)
    provider_usage_received: bool = False
    quota_reservation_status: Literal["not_required", "not_reserved", "reserved", "unknown"]


class InferenceAttemptHistory(BaseModel):
    records: list[InferenceAttemptRecord]
    retention_days: int
    maximum_records: int
    billing_information: Literal["unavailable"] = "unavailable"


class SQLiteInferenceTelemetry:
    """SQLite audit of run metadata only; prompts, source text and credentials are never stored."""

    def __init__(self, database_path: Path, pricing: PricingRegistry, retention_days: int = 90) -> None:
        if not 1 <= retention_days <= MAX_RETENTION_DAYS:
            raise ValueError("Inference telemetry retention is outside the allowed range")
        self.database_path = database_path
        self.pricing = pricing
        self.retention_days = retention_days

    def _connect(self) -> sqlite3.Connection:
        connection: sqlite3.Connection | None = None
        try:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            if os.name == "posix":
                os.chmod(self.database_path.parent, 0o700)
            connection = sqlite3.connect(self.database_path, timeout=5, isolation_level=None)
            if os.name == "posix":
                os.chmod(self.database_path, 0o600)
            connection.execute("PRAGMA busy_timeout=5000")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS inference_attempts ("
                "run_id TEXT PRIMARY KEY, started_at TEXT NOT NULL, ended_at TEXT, "
                "repository_id TEXT NOT NULL, task_id TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL, provider_reported_model TEXT, "
                "request_status TEXT NOT NULL, provider_http_status INTEGER, error_code TEXT, duration_ms INTEGER, "
                "input_tokens INTEGER, output_tokens INTEGER, reasoning_tokens INTEGER, total_tokens INTEGER, "
                "finish_reason TEXT, pricing_model TEXT, price_input TEXT, price_output TEXT, estimated_cost TEXT, "
                "actual_billed_cost TEXT, billing_status TEXT NOT NULL, pricing_source TEXT, pricing_as_of TEXT, "
                "pricing_registry_version TEXT, citation_validation_status TEXT NOT NULL, "
                "plan_validation_status TEXT NOT NULL, verified_reference_count INTEGER, "
                "plan_validation_failure_category TEXT, unsupported_reference_count INTEGER, provider_usage_received INTEGER NOT NULL, "
                "quota_reservation_status TEXT NOT NULL)"
            )
            columns = {row[1] for row in connection.execute("PRAGMA table_info(inference_attempts)")}
            if "provider_reported_model" not in columns:
                connection.execute("ALTER TABLE inference_attempts ADD COLUMN provider_reported_model TEXT")
            if "plan_validation_failure_category" not in columns:
                connection.execute("ALTER TABLE inference_attempts ADD COLUMN plan_validation_failure_category TEXT")
            connection.execute("CREATE INDEX IF NOT EXISTS ix_inference_attempts_started ON inference_attempts(started_at DESC)")
            self._prune(connection)
            return connection
        except (OSError, sqlite3.Error) as exc:
            if connection is not None:
                connection.close()
            logger.warning("Inference telemetry storage unavailable; error_type=%s", type(exc).__name__)
            raise InferenceTelemetryUnavailableError() from None

    def _prune(self, connection: sqlite3.Connection) -> None:
        cutoff = iso(utc_now() - timedelta(days=self.retention_days))
        connection.execute("DELETE FROM inference_attempts WHERE started_at < ?", (cutoff,))
        connection.execute(
            "DELETE FROM inference_attempts WHERE run_id IN ("
            "SELECT run_id FROM inference_attempts ORDER BY started_at DESC LIMIT -1 OFFSET ?)",
            (MAX_TELEMETRY_RECORDS,),
        )

    @staticmethod
    def _values(record: InferenceAttemptRecord) -> tuple[Any, ...]:
        return (
            record.run_id, record.started_at, record.ended_at, record.repository_id, record.task_id,
            record.provider, record.model, record.provider_reported_model, record.request_status, record.provider_http_status,
            record.error_code, record.duration_ms, record.input_tokens, record.output_tokens,
            record.reasoning_tokens, record.total_tokens, record.finish_reason, record.pricing_model,
            record.price_per_million_input_tokens, record.price_per_million_output_tokens,
            record.estimated_cost_usd, record.actual_billed_cost_usd, record.billing_status,
            record.pricing_source, record.pricing_as_of, record.pricing_registry_version,
            record.citation_validation_status, record.plan_validation_status, record.plan_validation_failure_category,
            record.verified_reference_count, record.unsupported_reference_count,
            int(record.provider_usage_received), record.quota_reservation_status,
        )

    @staticmethod
    def _columns() -> str:
        return (
            "run_id,started_at,ended_at,repository_id,task_id,provider,model,provider_reported_model,request_status,"
            "provider_http_status,error_code,duration_ms,input_tokens,output_tokens,reasoning_tokens,total_tokens,"
            "finish_reason,pricing_model,price_input,price_output,estimated_cost,actual_billed_cost,billing_status,"
            "pricing_source,pricing_as_of,pricing_registry_version,citation_validation_status,plan_validation_status,"
            "plan_validation_failure_category,"
            "verified_reference_count,unsupported_reference_count,provider_usage_received,quota_reservation_status"
        )

    def create_attempt(self, *, run_id: str, repository_id: str, task_id: str, provider: str, model: str) -> None:
        try:
            price = self.pricing.find(provider, model)
            is_mock = provider == "mock"
            record = InferenceAttemptRecord(
                run_id=run_id, timestamp=iso(utc_now()), started_at=iso(utc_now()),
                repository_id=repository_id, task_id=task_id, provider=provider, model=model,
                request_status="in_progress", billing_status="not_applicable" if is_mock else "unavailable",
                pricing_model=price.pricing_model if price else None,
                price_per_million_input_tokens=str(price.price_per_million_input_tokens) if price else None,
                price_per_million_output_tokens=str(price.price_per_million_output_tokens) if price else None,
                pricing_source=price.source if price else None,
                pricing_as_of=price.effective_as_of if price else None,
                pricing_registry_version=price.registry_version if price else None,
                quota_reservation_status="not_required" if is_mock else "not_reserved",
            )
            connection = self._connect()
            try:
                placeholders = ",".join("?" for _ in range(33))
                connection.execute(
                    f"INSERT INTO inference_attempts ({self._columns()}) VALUES ({placeholders})",
                    self._values(record),
                )
            finally:
                connection.close()
        except (sqlite3.Error, OSError, ValueError) as exc:
            logger.warning("Inference attempt could not be persisted before provider call; error_type=%s", type(exc).__name__)
            raise InferenceTelemetryUnavailableError() from None

    def _update(self, run_id: str, values: dict[str, Any]) -> None:
        allowed = {
            "request_status", "provider_http_status", "error_code", "ended_at", "duration_ms",
            "input_tokens", "output_tokens", "reasoning_tokens", "total_tokens", "finish_reason",
            "provider_reported_model",
            "estimated_cost_usd", "provider_usage_received", "quota_reservation_status",
            "citation_validation_status", "plan_validation_status", "plan_validation_failure_category", "verified_reference_count",
            "unsupported_reference_count",
        }
        if not values or set(values) - allowed:
            raise ValueError("Invalid inference telemetry update fields")
        fields = []
        parameters: list[Any] = []
        for field, value in values.items():
            column = "estimated_cost" if field == "estimated_cost_usd" else field
            fields.append(f"{column} = ?")
            parameters.append(int(value) if field == "provider_usage_received" else value)
        parameters.append(run_id)
        connection = self._connect()
        try:
            cursor = connection.execute(
                f"UPDATE inference_attempts SET {', '.join(fields)} WHERE run_id = ?", parameters
            )
            if cursor.rowcount != 1:
                raise sqlite3.Error("Inference attempt record was not found")
        except sqlite3.Error as exc:
            logger.warning("Inference attempt update failed; error_type=%s", type(exc).__name__)
            raise InferenceTelemetryUnavailableError() from None
        finally:
            connection.close()

    def mark_quota_reserved(self, run_id: str) -> None:
        self._update(run_id, {"quota_reservation_status": "reserved"})

    def finish_attempt(
        self, run_id: str, *, request_status: str, error_code: str | None = None,
        provider_http_status: int | None = None, duration_ms: int | None = None,
        usage: InferenceUsage | None = None, finish_reason: str | None = None,
        provider_reported_model: str | None = None,
    ) -> None:
        safe_status = request_status if request_status in {"completed", "provider_error", "timeout", "cancelled", "blocked", "interrupted"} else "provider_error"
        safe_error = error_code if error_code in _SAFE_ERROR_CODES else None
        usage_values: dict[str, Any] = {}
        usage_received = bool(usage and any(value is not None for value in usage.model_dump().values()))
        if usage:
            usage_values = {
                "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens,
                "reasoning_tokens": usage.reasoning_tokens, "total_tokens": usage.total_tokens,
            }
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT provider,model,price_input,price_output FROM inference_attempts WHERE run_id = ?", (run_id,)
            ).fetchone()
            if row is None:
                raise sqlite3.Error("Inference attempt record was not found")
            provider, model, price_input, price_output = row
            cost: str | None = None
            if (provider != "mock" and price_input is not None and price_output is not None
                    and usage and usage.input_tokens is not None and usage.output_tokens is not None):
                price = self.pricing.find(provider, model)
                if price:
                    cost = format(estimate_cost_usd(price, usage.input_tokens, usage.output_tokens), ".12f")
            fields = {
                "request_status": safe_status, "error_code": safe_error,
                "provider_http_status": provider_http_status if provider_http_status and 100 <= provider_http_status <= 599 else None,
                "ended_at": iso(utc_now()), "duration_ms": duration_ms,
                "provider_usage_received": usage_received,
                "finish_reason": finish_reason if finish_reason in {"stop", "length", "content_filter", "tool_calls", "function_call", "mock_complete", "other"} else None,
                "provider_reported_model": provider_reported_model if provider_reported_model and len(provider_reported_model) <= 200 else None,
                "estimated_cost_usd": cost,
                **usage_values,
            }
            self._update(run_id, fields)
        except (sqlite3.Error, InvalidOperation) as exc:
            logger.warning("Inference attempt finalization failed; error_type=%s", type(exc).__name__)
            raise InferenceTelemetryUnavailableError() from None
        finally:
            connection.close()

    def mark_plan_validation(
        self, run_id: str, *, plan_valid: bool, citations_valid: bool | None,
        verified_count: int | None = None, unsupported_count: int | None = None,
        failure_category: PlanValidationFailureCategory | None = None,
    ) -> None:
        if plan_valid and failure_category is not None:
            raise ValueError("A valid plan cannot have a validation failure category")
        if failure_category is not None and failure_category not in _PLAN_VALIDATION_FAILURE_CATEGORIES:
            raise ValueError("Invalid plan validation failure category")
        self._update(run_id, {
            "plan_validation_status": "passed" if plan_valid else "failed",
            "plan_validation_failure_category": failure_category if not plan_valid else None,
            "citation_validation_status": "not_run" if citations_valid is None else ("passed" if citations_valid else "failed"),
            "verified_reference_count": verified_count,
            "unsupported_reference_count": unsupported_count,
        })

    def mark_timeout(self, run_id: str, *, duration_ms: int | None, error_code: str = "task_planning_timeout") -> None:
        self._update(run_id, {
            "request_status": "timeout", "error_code": error_code, "ended_at": iso(utc_now()),
            "duration_ms": duration_ms,
        })

    def list_recent(self, limit: int = 30, repository_id: str | None = None) -> InferenceAttemptHistory:
        if not 1 <= limit <= 100:
            raise ValueError("Inference history limit must be between 1 and 100")
        connection = self._connect()
        try:
            if repository_id:
                rows = connection.execute(
                    f"SELECT {self._columns()} FROM inference_attempts WHERE repository_id = ? ORDER BY started_at DESC LIMIT ?",
                    (repository_id, limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    f"SELECT {self._columns()} FROM inference_attempts ORDER BY started_at DESC LIMIT ?", (limit,)
                ).fetchall()
        except sqlite3.Error as exc:
            logger.warning("Inference attempt history read failed; error_type=%s", type(exc).__name__)
            raise InferenceTelemetryUnavailableError() from None
        finally:
            connection.close()
        field_names = [field.strip() for field in self._columns().split(",")]
        records = []
        for row in rows:
            data = dict(zip(field_names, row))
            data["timestamp"] = data["started_at"]
            if data["request_status"] == "in_progress":
                started_at = datetime.fromisoformat(data["started_at"])
                age = utc_now() - started_at
                if age > timedelta(minutes=15):
                    ended_at = utc_now()
                    duration_ms = max(0, int(age.total_seconds() * 1000))
                    self._update(data["run_id"], {
                        "request_status": "interrupted", "error_code": "inference_interrupted",
                        "ended_at": iso(ended_at), "duration_ms": duration_ms,
                    })
                    data.update({
                        "request_status": "interrupted", "error_code": "inference_interrupted",
                        "ended_at": iso(ended_at), "duration_ms": duration_ms,
                    })
            data["price_per_million_input_tokens"] = data.pop("price_input")
            data["price_per_million_output_tokens"] = data.pop("price_output")
            data["estimated_cost_usd"] = data.pop("estimated_cost")
            data["actual_billed_cost_usd"] = data.pop("actual_billed_cost")
            data["provider_usage_received"] = bool(data["provider_usage_received"])
            records.append(InferenceAttemptRecord.model_validate(data))
        return InferenceAttemptHistory(records=records, retention_days=self.retention_days, maximum_records=MAX_TELEMETRY_RECORDS)
