"""Security and lifecycle tests for deterministic proposal generation.

These tests parse target source but never import or execute the synthetic repository.
"""

import shutil
from dataclasses import replace
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.errors import ProposalValidationError
from app.main import create_app
from app.models.inference import InferenceResponse
from app.services.mock_inference import MockModelProvider
from app.services.proposal_generation import (
    MAX_PATCH_BYTES,
    TARGET_PATH,
    validate_calculator_acceptance,
    validate_python_syntax,
    validate_relative_paths,
    validate_unified_diff,
)

PLANNING_REPO = Path(__file__).parent / "fixtures" / "planning_repo"
TASK = "Fix the division by zero defect in the calculator"


@pytest.fixture
def proposal_client(tmp_path: Path):
    root = tmp_path / "synthetic-repository"
    shutil.copytree(PLANNING_REPO, root)
    client = TestClient(create_app(Settings(
        _env_file=None,
        nebius_api_key=None,
        inference_provider="mock",
        authorized_repositories={"planning-fixture": root},
    )))
    with client:
        yield client, root


def create_plan(client: TestClient, description: str = TASK) -> dict:
    response = client.post("/api/v1/tasks/plan", json={
        "repository_id": "planning-fixture",
        "task_description": description,
    })
    assert response.status_code == 200
    return response.json()


def create_proposal(client: TestClient, task_id: str, repository_id: str = "planning-fixture"):
    return client.post("/api/v1/proposals/create", json={
        "repository_id": repository_id,
        "task_id": task_id,
        "transformation_id": "calculator-zero-denominator-value-error-v1",
    })


async def simulated_nebius(messages, max_tokens=1024, *, disable_thinking=False, json_mode=False, report_model=True, alter_content=None):
    del disable_thinking
    assert json_mode is True
    mocked = await MockModelProvider().complete(messages, max_tokens)
    content = alter_content if alter_content is not None else mocked.content
    return InferenceResponse(
        model="nvidia/Nemotron-3_5-Lightning", content=content,
        provider="nebius", is_mock=False, completion_status="completed",
        finish_reason="stop", model_reported_by_provider=report_model, latency_ms=12,
    )


def test_valid_calculator_proposal_is_structured_and_review_only(proposal_client):
    client, root = proposal_client
    plan = create_plan(client)
    response = create_proposal(client, plan["task_id"])

    assert response.status_code == 201
    proposal = response.json()
    assert proposal["repository_id"] == "planning-fixture"
    assert proposal["originating_task_id"] == plan["task_id"]
    assert proposal["originating_plan_provider"] == "mock"
    assert proposal["transformation_id"] == "calculator-zero-denominator-value-error-v1"
    assert proposal["target_files"][0]["path"] == TARGET_PATH
    assert len(proposal["target_files"][0]["original_sha256"]) == 64
    assert "raise ValueError" in proposal["unified_diff"]
    assert proposal["provider"] == "mock" and proposal["is_mock"] is True
    assert proposal["lifecycle_state"] == "awaiting_review"
    assert proposal["human_approval_required"] is True
    assert proposal["static_validation_status"] == "passed"
    assert proposal["runtime_validation_status"] == "not_run"
    assert all(item["status"] == "passed" for item in proposal["validation_findings"] if item["check"] != "runtime_isolation")
    runtime = next(item for item in proposal["validation_findings"] if item["check"] == "runtime_isolation")
    assert runtime["status"] == "not_run"
    assert "not executed" in proposal["runtime_validation_reason"]
    assert (root / TARGET_PATH).read_text(encoding="utf-8") == (
        "def divide(numerator, denominator):\n    return numerator / denominator\n"
    )


def test_generated_diff_passes_strict_unified_diff_validation(proposal_client):
    client, _ = proposal_client
    plan = create_plan(client)
    proposal = create_proposal(client, plan["task_id"]).json()
    validate_unified_diff(proposal["unified_diff"], [TARGET_PATH])
    assert proposal["unified_diff"].startswith(f"--- a/{TARGET_PATH}\n+++ b/{TARGET_PATH}\n@@ ")


def test_original_repository_is_unchanged_after_proposal(proposal_client):
    client, root = proposal_client
    target = root / TARGET_PATH
    before = target.read_bytes()
    plan = create_plan(client)
    assert create_proposal(client, plan["task_id"]).status_code == 201
    assert target.read_bytes() == before


def test_source_revision_mismatch_fails_closed(proposal_client):
    client, root = proposal_client
    plan = create_plan(client)
    (root / TARGET_PATH).write_text(
        "def divide(numerator, denominator):\n    return numerator / denominator  # changed\n",
        encoding="utf-8",
    )
    response = create_proposal(client, plan["task_id"])
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "proposal_source_stale"


