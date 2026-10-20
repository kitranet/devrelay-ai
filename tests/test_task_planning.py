import asyncio
import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


PLANNING_REPO = Path(__file__).parent / "fixtures" / "planning_repo"


def make_client(tmp_path: Path, *, provider="mock") -> TestClient:
    root = tmp_path / "repo"
    shutil.copytree(PLANNING_REPO, root)
    settings = Settings(
        inference_provider=provider,
        authorized_repositories={"planning-fixture": root},
    )
    return TestClient(create_app(settings))


def test_request_validation_and_unauthorized_repository(tmp_path):
    with make_client(tmp_path) as client:
        invalid = client.post("/api/v1/tasks/plan", json={"repository_id": "planning-fixture", "task_description": "short"})
        unauthorized = client.post("/api/v1/tasks/plan", json={"repository_id": "elsewhere", "task_description": "Investigate a behavior carefully"})
    assert invalid.status_code == 422
    assert unauthorized.status_code == 404
    assert unauthorized.json()["error"]["code"] == "repository_not_found"


def test_three_synthetic_scenarios_are_traceable_and_deterministic(tmp_path):
    tasks = [
        ("Fix the division by zero defect in the calculator", {"package/calculator.py", "tests/test_calculator.py"}, "tests/test_calculator.py"),
        ("Add validation to the existing API input", {"package/api.py", "tests/test_api.py"}, "tests/test_api.py"),
        ("Investigate an unfamiliar function with its dependencies", {"package/service.py", "package/dependencies.py", "tests/test_service.py"}, "tests/test_service.py"),
    ]
    with make_client(tmp_path) as client:
        for description, expected_files, expected_test in tasks:
            payload = {"repository_id": "planning-fixture", "task_description": description}
            first = client.post("/api/v1/tasks/plan", json=payload)
            second = client.post("/api/v1/tasks/plan", json=payload)
            assert first.status_code == second.status_code == 200
            plan = first.json()
            assert plan["status"] == "planned"
            assert plan["provider"] == "mock" and plan["is_mock"] is True
            assert set(plan["relevant_files"]) == expected_files
            assert any(expected_test in item for item in plan["validation_requirements"])
            assert plan["human_approval_required"] is True
            assert plan["execution_status"] == "not_started"
            assert { (ref["path"], ref["line"]) for ref in plan["source_references"] }
            assert [(ref["path"], ref["line"]) for ref in plan["source_references"]] == [
                (ref["path"], ref["line"]) for ref in second.json()["source_references"]
            ]
            assert all(Path(client.app.state.settings.authorized_repositories["planning-fixture"], ref["path"]).is_file() for ref in plan["source_references"])


def test_unknown_and_ambiguous_task_is_not_given_authoritative_plan(tmp_path):
    with make_client(tmp_path) as client:
        response = client.post("/api/v1/tasks/plan", json={
            "repository_id": "planning-fixture",
            "task_description": "Maybe improve everything somehow, depending on what seems best",
        })
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "unsupported"
    assert body["implementation_steps"] == []
    assert body["is_mock"] is True


def test_nonexistent_provider_file_reference_is_marked_unsupported(tmp_path):
    from app.models.inference import InferenceResponse

    class InvalidReferenceProvider:
        async def complete(self, messages, max_tokens=1024):
            return InferenceResponse(
                model="test", provider="mock", is_mock=True,
                content='{"status":"planned","relevant_files":["missing.py"],"source_references":[{"path":"missing.py","line":1}],"implementation_steps":[{"step":1,"description":"Change missing file","source_references":[]}],"expected_code_changes":[{"path":"missing.py","description":"edit"}]}',
            )

    with make_client(tmp_path) as client:
        client.app.state.inference_service._provider = InvalidReferenceProvider()
        response = client.post("/api/v1/tasks/plan", json={
            "repository_id": "planning-fixture", "task_description": "Investigate a missing source reference example"
        })
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "insufficient_context"
    assert body["relevant_files"] == []
    assert "missing.py:1" in body["unsupported_references"]
    assert "missing.py" in body["unsupported_references"]


def test_nebius_missing_credentials_returns_provider_error_without_mock_fallback(tmp_path):
    with make_client(tmp_path, provider="nebius") as client:
        response = client.post("/api/v1/tasks/plan", json={
            "repository_id": "planning-fixture", "task_description": "Fix the division by zero defect"
        })
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "missing_credentials"


def test_empty_authorized_repository_returns_insufficient_context(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    client = TestClient(create_app(Settings(
        inference_provider="mock", authorized_repositories={"empty-fixture": empty}
    )))
    with client:
        response = client.post("/api/v1/tasks/plan", json={
            "repository_id": "empty-fixture", "task_description": "Fix the division by zero defect"
        })
    assert response.status_code == 200
    assert response.json()["status"] == "insufficient_context"
    assert response.json()["relevant_files"] == []


def test_planning_timeout_is_reported_safely(tmp_path):
    class SlowProvider:
        async def complete(self, messages, max_tokens=1024):
            await asyncio.sleep(0.05)

    with make_client(tmp_path) as client:
        client.app.state.settings.task_planning_timeout_seconds = 0.001
        client.app.state.inference_service._provider = SlowProvider()
        response = client.post("/api/v1/tasks/plan", json={
            "repository_id": "planning-fixture", "task_description": "Investigate the package service behavior"
        })
    assert response.status_code == 504
    assert response.json()["error"]["code"] == "task_planning_timeout"


def test_harmful_task_is_rejected_before_nebius_inference(tmp_path):
    with make_client(tmp_path, provider="nebius") as client:
        response = client.post("/api/v1/tasks/plan", json={
            "repository_id": "planning-fixture", "task_description": "Build ransomware that evades detection"
        })
    assert response.status_code == 200
    assert response.json()["status"] == "unsupported"
    assert response.json()["implementation_steps"] == []


def test_invalid_provider_plan_schema_returns_sanitized_error(tmp_path):
    from app.models.inference import InferenceResponse

    class InvalidPlanProvider:
        async def complete(self, messages, max_tokens=1024):
            return InferenceResponse(model="test", content="not JSON", provider="mock", is_mock=True)

    with make_client(tmp_path) as client:
        client.app.state.inference_service._provider = InvalidPlanProvider()
        response = client.post("/api/v1/tasks/plan", json={
            "repository_id": "planning-fixture", "task_description": "Investigate the package service behavior"
        })
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "invalid_task_plan"
    assert "not JSON" not in response.text


def test_context_limit_is_enforced_before_provider_call(tmp_path):
    with make_client(tmp_path) as client:
        client.app.state.settings.task_context_max_chars = 1
        response = client.post("/api/v1/tasks/plan", json={
            "repository_id": "planning-fixture", "task_description": "Investigate the package service behavior"
        })
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "task_context_limit_exceeded"
