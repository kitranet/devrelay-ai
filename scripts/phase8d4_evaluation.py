"""Repeatable offline evidence-selection evaluation for the continuity fixture."""

from __future__ import annotations

import json
from pathlib import Path

from app.core.config import Settings
from app.services.inference import build_inference_service
from app.services.repository_analysis import RepositoryScanner
from app.services.task_planning import TaskPlanningService

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "continuity_pipeline"
RESULT = ROOT / "docs" / "evaluation" / "phase-8d4-results.json"
REPOSITORY_ID = "continuity-pipeline-fixture"
TASK = (
    "Investigate why the 02:00 ingestion job can publish a successful report with fewer rows than the inbound batch. "
    "Trace orchestration, validation, transformation, retry, configuration, and publication behavior across the repository. "
    "Propose safe investigation steps, evidence to collect, and regression checks. Do not assume the root cause."
)
GROUND_TRUTH_FILES = {
    "pipeline/orchestrator.py", "pipeline/validation.py", "pipeline/config.py",
    "pipeline/output.py", "tests/test_pipeline.py",
}


def snapshot_files() -> dict[str, bytes]:
    return {path.relative_to(FIXTURE).as_posix(): path.read_bytes() for path in FIXTURE.rglob("*") if path.is_file()}


def main() -> int:
    before = snapshot_files()
    settings = Settings(
        _env_file=None,
        inference_provider="mock",
        nebius_api_key=None,
        nebius_live_inference_enabled=False,
        authorized_repositories={REPOSITORY_ID: FIXTURE.resolve()},
        task_evidence_max_files=7,
    )
    scanner = RepositoryScanner(settings)
    analysis = scanner.analyze(REPOSITORY_ID)
    service = TaskPlanningService(settings, scanner, build_inference_service(settings))
    excerpts = service._select_excerpts(REPOSITORY_ID, TASK, analysis)
    repeated = service._select_excerpts(REPOSITORY_ID, TASK, analysis)
    after = snapshot_files()

    analyzed_paths = set(analysis.content_hashes)
    excerpt_paths = {item.path for item in excerpts}
    missing_ground_truth = sorted(GROUND_TRUTH_FILES - analyzed_paths)
    missing_excerpt_core = sorted(GROUND_TRUTH_FILES - excerpt_paths)
    valid_excerpt_locations = all(
        item.path in analysis.content_hashes
        and item.line > 0
        and item.end_line >= item.line
        and len(item.content) <= settings.task_evidence_max_file_chars
        for item in excerpts
    )
    result = {
        "scenario": "synthetic_northstar_nightly_reporting",
        "repository_id": REPOSITORY_ID,
        "mode": "offline_static_evidence_selection",
        "provider": "mock",
        "live_inference_enabled": False,
        "inference_requests": 0,
        "fixture_unchanged": before == after,
        "workflow_support": {
            "bounded_source_excerpts": True,
            "plan_only_handoff_report": True,
            "development_only_plan_review_without_proposal": True,
            "non_calculator_deterministic_proposal": False,
            "runtime_validation": "not_run",
        },
        "analysis": {
            "file_count": analysis.summary.file_count,
            "python_file_count": analysis.summary.python_file_count,
            "module_count": analysis.summary.module_count,
            "function_count": analysis.summary.function_count,
            "class_count": analysis.summary.class_count,
            "import_count": analysis.summary.import_count,
            "test_file_count": analysis.summary.test_file_count,
            "dependencies": [{"path": item.path, "names": item.dependencies} for item in analysis.dependency_manifests],
            "ground_truth_core_file_count": len(GROUND_TRUTH_FILES),
            "ground_truth_core_files_discovered": len(GROUND_TRUTH_FILES) - len(missing_ground_truth),
            "ground_truth_core_missing": missing_ground_truth,
            "ground_truth_coverage": (len(GROUND_TRUTH_FILES) - len(missing_ground_truth)) / len(GROUND_TRUTH_FILES),
            "core_files_missing_from_excerpts": missing_excerpt_core,
            "excerpt_file_count": len(excerpts),
            "excerpt_paths": [item.path for item in excerpts],
            "excerpt_characters": sum(len(item.content) for item in excerpts),
            "excerpt_character_budget": settings.task_evidence_max_chars,
            "excerpt_selection_deterministic": [item.model_dump() for item in excerpts] == [item.model_dump() for item in repeated],
            "excerpt_locations_and_file_hashes_valid": valid_excerpt_locations,
            "imports": [
                {"source_path": item.source_path, "line": item.line, "imported_module": item.imported_module, "kind": item.kind}
                for item in analysis.imports
            ],
            "warnings": [item.code for item in analysis.warnings],
        },
        "not_measured": [
            "live_model_plan_schema_validity", "live_model_citation_precision", "live_model_root_cause_quality",
            "live_model_investigation_completeness", "live_model_handoff_quality", "live_model_latency_tokens_cost",
        ],
        "notes": [
            "This run scans files and selects static excerpts only; it does not call a model or the task API.",
            "Fixture-specific file coverage and excerpt selection are not general model-quality scores.",
            "Ground-truth diagnosis is stored separately and is never included in the planner context.",
            "Offline mock plans are explicitly disclosed and are not evidence of Nemotron reasoning quality.",
        ],
    }
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if not missing_ground_truth and not missing_excerpt_core and before == after and valid_excerpt_locations and excerpts == repeated else 1


if __name__ == "__main__":
    raise SystemExit(main())
