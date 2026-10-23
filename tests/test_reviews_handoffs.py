"""Local review and handoff tests use only copied synthetic repositories.

These tests exercise the DevRelay service, never import or execute fixture source.
"""

import hashlib
import shutil
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.main import create_app
from app.models.runtime_validation import SandboxExecutionResult, SandboxReadiness, SandboxReadinessCheck
from app.services.proposal_generation import TARGET_PATH
from app.services.runtime_validation import TEST_FILE_PATH

FIXTURE = Path(__file__).parent / "fixtures" / "planning_repo"
TASK = "Fix the division by zero defect in the calculator"


@pytest.fixture
def local_client(tmp_path: Path):
    root = tmp_path / "repo"
    shutil.copytree(FIXTURE, root)
    settings = Settings(
        _env_file=None,
        nebius_api_key=None,
        environment="development",
        inference_provider="mock",
        enable_local_reviews=True,
        authorized_repositories={"planning-fixture": root},
    )
    client = TestClient(create_app(settings), base_url="http://127.0.0.1", client=("127.0.0.1", 54123))
    with client:
        yield client, root


def make_proposal(client: TestClient) -> dict:
    plan_response = client.post("/api/v1/tasks/plan", json={
        "repository_id": "planning-fixture", "task_description": TASK,
    })
    assert plan_response.status_code == 200
    proposal_response = client.post("/api/v1/proposals/create", json={
        "repository_id": "planning-fixture", "task_id": plan_response.json()["task_id"],
    })
    assert proposal_response.status_code == 201
    return proposal_response.json()


def review_body(proposal: dict, decision: str = "approve") -> dict:
    return {
        "proposal_id": proposal["proposal_id"],
        "decision": decision,
        "reviewer_identifier": "local-reviewer",
        "justification": "Reviewed the static diff and its documented limitations.",
        "proposal_version": proposal["version"],
        "source_sha256": proposal["target_files"][0]["original_sha256"],
        "diff_sha256": proposal["diff_sha256"],
        "outstanding_questions": ["Run the calculator tests in an isolated environment."],
    }


def approve_proposal(client: TestClient) -> dict:
    proposal = make_proposal(client)
    response = client.post("/api/v1/reviews", json=review_body(proposal))
    assert response.status_code == 201
    approved = client.get(f"/api/v1/proposals/{proposal['proposal_id']}").json()
    assert approved["lifecycle_state"] == "review_approved"
    return approved


def runtime_body(proposal: dict) -> dict:
    return {
        "proposal_id": proposal["proposal_id"],
        "proposal_version": proposal["version"],
        "source_sha256": proposal["target_files"][0]["original_sha256"],
        "diff_sha256": proposal["diff_sha256"],
        "test_case": "calculator_unit_tests",
        "authorization": {
            "authorizer_identifier": "local_authorizer",
            "purpose": "Validate the reviewed calculator proposal.",
        },
    }


class MockSandboxExecutor:
    """Test double only; it never launches a process or executes fixture code."""

    def __init__(self, result: SandboxExecutionResult, *, cleanup_ok: bool = True) -> None:
        self.result = result
        self.cleanup_ok = cleanup_ok
        self.execute_calls = []
        self.cleanup_calls = []

    def readiness(self, *, enabled: bool, environment: str) -> SandboxReadiness:
        checks = [SandboxReadinessCheck(name="mock_boundary", status="passed", detail="Mocked boundary only; no sandbox was started.")]
        return SandboxReadiness(
            enabled=enabled,
            environment=environment,
            available=True,
            status="ready",
            checks=checks,
            limitations=["This readiness result exists only inside a unit test."],
        )

    def execute(self, evidence_id, sandbox_input):
        self.execute_calls.append((evidence_id, sandbox_input))
        return self.result

    def cleanup(self, evidence_id):
        self.cleanup_calls.append(evidence_id)
        return self.cleanup_ok


def test_review_feature_is_disabled_by_default(tmp_path: Path):
    root = tmp_path / "repo"
    shutil.copytree(FIXTURE, root)
    app = create_app(Settings(_env_file=None, nebius_api_key=None, inference_provider="mock", authorized_repositories={"planning-fixture": root}))
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 54123)) as client:
        assert client.get("/api/v1/reviews/status").json()["enabled"] is False
        assert client.post("/api/v1/reviews", content="{}").status_code == 404