def test_unauthorized_repository_and_missing_plan_are_rejected(proposal_client):
    client, _ = proposal_client
    plan = create_plan(client)
    unauthorized = create_proposal(client, plan["task_id"], "elsewhere")
    missing = create_proposal(client, "unknown-plan-id")
    assert unauthorized.status_code == 404
    assert unauthorized.json()["error"]["code"] == "repository_not_found"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "task_plan_not_found"


@pytest.mark.parametrize("path", [
    "../outside.py",
    "package/../../outside.py",
    "/etc/passwd",
    "C:/outside.py",
    r"C:\\outside.py",
    "\\\\server\\share\\outside.py",
])
def test_absolute_and_traversal_patch_paths_are_rejected(path):
    with pytest.raises(ProposalValidationError):
        validate_relative_paths([path])


def test_duplicate_conflicting_file_modifications_are_rejected():
    with pytest.raises(ProposalValidationError, match="same file"):
        validate_relative_paths([TARGET_PATH, TARGET_PATH])


def test_symlink_escape_target_is_rejected(proposal_client, tmp_path: Path):
    client, root = proposal_client
    plan = create_plan(client)
    target = root / TARGET_PATH
    outside = tmp_path / "outside.py"
    outside.write_text("secret = 'outside'\n", encoding="utf-8")
    target.unlink()
    try:
        target.symlink_to(outside)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"This Windows environment cannot create a test symlink: {exc}")

    response = create_proposal(client, plan["task_id"])
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "proposal_validation_failed"
    assert "outside" not in response.text


@pytest.mark.parametrize("path", [".env", ".env.production", "credentials.json", "secrets/token.txt", "id_rsa.pem"])
def test_sensitive_file_targets_are_rejected(path):
    with pytest.raises(ProposalValidationError, match="Sensitive files"):
        validate_relative_paths([path])


def test_malformed_unified_diff_is_rejected():
    malformed = f"--- a/{TARGET_PATH}\n+++ b/{TARGET_PATH}\n@@ malformed @@\n+raise ValueError()\n"
    with pytest.raises(ProposalValidationError, match="malformed hunk"):
        validate_unified_diff(malformed, [TARGET_PATH])


def test_oversized_patch_is_rejected():
    oversized = "x" * (MAX_PATCH_BYTES + 1)
    with pytest.raises(ProposalValidationError, match="size limit"):
        validate_unified_diff(oversized, [TARGET_PATH])


def test_unsupported_task_does_not_receive_a_proposal(proposal_client):
    client, _ = proposal_client
    plan = create_plan(client, "Maybe improve everything in the synthetic repository")
    assert plan["status"] == "unsupported"
    response = create_proposal(client, plan["task_id"])
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "proposal_validation_failed"


def test_static_syntax_and_acceptance_validation_do_not_execute_source():
    valid = (
        "def divide(numerator, denominator):\n"
        "    if denominator == 0:\n"
        "        raise ValueError('denominator must not be zero')\n"
        "    return numerator / denominator\n"
    )
    assert validate_python_syntax(valid) is True
    assert validate_calculator_acceptance(valid) is True
    assert validate_python_syntax("def broken(:\n") is False
    assert validate_calculator_acceptance("def divide(a, b):\n    return a / b\n") is False


def test_oversized_target_source_is_rejected_before_proposal_generation(proposal_client):
    client, root = proposal_client
    plan = create_plan(client)
    (root / TARGET_PATH).write_bytes(b"x" * 256_001)
    response = create_proposal(client, plan["task_id"])
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "proposal_validation_failed"


def test_request_validation_retrieval_and_no_apply_endpoint(proposal_client):
    client, _ = proposal_client
    invalid_request = client.post("/api/v1/proposals/create", json={"repository_id": "planning-fixture"})
    assert invalid_request.status_code == 422
    plan = create_plan(client)
    response = create_proposal(client, plan["task_id"])
    proposal = response.json()
    retrieved = client.get(f"/api/v1/proposals/{proposal['proposal_id']}")
    assert retrieved.status_code == 200
    assert retrieved.json() == proposal
    assert client.post(f"/api/v1/proposals/{proposal['proposal_id']}/apply").status_code == 404
    assert client.get("/api/v1/proposals/not-a-uuid").status_code == 422


