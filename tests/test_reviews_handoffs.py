"""Local review and handoff tests use only copied synthetic repositories.

These tests exercise the DevRelay service, never import or execute fixture source.
"""

import hashlib
import shutil
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.main import create_app
from app.services.proposal_generation import TARGET_PATH

FIXTURE = Path(__file__).parent / "fixtures" / "planning_repo"
TASK = "Fix the division by zero defect in the calculator"


@pytest.fixture
def local_client(tmp_path: Path):
    root = tmp_path / "repo"
    shutil.copytree(FIXTURE, root)
    settings = Settings(
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


def test_review_feature_is_disabled_by_default(tmp_path: Path):
    root = tmp_path / "repo"
    shutil.copytree(FIXTURE, root)
    app = create_app(Settings(inference_provider="mock", authorized_repositories={"planning-fixture": root}))
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 54123)) as client:
        assert client.get("/api/v1/reviews/status").json()["enabled"] is False
        assert client.post("/api/v1/reviews", content="{}").status_code == 404


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
        Settings(environment="production", enable_local_reviews=True, authorized_repositories={"planning-fixture": root})