def test_runtime_validation_is_disabled_by_default_and_readiness_is_honest(local_client):
    client, _ = local_client
    readiness = client.get("/api/v1/runtime-validation/readiness")
    assert readiness.status_code == 200
    assert readiness.json()["enabled"] is False
    assert readiness.json()["status"] == "disabled"
    assert readiness.json()["available"] is False
    assert any(check["name"] == "linux_sandbox_host" and check["status"] == "failed" for check in readiness.json()["checks"])
    assert "C:\\" not in readiness.text and str(Path.cwd()) not in readiness.text
    response = client.post("/api/v1/runtime-validation", json={})
    assert response.status_code == 404


def test_runtime_authorization_records_unavailable_run_once_and_links_handoff(local_client):
    client, root = local_client
    original_source = (root / TARGET_PATH).read_bytes()
    settings = client.app.state.settings
    client.app.state.settings = settings.model_copy(update={"enable_isolated_runtime_validation": True})
    proposal = make_proposal(client)
    body = runtime_body(proposal)
    assert client.post("/api/v1/runtime-validation", json=body).status_code == 422
    assert client.post("/api/v1/reviews", json=review_body(proposal)).status_code == 201
    approved = client.get(f"/api/v1/proposals/{proposal['proposal_id']}").json()
    assert approved["lifecycle_state"] == "review_approved"
    body = runtime_body(approved)

    stale = {**body, "proposal_version": body["proposal_version"] + 1}
    assert client.post("/api/v1/runtime-validation", json=stale).status_code == 409
    stale_hash = {**body, "source_sha256": "0" * 64}
    assert client.post("/api/v1/runtime-validation", json=stale_hash).status_code == 409
    missing_authorization = {key: value for key, value in body.items() if key != "authorization"}
    assert client.post("/api/v1/runtime-validation", json=missing_authorization).status_code == 422
    unsupported_case = {**body, "test_case": "arbitrary_shell"}
    assert client.post("/api/v1/runtime-validation", json=unsupported_case).status_code == 422
    arbitrary_command = {**body, "command": "python attacker.py"}
    assert client.post("/api/v1/runtime-validation", json=arbitrary_command).status_code == 422

    response = client.post("/api/v1/runtime-validation", json=body)
    assert response.status_code == 202
    evidence = response.json()
    assert evidence["status"] == "sandbox_unavailable"
    assert evidence["authorizer_identifier"] == "local_authorizer"
    assert evidence["authorizer_identity_status"] == "unverified_local_development"
    assert evidence["test_command_id"] == "calculator_pytest_suite_v1"
    assert evidence["exit_code"] is evidence["duration_ms"] is None
    assert evidence["stdout"] == evidence["stderr"] == ""
    assert evidence["original_repository_modified"] is False
    assert evidence["code_applied_to_original"] is False
    assert "C:\\" not in response.text and str(Path.cwd()) not in response.text
    assert client.get(f"/api/v1/runtime-validation/{evidence['evidence_id']}").json() == evidence
    assert client.post("/api/v1/runtime-validation", json=body).status_code == 409

    handoff_response = client.post("/api/v1/handoffs", json={"proposal_id": proposal["proposal_id"]})
    assert handoff_response.status_code == 201
    report = handoff_response.json()
    assert report["validation_and_risks"]["runtime_tests_status"] == "sandbox_unavailable"
    assert report["runtime_execution"]["evidence_id"] == evidence["evidence_id"]
    assert report["runtime_execution"]["source_sha256"] == body["source_sha256"]
    assert report["runtime_execution"]["diff_sha256"] == body["diff_sha256"]
    assert report["runtime_execution"]["test_command_id"] == "calculator_pytest_suite_v1"
    assert report["runtime_execution"]["exit_code"] is None
    assert report["runtime_execution"]["remaining_work"]
    assert (root / TARGET_PATH).read_bytes() == original_source


def test_runtime_snapshot_rejects_malicious_proposal_target(local_client):
    client, _ = local_client
    client.app.state.settings = client.app.state.settings.model_copy(update={"enable_isolated_runtime_validation": True})
    approved = approve_proposal(client)
    proposal_id = UUID(approved["proposal_id"])
    stored = client.app.state.proposal_store.get(proposal_id)
    malicious_target = stored.target_files[0].model_copy(update={"path": "../outside.py"})
    client.app.state.proposal_store.put(stored.model_copy(update={"target_files": [malicious_target]}))
    response = client.post("/api/v1/runtime-validation", json=runtime_body(approved))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "proposal_validation_failed"


