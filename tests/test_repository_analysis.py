import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import (
    RepositoryAnalysisTimeoutError,
    RepositoryLimitError,
    RepositoryNotAuthorizedError,
)
from app.models.repository import RepositoryAnalysisRequest
from app.services.repository_analysis import RepositoryScanner


def make_scanner(repository: Path, **overrides) -> RepositoryScanner:
    return RepositoryScanner(
        Settings(authorized_repositories={"sample": repository}, **overrides)
    )


class FakeLinkEntry:
    def __init__(self, path: Path, *, symlink: bool = False, junction: bool = False):
        self.name = path.name
        self.path = str(path)
        self._symlink = symlink
        self._junction = junction

    def is_symlink(self):
        return self._symlink

    def is_junction(self):
        return self._junction


class ScandirEntries:
    def __init__(self, entries):
        self.entries = entries

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def __iter__(self):
        return iter(self.entries)


def add_root_entry_to_scandir(root: Path, extra_entry, monkeypatch):
    real_scandir = os.scandir

    def patched_scandir(path):
        with real_scandir(path) as iterator:
            entries = list(iterator)
        if Path(path).resolve() == root:
            entries.append(extra_entry)
        return ScandirEntries(entries)

    monkeypatch.setattr("app.services.repository_analysis.os.scandir", patched_scandir)


def test_valid_repository_analysis_extracts_traceable_structure(sample_repository):
    result = make_scanner(sample_repository).analyze("sample")

    assert result.summary.repository_id == "sample"
    assert result.summary.python_file_count == 5
    assert result.summary.test_file_count == 1
    assert "tests/test_core.py" in result.test_files
    assert "README.md" in result.readme_files
    assert "pyproject.toml" in result.configuration_files
    assert any(item.path == "pyproject.toml" for item in result.dependency_manifests)
    assert any(item.path == "requirements-dev.txt" for item in result.dependency_manifests)
    assert "httpx>=0.27" in next(
        item.dependencies for item in result.dependency_manifests if item.path == "pyproject.toml"
    )
    assert not any(
        item.path in {
            ".env", ".npmrc", "credentials.json", "token.txt", "build/generated.py",
            "assets/image.png", ".config/gcloud/application_default_credentials.json",
        }
        for item in result.files
    )
    assert "TEST-PLACEHOLDER" not in result.model_dump_json()
    assert all(not Path(item.path).is_absolute() for item in result.files)


def test_sensitive_files_are_never_opened(sample_repository, monkeypatch):
    original_open = Path.open

    def guarded_open(path, *args, **kwargs):
        relative = path.relative_to(sample_repository)
        if any(part.lower() in {".config", "credentials", "secrets"} for part in relative.parts):
            raise AssertionError("scanner opened a secret directory")
        if any(token in path.name.lower() for token in (".env", "token", "credential", ".npmrc")):
            raise AssertionError("scanner opened a credential-like file")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)
    make_scanner(sample_repository).analyze("sample")


def test_ast_finds_nested_functions_classes_async_functions_and_imports(sample_repository):
    result = make_scanner(sample_repository).analyze("sample")

    assert any(item.name == "Worker" and item.source.path == "package/core.py" for item in result.classes)
    assert any(item.qualified_name == "outer.inner" for item in result.functions)
    assert any(item.kind == "async_function" and item.name == "start_worker" for item in result.functions)
    assert any(
        item.source_path == "package/core.py" and item.imported_module == ".helpers" and item.line == 3
        for item in result.imports
    )
    assert result.summary.import_count == len(result.imports)


def test_malformed_python_is_reported_without_aborting(sample_repository):
    result = make_scanner(sample_repository).analyze("sample")

    assert any(item.code == "python_parse_error" and item.path == "package/malformed.py" for item in result.warnings)
    assert not any(item.path == "package/malformed.py" for item in result.modules)