def test_valid_trusted_nebius_plan_can_create_only_the_allowlisted_proposal(tmp_path):
    root = tmp_path / "synthetic-repository"
    shutil.copytree(PLANNING_REPO, root)
    client = TestClient(create_app(Settings(
        _env_file=None, nebius_api_key=None, inference_provider="nebius",
        nebius_model="nvidia/Nemotron-3_5-Lightning",
        authorized_repositories={"planning-fixture": root},
    )))
    with client:
        original_source = (root / TARGET_PATH).read_bytes()
        client.app.state.inference_service._provider.complete = simulated_nebius
        plan = create_plan(client)
        assert plan["provider"] == "nebius" and plan["is_mock"] is False
        assert plan["human_approval_required"] is True and plan["execution_status"] == "not_started"
        response = create_proposal(client, plan["task_id"])
        assert response.status_code == 201, response.text
        proposal = response.json()
        assert proposal["originating_plan_provider"] == "nebius"
        assert proposal["provider"] == "mock" and proposal["is_mock"] is True
        assert proposal["human_approval_required"] is True
        assert proposal["runtime_validation_status"] == "not_run"
        assert proposal["lifecycle_state"] == "awaiting_review"
        assert (root / TARGET_PATH).read_bytes() == original_source


def test_client_cannot_forge_plan_provider_or_validation_metadata(proposal_client):
    client, _ = proposal_client
    plan = create_plan(client)
    response = client.post("/api/v1/proposals/create", json={
        "repository_id": "planning-fixture", "task_id": plan["task_id"],
        "transformation_id": "calculator-zero-denominator-value-error-v1",
        "provider": "nebius", "is_mock": False, "status": "planned",
        "unsupported_references": [], "source_references_validated": True,
    })
    assert response.status_code == 201
    assert response.json()["originating_plan_provider"] == "mock"


def test_modified_server_stored_plan_metadata_fails_integrity_check(proposal_client):
    client, _ = proposal_client
    plan = create_plan(client)
    store = client.app.state.task_plan_store
    record = store._records[plan["task_id"]]
    altered_plan = record.plan.model_copy(update={"provider": "nebius", "is_mock": False})
    store._records[plan["task_id"]] = replace(record, plan=altered_plan)
    response = create_proposal(client, plan["task_id"])
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "proposal_validation_failed"


def test_stale_analysis_snapshot_is_rejected_even_when_calculator_target_is_unchanged(proposal_client):
    client, root = proposal_client
    plan = create_plan(client)
    dependency_file = root / "package/dependencies.py"
    dependency_file.write_text(dependency_file.read_text(encoding="utf-8") + "\n# changed snapshot\n", encoding="utf-8")
    response = create_proposal(client, plan["task_id"])
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "proposal_source_stale"


def test_unsupported_transformation_is_rejected(proposal_client):
    client, _ = proposal_client
    plan = create_plan(client)
    response = client.post("/api/v1/proposals/create", json={
        "repository_id": "planning-fixture", "task_id": plan["task_id"],
        "transformation_id": "arbitrary-model-recommendation",
    })
    assert response.status_code == 422


def test_plan_with_unsupported_citation_cannot_create_proposal(tmp_path):
    root = tmp_path / "synthetic-repository"
    shutil.copytree(PLANNING_REPO, root)
    client = TestClient(create_app(Settings(
        _env_file=None, nebius_api_key=None, inference_provider="nebius",
        nebius_model="nvidia/Nemotron-3_5-Lightning",
        authorized_repositories={"planning-fixture": root},
    )))

    async def invalid_evidence(messages, max_tokens=1024, *, disable_thinking=False, json_mode=False):
        del disable_thinking
        assert json_mode
        mocked = await MockModelProvider().complete(messages, max_tokens)
        content = json.loads(mocked.content)
        content["source_references"].append({"path": "package/calculator.py", "line": 999})
        return InferenceResponse(
            model="nvidia/Nemotron-3_5-Lightning", content=json.dumps(content),
            provider="nebius", is_mock=False, completion_status="completed",
            finish_reason="stop", model_reported_by_provider=True,
        )

    with client:
        client.app.state.inference_service._provider.complete = invalid_evidence
        plan = create_plan(client)
        assert plan["status"] == "insufficient_context"
        assert plan["unsupported_references"] == ["package/calculator.py:999"]
        response = create_proposal(client, plan["task_id"])
        assert response.status_code == 422


def test_unverified_nebius_model_identity_is_rejected_before_plan_storage(tmp_path):
    root = tmp_path / "synthetic-repository"
    shutil.copytree(PLANNING_REPO, root)
    client = TestClient(create_app(Settings(
        _env_file=None, nebius_api_key=None, inference_provider="nebius",
        nebius_model="nvidia/Nemotron-3_5-Lightning",
        authorized_repositories={"planning-fixture": root},
    )))
    with client:
        async def unverified(messages, max_tokens=1024, *, disable_thinking=False, json_mode=False):
            return await simulated_nebius(messages, max_tokens, disable_thinking=disable_thinking,
                                          json_mode=json_mode, report_model=False)
        client.app.state.inference_service._provider.complete = unverified
        response = client.post("/api/v1/tasks/plan", json={
            "repository_id": "planning-fixture", "task_description": TASK,
        })
        assert response.status_code == 502
        assert response.json()["error"]["code"] == "model_provider_error"
