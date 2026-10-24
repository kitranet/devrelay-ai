"""Offline scanner contract checks for the synthetic continuity scenario."""

from pathlib import Path

from app.core.config import Settings
from app.services.repository_analysis import RepositoryScanner


FIXTURE = Path(__file__).parent / "fixtures" / "continuity_pipeline"


def analyze_fixture():
    settings = Settings(
        _env_file=None,
        inference_provider="mock",
        nebius_api_key=None,
        authorized_repositories={"continuity-pipeline-fixture": FIXTURE.resolve()},
    )
    return RepositoryScanner(settings).analyze("continuity-pipeline-fixture")


def test_scanner_discovers_pipeline_modules_and_dependency_manifest():
    analysis = analyze_fixture()

    paths = {item.path for item in analysis.files}
    module_paths = {item.path for item in analysis.modules}
    imported_modules = {item.imported_module for item in analysis.imports}

    assert analysis.summary.repository_id == "continuity-pipeline-fixture"
    assert {
        "pipeline/source.py",
        "pipeline/validation.py",
        "pipeline/transform.py",
        "pipeline/retry.py",
        "pipeline/config.py",
        "pipeline/output.py",
        "pipeline/orchestrator.py",
        "pipeline/models.py",
        "tests/test_pipeline.py",
    } <= paths
    assert "pipeline/orchestrator.py" in module_paths
    assert "pipeline.validation" in imported_modules
    assert "pipeline.output" in imported_modules
    assert any(manifest.path == "requirements.txt" and "pytest>=8.0" in manifest.dependencies
               for manifest in analysis.dependency_manifests)


def test_ground_truth_references_are_available_without_scanning_ground_truth():
    analysis = analyze_fixture()
    analyzed_paths = set(analysis.content_hashes)
    reference_paths = {reference.path for reference in [
        *(function.source for function in analysis.functions),
        *(item.source for item in analysis.classes),
    ]}

    assert {
        "pipeline/orchestrator.py",
        "pipeline/validation.py",
        "pipeline/config.py",
        "pipeline/output.py",
        "tests/test_pipeline.py",
    } <= analyzed_paths
    assert "run_nightly" in {
        function.qualified_name for function in analysis.functions
    }
    assert "continuity-pipeline-ground-truth.md" not in analyzed_paths
    assert reference_paths <= analyzed_paths


def test_analysis_is_read_only_for_the_synthetic_fixture():
    before = {
        path.relative_to(FIXTURE).as_posix(): path.read_bytes()
        for path in FIXTURE.rglob("*")
        if path.is_file()
    }

    analyze_fixture()

    after = {
        path.relative_to(FIXTURE).as_posix(): path.read_bytes()
        for path in FIXTURE.rglob("*")
        if path.is_file()
    }
    assert after == before