def test_unknown_binary_extension_is_skipped(tmp_path):
    (tmp_path / "opaque.payload").write_bytes(b"\x00\x01\x02binary")
    result = make_scanner(tmp_path).analyze("sample")
    assert result.files == []
    assert result.summary.file_count == 0


def test_empty_repository_returns_empty_analysis(tmp_path):
    result = make_scanner(tmp_path).analyze("sample")

    assert result.summary.file_count == 0
    assert result.modules == []
    assert result.functions == []
    assert result.warnings == []


def test_repository_id_cannot_be_a_path_and_unknown_ids_are_denied(tmp_path):
    with pytest.raises(ValidationError):
        RepositoryAnalysisRequest(repository_id="../outside")
    with pytest.raises(RepositoryNotAuthorizedError):
        make_scanner(tmp_path).analyze(str(tmp_path))


def test_escaping_symlink_is_skipped(sample_repository, tmp_path, monkeypatch):
    outside = tmp_path / "outside.py"
    outside.write_text("SECRET_OUTSIDE = True\n", encoding="utf-8")
    root = sample_repository.resolve()
    add_root_entry_to_scandir(root, FakeLinkEntry(root / "escape.py", symlink=True), monkeypatch)

    result = make_scanner(sample_repository).analyze("sample")
    assert "escape.py" not in {item.path for item in result.files}
    assert any(item.code == "symlink_skipped" and item.path == "escape.py" for item in result.warnings)
    assert "SECRET_OUTSIDE" not in result.model_dump_json()


def test_windows_directory_junction_is_not_traversed(sample_repository, tmp_path, monkeypatch):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "private.py").write_text("OUTSIDE_SENTINEL = True\n", encoding="utf-8")
    root = sample_repository.resolve()
    add_root_entry_to_scandir(root, FakeLinkEntry(root / "junction", junction=True), monkeypatch)
    result = make_scanner(sample_repository).analyze("sample")

    assert not any(item.path.startswith("junction/") for item in result.files)
    assert any(item.code == "symlink_skipped" and item.path == "junction" for item in result.warnings)
    assert "OUTSIDE_SENTINEL" not in result.model_dump_json()


def test_file_count_limit_fails_closed(sample_repository):
    scanner = make_scanner(sample_repository, repository_max_files=2)
    with pytest.raises(RepositoryLimitError, match="file-count"):
        scanner.analyze("sample")


def test_file_size_limit_fails_closed(tmp_path):
    (tmp_path / "oversized.py").write_text("x = '" + ("x" * 2048) + "'\n", encoding="utf-8")
    scanner = make_scanner(tmp_path, repository_max_file_size_bytes=128)
    with pytest.raises(RepositoryLimitError, match="file-size"):
        scanner.analyze("sample")


def test_total_size_limit_fails_closed(tmp_path):
    (tmp_path / "a.txt").write_text("a" * 80, encoding="utf-8")
    (tmp_path / "b.txt").write_text("b" * 80, encoding="utf-8")
    scanner = make_scanner(tmp_path, repository_max_total_bytes=100)
    with pytest.raises(RepositoryLimitError, match="total-size"):
        scanner.analyze("sample")


def test_depth_limit_skips_deep_files(sample_repository):
    scanner = make_scanner(sample_repository, repository_max_depth=1)
    result = scanner.analyze("sample")
    assert any(item.code == "depth_limit" for item in result.warnings)
    assert not any(item.path == "package/core.py" for item in result.files)


def test_processing_time_limit_is_enforced(sample_repository):
    class Clock:
        value = 0.0

        def __call__(self):
            self.value += 0.01
            return self.value

    scanner = RepositoryScanner(
        Settings(
            authorized_repositories={"sample": sample_repository},
            repository_max_processing_seconds=0.001,
        ),
        clock=Clock(),
    )
    with pytest.raises(RepositoryAnalysisTimeoutError):
        scanner.analyze("sample")