def test_mocked_executor_timeout_bounds_logs_redacts_paths_and_cleans_up(local_client):
    client, root = local_client
    client.app.state.settings = client.app.state.settings.model_copy(update={"enable_isolated_runtime_validation": True})
    approved = approve_proposal(client)
    fake = MockSandboxExecutor(SandboxExecutionResult(
        status="timed_out", duration_ms=600_000, stdout="x" * 20_000,
        stderr=r"C:\Users\someone\workspace\test.py nvapi-" + "A" * 20,
        failure_reason=r"Timed out at C:\Users\someone\workspace\test.py",
        sandbox_summary="Mocked timeout result.",
    ))
    client.app.state.runtime_validation_executor = fake
    response = client.post("/api/v1/runtime-validation", json=runtime_body(approved))
    assert response.status_code == 202
    evidence = response.json()
    assert evidence["status"] == "timed_out"
    assert len(evidence["stdout"].encode("utf-8")) <= 8_192
    assert "C:\\" not in evidence["stderr"] and "C:\\" not in evidence["failure_reason"]
    assert "[redacted]" in evidence["stderr"]
    assert len(fake.execute_calls) == len(fake.cleanup_calls) == 1
    sandbox_input = fake.execute_calls[0][1]
    assert set(sandbox_input.files) == {TARGET_PATH, TEST_FILE_PATH}
    assert sandbox_input.test_command_id == "calculator_pytest_suite_v1"
    assert (root / TARGET_PATH).read_text(encoding="utf-8") == "def divide(numerator, denominator):\n    return numerator / denominator\n"


def test_mocked_executor_cleanup_failure_cannot_report_success(local_client):
    client, _ = local_client
    client.app.state.settings = client.app.state.settings.model_copy(update={"enable_isolated_runtime_validation": True})
    approved = approve_proposal(client)
    fake = MockSandboxExecutor(SandboxExecutionResult(
        status="failed", exit_code=1, stderr="simulated failure", sandbox_summary="Mock sandbox."),
        cleanup_ok=False,
    )
    client.app.state.runtime_validation_executor = fake
    evidence = client.post("/api/v1/runtime-validation", json=runtime_body(approved)).json()
    assert evidence["status"] == "failed"
    assert "cleanup could not be verified" in evidence["failure_reason"]
    assert fake.cleanup_calls


@pytest.mark.parametrize(("decision", "state"), [
    ("approve", "review_approved"),
    ("request_changes", "changes_requested"),
    ("reject", "rejected"),
])
def test_review_decisions_are_versioned_unverified_and_audited(local_client, decision: str, state: str):
    client, root = local_client
    source_path = root / TARGET_PATH
    original = source_path.read_bytes()
    proposal = make_proposal(client)
    response = client.post("/api/v1/reviews", json=review_body(proposal, decision))
    assert response.status_code == 201
    review = response.json()
    assert review["reviewer_identity_status"] == "unverified_local_development"
    assert review["proposal_version"] == proposal["version"]
    assert review["proposal_lifecycle_state"] == state
    assert review["runtime_validation_status"] == "not_run"
    assert source_path.read_bytes() == original

    current = client.get(f"/api/v1/proposals/{proposal['proposal_id']}").json()
    assert current["lifecycle_state"] == state
    assert current["version"] == proposal["version"] + 1
    assert client.post(f"/api/v1/proposals/{proposal['proposal_id']}/apply", json={}).status_code == 404

    history = client.get(f"/api/v1/reviews/{proposal['proposal_id']}").json()
    assert len(history["reviews"]) == len(history["audit_events"]) == 1
    event = history["audit_events"][0]
    assert event["previous_state"] == "awaiting_review"
    assert event["new_state"] == state
    assert event["source_sha256"] == proposal["target_files"][0]["original_sha256"]
    assert event["diff_sha256"] == proposal["diff_sha256"]


def test_blank_justification_and_invalid_decision_are_rejected(local_client):
    client, _ = local_client
    proposal = make_proposal(client)
    blank = review_body(proposal)
    blank["justification"] = "  \n  "
    assert client.post("/api/v1/reviews", json=blank).status_code == 422
    invalid = review_body(proposal)
    invalid["decision"] = "apply"
    assert client.post("/api/v1/reviews", json=invalid).status_code == 422
    sensitive = review_body(proposal)
    sensitive["justification"] = "api_key=example-sensitive-value"
    assert client.post("/api/v1/reviews", json=sensitive).status_code == 422


@pytest.mark.parametrize(("reviewer_identifier", "expected_status"), [
    ("demo_reviewer", 201),
    ("Demo Reviewer", 422),
    ("api_key=example-sensitive-value", 422),
])
def test_reviewer_identifier_format_is_enforced(local_client, reviewer_identifier: str, expected_status: int):
    client, _ = local_client
    proposal = make_proposal(client)
    body = review_body(proposal)
    body["reviewer_identifier"] = reviewer_identifier
    response = client.post("/api/v1/reviews", json=body)
    assert response.status_code == expected_status
    if expected_status == 201:
        assert response.json()["reviewer_identifier"] == "demo_reviewer"


