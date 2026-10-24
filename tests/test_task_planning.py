import asyncio
import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.models.inference import InferenceResponse, InferenceUsage
from app.services.mock_inference import MockModelProvider


PLANNING_REPO = Path(__file__).parent / "fixtures" / "planning_repo"


def make_client(tmp_path: Path, *, provider="mock", **settings_overrides) -> TestClient:
    root = tmp_path / "repo"
    shutil.copytree(PLANNING_REPO, root)
    settings = Settings(
        _env_file=None,
        nebius_api_key=None,
        inference_provider=provider,
        authorized_repositories={"planning-fixture": root},
        **settings_overrides,
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
            assert plan["inference_diagnostics"]["provider"] == "mock"
            assert plan["inference_diagnostics"]["is_mock"] is True
            assert plan["inference_diagnostics"]["completion_status"] == "completed"
            assert plan["inference_diagnostics"]["usage"] is None
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
                content='{"status":"planned","relevant_files":["missing.py"],"source_references":[{"path":"missing.py","line":1}],"implementation_steps":[{"step":1,"description":"Change missing file","source_references":[]}],"expected_code_changes":[{"path":"missing.py","description":"edit"}],"risks":[],"dependencies":[],"validation_requirements":[],"assumptions":[]}',
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
    with make_client(tmp_path, provider="nebius", nebius_live_inference_enabled=True) as client:
        response = client.post("/api/v1/tasks/plan", json={
            "repository_id": "planning-fixture", "task_description": "Fix the division by zero defect"
        })
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "missing_credentials"


def test_empty_authorized_repository_returns_insufficient_context(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    client = TestClient(create_app(Settings(
        _env_file=None, nebius_api_key=None,
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


@pytest.mark.parametrize(
    ("content", "diagnostic", "public_code"),
    [
        ("not JSON DO_NOT_LOG", "invalid_json_syntax", "invalid_task_plan"),
        ("[]", "incorrect_json_root_type", "invalid_task_plan"),
        ('{"status":"planned","private_value":"DO_NOT_LOG"}', "missing_required_field", "invalid_task_plan"),
        (
            json.dumps({"status": "planned", "relevant_files": {"private": "DO_NOT_LOG"}}),
            "incorrect_field_type", "invalid_task_plan",
        ),
        ('{"status":"DO_NOT_LOG","relevant_files":[],"source_references":[],"implementation_steps":[],"expected_code_changes":[],"risks":[],"dependencies":[],"validation_requirements":[],"assumptions":[]}', "invalid_enum_value", "invalid_task_plan"),
        (
            json.dumps({"status": "planned", "relevant_files": [f"file{i}.py" for i in range(6)], "source_references": [], "implementation_steps": [], "expected_code_changes": [], "risks": [], "dependencies": [], "validation_requirements": [], "assumptions": []}),
            "excessive_item_count", "invalid_task_plan",
        ),
        ("", "empty_model_content", "empty_model_response"),
    ],
)
def test_invalid_provider_plan_has_safe_structured_diagnostics(tmp_path, capsys, content, diagnostic, public_code):
    class InvalidPlanProvider:
        async def complete(self, messages, max_tokens=1024):
            return InferenceResponse(model="test", content=content, provider="mock", is_mock=True)

    with make_client(tmp_path) as client:
        client.app.state.inference_service._provider = InvalidPlanProvider()
        response = client.post("/api/v1/tasks/plan", json={
            "repository_id": "planning-fixture", "task_description": "Investigate the package service behavior"
        })
    assert response.status_code == 502
    assert response.json()["error"]["code"] == public_code
    logs = capsys.readouterr().err
    assert diagnostic in logs
    assert "DO_NOT_LOG" not in logs
    assert "DO_NOT_LOG" not in response.text


def test_schema_valid_plan_with_unknown_evidence_is_rejected_as_insufficient_context(tmp_path, capsys):
    content = json.dumps({
        "status": "planned", "relevant_files": ["secret-sentinel.py"],
        "source_references": [{"path": "secret-sentinel.py", "line": 900}],
        "implementation_steps": [{"step": 1, "description": "Inspect source", "source_references": []}],
        "expected_code_changes": [{"path": "secret-sentinel.py", "description": "Fix defect"}],
        "risks": [], "dependencies": [], "validation_requirements": [], "assumptions": [],
    })

    class InvalidEvidenceProvider:
        async def complete(self, messages, max_tokens=1024):
            return InferenceResponse(model="test", content=content, provider="mock", is_mock=True)

    with make_client(tmp_path) as client:
        client.app.state.inference_service._provider = InvalidEvidenceProvider()
        response = client.post("/api/v1/tasks/plan", json={
            "repository_id": "planning-fixture", "task_description": "Investigate the package service behavior"
        })
    assert response.status_code == 200
    assert response.json()["status"] == "insufficient_context"
    assert response.json()["human_approval_required"] is True
    assert response.json()["execution_status"] == "not_started"
    logs = capsys.readouterr().err
    assert "unknown_file_path" in logs
    assert "source_reference_not_in_analysis" in logs
    assert "expected_change_path_not_in_analysis" in logs
    assert "secret-sentinel.py" not in logs


def test_minimal_schema_valid_plan_uses_fixture_source_references(tmp_path):
    content = json.dumps({
        "status": "planned",
        "relevant_files": ["package/calculator.py", "tests/test_calculator.py"],
        "source_references": [
            {"path": "package/calculator.py", "line": 1, "end_line": 2},
            {"path": "tests/test_calculator.py", "line": 1, "end_line": None},
        ],
        "implementation_steps": [{
            "step": 1, "description": "Review divide behavior and define the zero-denominator case.",
            "source_references": [{"path": "package/calculator.py", "line": 1, "end_line": 2}],
        }],
        "expected_code_changes": [{"path": "package/calculator.py", "description": "Handle a zero denominator."}],
        "risks": ["Expected behavior for division by zero is unspecified."],
        "dependencies": [],
        "validation_requirements": ["Run tests/test_calculator.py."],
        "assumptions": [],
    })

    class ValidPlanProvider:
        async def complete(self, messages, max_tokens=1024):
            return InferenceResponse(model="test", content=content, provider="mock", is_mock=True)

    with make_client(tmp_path) as client:
        client.app.state.inference_service._provider = ValidPlanProvider()
        response = client.post("/api/v1/tasks/plan", json={
            "repository_id": "planning-fixture", "task_description": "Fix the division by zero defect in the calculator"
        })
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "planned"
    assert body["human_approval_required"] is True
    assert body["execution_status"] == "not_started"
    assert {item["path"] for item in body["source_references"]} == {
        "package/calculator.py", "tests/test_calculator.py",
    }


@pytest.mark.parametrize(
    ("reference", "expected_status"),
    [
        ({"path": "package/calculator.py", "line": 1}, "planned"),
        ({"path": "package/calculator.py", "line": 1, "end_line": 2}, "planned"),
        ({"path": "package/calculator.py", "line": 1, "end_line": 3}, "insufficient_context"),
        ({"path": "package/calculator.py", "line": 99}, "insufficient_context"),
        ({"path": "package/missing.py", "line": 1}, "insufficient_context"),
    ],
)
def test_source_references_require_an_analyzed_start_and_exact_supplied_range(
    tmp_path, reference, expected_status,
):
    content = json.dumps({
        "status": "planned",
        "relevant_files": ["package/calculator.py", "tests/test_calculator.py"],
        "source_references": [reference],
        "implementation_steps": [{"step": 1, "description": "Inspect the calculator definition.", "source_references": [reference]}],
        "expected_code_changes": [{"path": "package/calculator.py", "description": "Handle the zero denominator."}],
        "risks": [], "dependencies": [], "validation_requirements": [], "assumptions": [],
    })

    class ReferenceProvider:
        async def complete(self, messages, max_tokens=1024):
            return InferenceResponse(model="test", content=content, provider="mock", is_mock=True)

    with make_client(tmp_path) as client:
        client.app.state.inference_service._provider = ReferenceProvider()
        response = client.post("/api/v1/tasks/plan", json={
            "repository_id": "planning-fixture", "task_description": "Fix the division by zero defect in the calculator",
        })
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == expected_status
    if expected_status == "planned":
        expected_reference = {"path": reference["path"], "line": reference["line"], "end_line": reference.get("end_line")}
        assert body["source_references"] == [expected_reference]
        assert body["unsupported_references"] == []
    else:
        assert body["source_references"] == []
        assert body["unsupported_references"] == [f"{reference['path']}:{reference['line']}"]
        assert body["human_approval_required"] is True
        assert body["execution_status"] == "not_started"


def test_duplicate_and_partially_valid_citations_separate_verified_and_rejected_evidence(tmp_path):
    valid = {"path": "package/calculator.py", "line": 1}
    invalid = {"path": "package/calculator.py", "line": 1, "end_line": 3}
    content = json.dumps({
        "status": "planned",
        "relevant_files": ["package/calculator.py", "tests/test_calculator.py"],
        "source_references": [valid, valid, invalid],
        "implementation_steps": [{"step": 1, "description": "Inspect the calculator definition.", "source_references": [valid, valid, invalid]}],
        "expected_code_changes": [{"path": "package/calculator.py", "description": "Handle the zero denominator."}],
        "risks": [], "dependencies": [], "validation_requirements": [], "assumptions": [],
    })

    class MixedReferenceProvider:
        async def complete(self, messages, max_tokens=1024):
            return InferenceResponse(model="test", content=content, provider="mock", is_mock=True)

    with make_client(tmp_path) as client:
        client.app.state.inference_service._provider = MixedReferenceProvider()
        response = client.post("/api/v1/tasks/plan", json={
            "repository_id": "planning-fixture", "task_description": "Fix the division by zero defect in the calculator",
        })
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "insufficient_context"
    expected_valid = {"path": valid["path"], "line": valid["line"], "end_line": None}
    assert body["source_references"] == [expected_valid]
    assert body["implementation_steps"][0]["source_references"] == [expected_valid]
    assert body["unsupported_references"] == ["package/calculator.py:1"]
    assert body["human_approval_required"] is True
    assert body["execution_status"] == "not_started"


def test_context_limit_is_enforced_before_provider_call(tmp_path):
    with make_client(tmp_path) as client:
        client.app.state.settings.task_context_max_chars = 1
        response = client.post("/api/v1/tasks/plan", json={
            "repository_id": "planning-fixture", "task_description": "Investigate the package service behavior"
        })
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "task_context_limit_exceeded"


def test_live_provider_structured_plan_returns_only_safe_diagnostics(tmp_path):
    class SimulatedNebiusProvider:
        async def complete(self, messages, max_tokens=1024, *, disable_thinking=False, json_mode=False):
            assert json_mode is True
            deterministic = await MockModelProvider().complete(messages, max_tokens)
            return InferenceResponse(
                model="nvidia/Nemotron-3_5-Lightning", content=deterministic.content,
                provider="nebius", is_mock=False, completion_status="completed",
                finish_reason="stop", model_reported_by_provider=True, latency_ms=275,
                usage=InferenceUsage(input_tokens=280, output_tokens=192, reasoning_tokens=72, total_tokens=472),
            )

    with make_client(tmp_path, provider="nebius") as client:
        client.app.state.inference_service._provider = SimulatedNebiusProvider()
        response = client.post("/api/v1/tasks/plan", json={
            "repository_id": "planning-fixture", "task_description": "Fix the division by zero defect in the calculator",
        })
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "planned"
    assert body["provider"] == "nebius" and body["is_mock"] is False
    assert body["human_approval_required"] is True and body["execution_status"] == "not_started"
    assert body["inference_diagnostics"] == {
        "provider": "nebius", "model": "nvidia/Nemotron-3_5-Lightning", "is_mock": False,
        "completion_status": "completed", "finish_reason": "stop",
        "model_reported_by_provider": True, "latency_ms": 275,
        "usage": {"input_tokens": 280, "output_tokens": 192, "reasoning_tokens": 72, "total_tokens": 472},
    }
    assert all(":" not in reference["path"] for reference in body["source_references"])


def test_planner_uses_compact_json_instructions_and_gates_optional_thinking_control(tmp_path):
    class InspectProvider:
        def __init__(self):
            self.calls = []
            self.model = "nvidia/Nemotron-3_5-Lightning"

        async def complete(self, messages, max_tokens=1024, *, disable_thinking=False, json_mode=False):
            self.calls.append((messages, max_tokens, disable_thinking, json_mode))
            mocked = await MockModelProvider().complete(messages, max_tokens)
            return mocked.model_copy(update={
                "model": self.model,
                "provider": "nebius", "is_mock": False,
                "model_reported_by_provider": True, "finish_reason": "stop",
            })

    with make_client(tmp_path, provider="nebius", nebius_planning_disable_thinking=True) as client:
        provider = InspectProvider()
        client.app.state.inference_service._provider = provider
        payload = {
            "repository_id": "planning-fixture",
            "task_description": "Fix the division by zero defect in the calculator",
        }
        response = client.post("/api/v1/tasks/plan", json=payload)
        assert response.status_code == 200
        assert provider.calls[-1][2:] == (True, True)
        system_prompt = provider.calls[-1][0][0].content
        for required in (
            "exactly one JSON object matching this shape", "No Markdown", "at most 4 steps",
            "5 files", "5 top-level references", "20 references per step", "4 risks", "4 validation requirements",
            "3 assumptions", "Include every key", "status must be exactly one of planned, insufficient_context, or unsupported",
            '"implementation_steps":[{"step":1,"description":"text","source_references":[]}]',
            "positive integer line", "Step descriptions must be 1-1000 characters",
            "expected-code-change descriptions must be 1-500 characters",
            "only supplied references", "Do not invent source",
            "internal reasoning",
        ):
            assert required in system_prompt

        client.app.state.settings.nebius_model = "nvidia/other-model"
        provider.model = "nvidia/other-model"
        response = client.post("/api/v1/tasks/plan", json=payload)
        assert response.status_code == 200
        assert provider.calls[-1][2:] == (False, False)

        client.app.state.settings.inference_provider = "mock"
        client.app.state.settings.nebius_model = "nvidia/Nemotron-3_5-Lightning"
        client.app.state.inference_service._provider = MockModelProvider()
        response = client.post("/api/v1/tasks/plan", json=payload)
        assert response.status_code == 200
        assert provider.calls[-1][2:] == (False, False)


def test_truncated_live_response_is_rejected_before_plan_parsing(tmp_path):
    class TruncatedProvider:
        async def complete(self, messages, max_tokens=1024, *, disable_thinking=False, json_mode=False):
            assert json_mode is True
            return InferenceResponse(
                model="nvidia/Nemotron-3_5-Lightning", provider="nebius", is_mock=False,
                completion_status="incomplete", finish_reason="length",
                content='{"partial secret answer":',
            )

    with make_client(tmp_path, provider="nebius") as client:
        client.app.state.inference_service._provider = TruncatedProvider()
        response = client.post("/api/v1/tasks/plan", json={
            "repository_id": "planning-fixture", "task_description": "Fix the division by zero defect in the calculator",
        })
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "incomplete_model_response"
    assert "partial secret answer" not in response.text


def test_configured_key_echo_is_rejected_before_it_can_enter_a_plan_response(tmp_path):
    class EchoProvider:
        async def complete(self, messages, max_tokens=1024, *, disable_thinking=False, json_mode=False):
            assert json_mode is True
            return InferenceResponse(
                model="nvidia/Nemotron-3_5-Lightning", provider="nebius", is_mock=False,
                content='{"status":"planned","risks":["unit-test-key"]}',
            )

    root = tmp_path / "repo"
    shutil.copytree(PLANNING_REPO, root)
    settings = Settings(
        _env_file=None, inference_provider="nebius", nebius_api_key="unit-test-key",
        authorized_repositories={"planning-fixture": root},
    )
    with TestClient(create_app(settings)) as client:
        client.app.state.inference_service._provider = EchoProvider()
        response = client.post("/api/v1/tasks/plan", json={
            "repository_id": "planning-fixture", "task_description": "Fix the division by zero defect",
        })
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "sensitive_inference_content"
    assert "unit-test-key" not in response.text


def test_credential_like_task_description_is_rejected_before_inference(tmp_path):
    class NeverCallProvider:
        async def complete(self, messages, max_tokens=1024):
            raise AssertionError("Paid provider must not receive credential-like task content")

    with make_client(tmp_path, provider="nebius") as client:
        client.app.state.inference_service._provider = NeverCallProvider()
        response = client.post("/api/v1/tasks/plan", json={
            "repository_id": "planning-fixture", "task_description": "Fix api_key=nvapi-" + "A" * 20,
        })
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "sensitive_inference_content"
    assert "nvapi-" not in response.text
