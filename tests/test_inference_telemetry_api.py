import pytest
from starlette.requests import Request

from app.api.routes.inference import inference_attempts
from app.core.errors import LocalReviewLoopbackError
from app.services.inference_pricing import PricingRegistry
from app.services.inference_telemetry import SQLiteInferenceTelemetry


def test_attempt_history_is_loopback_only_and_contains_safe_metadata(client, tmp_path):
    telemetry = SQLiteInferenceTelemetry(tmp_path / "history.sqlite3", PricingRegistry())
    telemetry.create_attempt(run_id="11111111-1111-4111-8111-111111111111", repository_id="continuity-pipeline-fixture",
                             task_id="22222222-2222-4222-8222-222222222222", provider="mock", model="devrelay-mock-v1")
    client.state.inference_telemetry = telemetry

    def request(host, remote):
        return Request({
            "type": "http", "method": "GET", "scheme": "http", "path": "/api/v1/inference/attempts",
            "query_string": b"", "headers": [], "server": (host, 80), "client": (remote, 43210), "app": client,
        })

    allowed = inference_attempts(request("127.0.0.1", "127.0.0.1"), limit=30, repository_id=None)
    record = allowed.records[0].model_dump()
    assert record["provider"] == "mock"
    assert record["provider_usage_received"] is False
    assert record["estimated_cost_usd"] is None
    assert "task_description" not in record and "content" not in record

    with pytest.raises(LocalReviewLoopbackError):
        inference_attempts(request("example.test", "203.0.113.8"), limit=30, repository_id=None)
