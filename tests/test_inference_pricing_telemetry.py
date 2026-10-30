from decimal import Decimal
from datetime import timedelta
import sqlite3

import pytest

from app.core.errors import ModelIncompleteResponseError
from app.models.inference import ChatMessage, InferenceRequest, InferenceUsage
from app.services.inference import InferenceService
from app.services.inference_pricing import PricingRegistry, estimate_cost_usd
from app.services.inference_telemetry import SQLiteInferenceTelemetry, iso, utc_now


def test_price_lookup_is_exact_and_reasoning_is_not_double_counted():
    registry = PricingRegistry()
    price = registry.find("nebius", "nvidia/Nemotron-3_5-Lightning")
    assert price is not None
    assert estimate_cost_usd(price, 1_349, 381) == Decimal("0.00017238")
    assert registry.find("mock", "devrelay-mock-v1") is None
    assert registry.find("nebius", "another-model") is None


def test_successful_attempt_persists_usage_pricing_and_quota_separately(tmp_path):
    store = SQLiteInferenceTelemetry(tmp_path / "attempts.sqlite3", PricingRegistry(), retention_days=30)
    store.create_attempt(run_id="11111111-1111-4111-8111-111111111111", repository_id="planning-fixture",
                         task_id="22222222-2222-4222-8222-222222222222", provider="nebius",
                         model="nvidia/Nemotron-3_5-Lightning")
    store.mark_quota_reserved("11111111-1111-4111-8111-111111111111")
    store.finish_attempt("11111111-1111-4111-8111-111111111111", request_status="completed",
                         provider_http_status=200, duration_ms=1533,
                         usage=InferenceUsage(input_tokens=23, output_tokens=177, reasoning_tokens=174, total_tokens=200),
                         finish_reason="stop")
    row = store.list_recent().records[0]
    assert row.request_status == "completed"
    assert row.quota_reservation_status == "reserved"
    assert row.input_tokens == 23 and row.output_tokens == 177 and row.reasoning_tokens == 174
    assert row.estimated_cost_usd == "0.000043860000"
    assert row.actual_billed_cost_usd is None and row.billing_status == "unavailable"
    assert row.provider_http_status == 200 and row.duration_ms == 1533
    assert row.plan_validation_failure_category is None


def test_plan_validation_failure_category_is_bounded_and_survives_history(tmp_path):
    store = SQLiteInferenceTelemetry(tmp_path / "attempts.sqlite3", PricingRegistry())
    run_id = "abababab-abab-4bab-8bab-abababababab"
    store.create_attempt(run_id=run_id, repository_id="fixture", task_id=run_id,
                         provider="nebius", model="nvidia/Nemotron-3_5-Lightning")
    store.finish_attempt(run_id, request_status="completed", provider_http_status=200,
                         usage=InferenceUsage(input_tokens=3, output_tokens=4), finish_reason="stop")
    store.mark_plan_validation(run_id, plan_valid=False, citations_valid=None,
                               failure_category="schema_missing_required_field")
    row = store.list_recent().records[0]
    assert row.plan_validation_status == "failed"
    assert row.citation_validation_status == "not_run"
    assert row.plan_validation_failure_category == "schema_missing_required_field"
    with pytest.raises(ValueError):
        store.mark_plan_validation(run_id, plan_valid=False, citations_valid=None,
                                   failure_category="raw provider output")


def test_missing_usage_is_unknown_and_failed_response_keeps_returned_usage(tmp_path):
    store = SQLiteInferenceTelemetry(tmp_path / "attempts.sqlite3", PricingRegistry())
    store.create_attempt(run_id="33333333-3333-4333-8333-333333333333", repository_id="fixture",
                         task_id="44444444-4444-4444-8444-444444444444", provider="nebius",
                         model="nvidia/Nemotron-3_5-Lightning")
    store.finish_attempt("33333333-3333-4333-8333-333333333333", request_status="provider_error",
                         error_code="incomplete_model_response", provider_http_status=200,
                         usage=InferenceUsage(input_tokens=100, output_tokens=2048, reasoning_tokens=2048, total_tokens=2148),
                         finish_reason="length")
    failed = store.list_recent().records[0]
    assert failed.provider_usage_received is True
    assert failed.estimated_cost_usd == "0.000497520000"
    assert failed.error_code == "incomplete_model_response"

    store.create_attempt(run_id="55555555-5555-4555-8555-555555555555", repository_id="fixture",
                         task_id="66666666-6666-4666-8666-666666666666", provider="nebius",
                         model="unpriced-model")
    store.finish_attempt("55555555-5555-4555-8555-555555555555", request_status="timeout", error_code="model_timeout")
    missing = store.list_recent().records[0]
    assert missing.input_tokens is None and missing.output_tokens is None
    assert missing.estimated_cost_usd is None
    assert missing.provider_usage_received is False


def test_inference_service_persists_sanitized_provider_failure_metadata(tmp_path):
    store = SQLiteInferenceTelemetry(tmp_path / "attempts.sqlite3", PricingRegistry())

    class TruncatedProvider:
        async def complete(self, messages, max_tokens=1024, **options):
            del messages, max_tokens, options
            error = ModelIncompleteResponseError()
            error.usage = InferenceUsage(input_tokens=60, output_tokens=128, reasoning_tokens=128, total_tokens=188)
            error.finish_reason = "length"
            error.latency_ms = 1_250
            error.provider_http_status = 200
            raise error

    service = InferenceService(TruncatedProvider(), telemetry=store, provider_name="nebius",
                               model_name="nvidia/Nemotron-3_5-Lightning")
    request = InferenceRequest(
        messages=[ChatMessage(role="user", content="private task text is not persisted")],
        run_id="77777777-7777-4777-8777-777777777777",
        repository_id="continuity-pipeline-fixture", task_id="88888888-8888-4888-8888-888888888888",
    )

    async def call():
        with pytest.raises(ModelIncompleteResponseError):
            await service.generate(request)

    import asyncio
    asyncio.run(call())
    record = store.list_recent().records[0]
    assert record.request_status == "provider_error"
    assert record.provider_http_status == 200 and record.finish_reason == "length"
    assert record.output_tokens == 128 and record.reasoning_tokens == 128
    assert record.estimated_cost_usd == "0.000034320000"
    assert "private task text" not in str(record.model_dump())


def test_abandoned_in_progress_attempts_become_interrupted_without_inventing_usage(tmp_path):
    database = tmp_path / "attempts.sqlite3"
    store = SQLiteInferenceTelemetry(database, PricingRegistry())
    store.create_attempt(run_id="99999999-9999-4999-8999-999999999999", repository_id="fixture",
                         task_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", provider="nebius",
                         model="nvidia/Nemotron-3_5-Lightning")
    connection = sqlite3.connect(database)
    try:
        connection.execute("UPDATE inference_attempts SET started_at=? WHERE run_id=?",
                           (iso(utc_now() - timedelta(minutes=20)), "99999999-9999-4999-8999-999999999999"))
        connection.commit()
    finally:
        connection.close()

    record = store.list_recent().records[0]
    assert record.request_status == "interrupted"
    assert record.error_code == "inference_interrupted"
    assert record.ended_at is not None and record.duration_ms is not None
    assert record.input_tokens is None and record.output_tokens is None
    assert record.estimated_cost_usd is None


@pytest.mark.parametrize("limit", [0, 101])
def test_history_limit_is_bounded(tmp_path, limit):
    store = SQLiteInferenceTelemetry(tmp_path / "attempts.sqlite3", PricingRegistry())
    with pytest.raises(ValueError):
        store.list_recent(limit=limit)