def test_unknown_proposal_and_stale_revision_are_rejected(local_client):
    client, root = local_client
    unknown = review_body({
        "proposal_id": str(uuid4()), "version": 1,
        "target_files": [{"original_sha256": "a" * 64}], "diff_sha256": "b" * 64,
    })
    assert client.post("/api/v1/reviews", json=unknown).status_code == 404

    proposal = make_proposal(client)
    stale_version = review_body(proposal)
    stale_version["proposal_version"] += 1
    assert client.post("/api/v1/reviews", json=stale_version).status_code == 409
    stale_hash = review_body(proposal)
    stale_hash["diff_sha256"] = "0" * 64
    assert client.post("/api/v1/reviews", json=stale_hash).status_code == 409
    (root / TARGET_PATH).write_text("def divide(a, b):\n    return a / b  # changed\n", encoding="utf-8")
    assert client.post("/api/v1/reviews", json=review_body(proposal)).status_code == 409
    audit = client.get(f"/api/v1/reviews/{proposal['proposal_id']}").json()["audit_events"]
    assert len(audit) == 3
    assert audit[-1]["outcome"] == "rejected"
    assert "source revision is stale" in audit[-1]["failure_reason"]


def test_conflicting_second_decision_and_oversized_body_are_rejected(local_client):
    client, _ = local_client
    proposal = make_proposal(client)
    assert client.post("/api/v1/reviews", json=review_body(proposal)).status_code == 201
    second = review_body(proposal, "reject")
    second["proposal_version"] += 1
    assert client.post("/api/v1/reviews", json=second).status_code == 409
    assert client.post("/api/v1/reviews", content="x" * 16_385).status_code == 413


def test_handoff_is_traceable_mock_labeled_and_never_claims_runtime_tests(local_client):
    client, root = local_client
    source = (root / TARGET_PATH).read_bytes()
    proposal = make_proposal(client)
    review = review_body(proposal)
    review["reviewer_identifier"] = "demo_reviewer"
    review["justification"] = "Reviewed the static change and confirmed no code was run."
    review["outstanding_questions"] = ["Confirm behavior for non-numeric input."]
    recorded = client.post("/api/v1/reviews", json=review)
    assert recorded.status_code == 201

    generated = client.post("/api/v1/handoffs", json={"proposal_id": proposal["proposal_id"]})
    assert generated.status_code == 201
    report = generated.json()
    assert report["provider"] == "mock" and report["is_mock"] is True
    assert report["task"]["proposal_lifecycle_state"] == "review_approved"
    assert report["proposed_change"]["target_files"][0]["path"] == TARGET_PATH
    assert report["proposed_change"]["source_revision_status"] == "current"
    assert report["technical_understanding"]["relevant_functions"]
    assert report["human_decisions"][0]["reviewer_identity_status"] == "unverified_local_development"
    assert report["human_decisions"][0]["reviewer_identifier"] == "demo_reviewer"
    assert report["human_decisions"][0]["justification"] == "Reviewed the static change and confirmed no code was run."
    assert report["human_decisions"][0]["timestamp"] == recorded.json()["timestamp"]
    assert report["outstanding_questions"] == ["Confirm behavior for non-numeric input."]
    assert report["validation_and_risks"]["runtime_tests_status"] == "not_run"
    assert client.get(f"/api/v1/handoffs/{report['report_id']}").json() == report
    assert (root / TARGET_PATH).read_bytes() == source


def test_review_routes_reject_non_loopback_clients(local_client):
    _, root = local_client
    app = create_app(Settings(
        _env_file=None,
        nebius_api_key=None,
        environment="development", inference_provider="mock", enable_local_reviews=True,
        authorized_repositories={"planning-fixture": root},
    ))
    with TestClient(app, base_url="http://127.0.0.1", client=("192.0.2.10", 54123)) as remote_client:
        response = remote_client.get("/api/v1/reviews/status")
        assert response.status_code == 403


def test_review_routes_reject_cross_site_browser_origins(local_client):
    client, _ = local_client
    response = client.get("/api/v1/reviews/status", headers={"Origin": "https://attacker.example"})
    assert response.status_code == 403


def test_review_flag_cannot_be_enabled_outside_development(tmp_path: Path):
    root = tmp_path / "repo"
    shutil.copytree(FIXTURE, root)
    with pytest.raises(ValidationError, match="only be enabled in development"):
        Settings(_env_file=None, environment="production", enable_local_reviews=True, authorized_repositories={"planning-fixture": root})
