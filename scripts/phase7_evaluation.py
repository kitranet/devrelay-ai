"""Run the repeatable, offline Phase 7 synthetic calculator evaluation.

This script uses the deterministic mock provider and a temporary copy of the
synthetic fixture. It never imports, executes, or writes to fixture source.
"""

from __future__ import annotations

import hashlib
import json
import argparse
import logging
import shutil
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.models.task import TaskPlan


REPOSITORY_ID = "planning-fixture"
TASK = "Fix the division by zero defect in the calculator"
TRANSFORMATION = "calculator-zero-denominator-value-error-v1"
FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "planning_repo"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
GROUND_TRUTH_RELEVANT_FILES = {
    "package/calculator.py",
    "tests/test_calculator.py",
}


def _tree_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }


def run_evaluation() -> dict[str, object]:
    if not FIXTURE.is_dir():
        raise RuntimeError("The checked-in synthetic planning fixture is missing.")

    # Keep scratch I/O under the workspace: some restricted Windows runners
    # cannot create/clean directories under the OS-managed temporary folder.
    with tempfile.TemporaryDirectory(prefix=".phase7-eval-", dir=REPOSITORY_ROOT) as temp_dir:
        root = Path(temp_dir) / REPOSITORY_ID
        shutil.copytree(FIXTURE, root)
        settings = Settings(
            _env_file=None,
            environment="development",
            inference_provider="mock",
            nebius_api_key=None,
            inference_telemetry_db_path=Path(temp_dir) / "inference-attempts.sqlite3",
            enable_local_reviews=False,
            enable_isolated_runtime_validation=False,
            authorized_repositories={REPOSITORY_ID: root},
        )
        before = _tree_hashes(root)
        checks: dict[str, bool] = {}
        started = time.perf_counter()

        with TestClient(
            create_app(settings), base_url="http://127.0.0.1",
            client=("127.0.0.1", 54123),
        ) as client:
            analysis_response = client.post(
                "/api/v1/repositories/analyze", json={"repository_id": REPOSITORY_ID}
            )
            checks["authorized_repository_analysis"] = analysis_response.status_code == 200
            analysis = analysis_response.json()
            manifests = {item["path"] for item in analysis.get("dependency_manifests", [])}
            dependencies = {
                dependency
                for manifest in analysis.get("dependency_manifests", [])
                for dependency in manifest.get("dependencies", [])
            }
            checks["dependency_manifest_discovery"] = (
                "requirements.txt" in manifests and "pytest>=8" in dependencies
            )

            plan_response = client.post("/api/v1/tasks/plan", json={
                "repository_id": REPOSITORY_ID,
                "task_description": TASK,
            })
            checks["mock_plan_generation"] = plan_response.status_code == 200
            plan_data = plan_response.json()
            plan = TaskPlan.model_validate(plan_data)
            checks["plan_schema_validity"] = True
            checks["mock_provenance_explicit"] = plan.provider == "mock" and plan.is_mock is True
            checks["plan_evidence_grounded"] = (
                plan.status == "planned" and not plan.unsupported_references
                and bool(plan.source_references)
            )
            checks["approval_and_execution_gate"] = (
                plan.human_approval_required is True and plan.execution_status == "not_started"
            )
            plan_text = " ".join(
                [step["description"] for step in plan_data.get("implementation_steps", [])]
                + plan_data.get("validation_requirements", [])
            ).lower()
            checks["manual_plan_completeness_ground_truth"] = (
                "zero" in plan_text
                and "regression test" in plan_text
                and "test_calculator.py" in plan_text
            )

            proposal_response = client.post("/api/v1/proposals/create", json={
                "repository_id": REPOSITORY_ID,
                "task_id": plan.task_id,
                "transformation_id": TRANSFORMATION,
            })
            checks["deterministic_proposal_eligible"] = proposal_response.status_code == 201
            proposal = proposal_response.json()
            checks["proposal_waits_for_human_review"] = (
                proposal.get("lifecycle_state") == "awaiting_review"
                and proposal.get("human_approval_required") is True
                and proposal.get("runtime_validation_status") == "not_run"
            )
            checks["diff_is_presented_read_only"] = (
                proposal.get("unified_diff", "").startswith("--- a/package/calculator.py")
                and client.post(f"/api/v1/proposals/{proposal.get('proposal_id')}/apply").status_code == 404
            )

            handoff_response = client.post("/api/v1/handoffs", json={
                "proposal_id": proposal["proposal_id"],
            })
            checks["handoff_report_generated"] = handoff_response.status_code == 201
            handoff = handoff_response.json()
            checks["handoff_reports_runtime_not_run"] = (
                handoff.get("validation_and_risks", {}).get("runtime_tests_status") == "not_run"
                and handoff.get("runtime_execution", {}).get("status") == "not_run"
            )

        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        after = _tree_hashes(root)
        checks["repository_immutable"] = before == after

        plan_files = set(plan_data.get("relevant_files", []))
        relevant_covered = sorted(plan_files & GROUND_TRUTH_RELEVANT_FILES)
        relevant_references = len(plan_data.get("source_references", []))
        unsupported_count = len(plan_data.get("unsupported_references", []))
        citation_total = relevant_references + unsupported_count
        checks_list = list(checks.values())
        passed = sum(checks_list)

        return {
            "report_version": 1,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "evaluation_kind": "offline_mock_end_to_end",
            "provider": "mock",
            "is_mock": True,
            "fixture": "tests/fixtures/planning_repo",
            "task": TASK,
            "plan_status": plan_data.get("status"),
            "workflow_cases": {
                "total": len(checks),
                "passed": passed,
                "failed": len(checks) - passed,
                "skipped": 0,
                "checks": checks,
            },
            "quality": {
                "plan_schema_valid": checks["plan_schema_validity"],
                "manual_plan_completeness_ground_truth": checks["manual_plan_completeness_ground_truth"],
                "verified_citations": relevant_references,
                "unsupported_citations": unsupported_count,
                "citation_accuracy": (relevant_references / citation_total) if citation_total else None,
                "relevant_file_ground_truth": sorted(GROUND_TRUTH_RELEVANT_FILES),
                "relevant_files_covered": relevant_covered,
                "relevant_file_coverage": len(relevant_covered) / len(GROUND_TRUTH_RELEVANT_FILES),
                "dependency_manifests_found": sorted(manifests),
                "proposal_eligibility_correct": checks["deterministic_proposal_eligible"],
                "approval_gate_compliant": checks["proposal_waits_for_human_review"],
                "repository_immutable": checks["repository_immutable"],
            },
            "offline_performance": {
                "workflow_elapsed_ms": elapsed_ms,
                "model_latency_ms": None,
                "input_tokens": None,
                "output_tokens": None,
                "reasoning_tokens": None,
                "estimated_cost_usd": None,
                "note": "Mock inference does not report model tokens, provider latency, or cost.",
            },
            "historical_live_nebius_observation": {
                "source": "user-provided Phase 6B.2 result; not measured by this offline run",
                "model": "nvidia/Nemotron-3_5-Lightning",
                "input_tokens": 1349,
                "output_tokens": 381,
                "reasoning_tokens": 0,
                "latency_ms": 2823,
                "verified_citations": 5,
                "unsupported_citations": 0,
                "estimated_cost_usd": 0.00017238,
            },
            "adversarial_test_coverage": {
                "backend_test_cases": {
                    "forged_client_provenance": ["tests/test_proposals.py::test_client_cannot_forge_plan_provider_or_validation_metadata"],
                    "tampered_stored_plan": ["tests/test_proposals.py::test_modified_server_stored_plan_metadata_fails_integrity_check"],
                    "unsupported_citations": ["tests/test_task_planning.py::test_schema_valid_plan_with_unknown_evidence_is_rejected_as_insufficient_context", "tests/test_proposals.py::test_plan_with_unsupported_citation_cannot_create_proposal"],
                    "stale_analysis_snapshot": ["tests/test_proposals.py::test_stale_analysis_snapshot_is_rejected_even_when_calculator_target_is_unchanged"],
                    "unsupported_task_and_transformation": ["tests/test_proposals.py::test_unsupported_task_does_not_receive_a_proposal", "tests/test_proposals.py::test_unsupported_transformation_is_rejected"],
                    "hostile_model_execution_instruction": ["tests/test_phase7_evaluation.py::test_model_execution_instruction_cannot_change_deterministic_proposal_or_execute"],
                    "repository_prompt_injection": ["tests/test_phase7_evaluation.py::test_repository_prompt_injection_text_is_not_forwarded_to_mock_provider"],
                    "traversal_and_symlink": ["tests/test_proposals.py::test_absolute_and_traversal_patch_paths_are_rejected", "tests/test_repository_analysis.py::test_escaping_symlink_is_skipped", "tests/test_proposals.py::test_symlink_escape_target_is_rejected"],
                    "development_review_authorization": ["tests/test_reviews_handoffs.py::test_review_feature_is_disabled_by_default", "tests/test_reviews_handoffs.py::test_review_routes_reject_non_loopback_clients", "tests/test_reviews_handoffs.py::test_review_flag_cannot_be_enabled_outside_development"],
                    "provider_error_malformed_and_truncated": ["tests/test_nebius.py::test_timeout_and_http_error_are_distinct_and_never_retry", "tests/test_task_planning.py::test_invalid_provider_plan_has_safe_structured_diagnostics", "tests/test_task_planning.py::test_truncated_live_response_is_rejected_before_plan_parsing"],
                },
                "linux_symlink_ci": "not_configured",
            },
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPOSITORY_ROOT / "docs" / "evaluation" / "phase-7-results.json",
        help="Write the machine-readable report here (default: docs/evaluation/phase-7-results.json).",
    )
    args = parser.parse_args()
    logging.getLogger("httpx").setLevel(logging.WARNING)
    report = run_evaluation()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["workflow_cases"]["failed"]:
        raise SystemExit(1)
