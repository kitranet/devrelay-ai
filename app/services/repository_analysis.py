"""Bounded, non-executing static analysis of explicitly authorized repositories."""

from __future__ import annotations

import ast
import hashlib
import json
import configparser
import os
import re
import time
import tomllib
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import Settings
from app.core.errors import (
    RepositoryAnalysisTimeoutError,
    RepositoryLimitError,
    RepositoryNotAuthorizedError,
)
from app.models.repository import (
    AnalysisWarning,
    DependencyManifest,
    ImportRelationship,
    RepositoryAnalysisResponse,
    RepositoryClass,
    RepositoryFile,
    RepositoryFunction,
    RepositoryModule,
    RepositorySummary,
    SourceReference,
)

_PRUNED_DIRECTORIES = {
    ".git", ".hg", ".svn", ".venv", "venv", "env", "virtualenv",
    "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".tox", ".nox", ".cache", ".idea", ".vscode", ".aws", ".ssh", ".gnupg",
    ".azure", ".config", ".kube", ".docker", ".npm", ".terraform",
    "credentials", "secrets", ".secrets", "build", "dist", "target",
    "site-packages", "htmlcov", "coverage",
}
_SECRET_FILENAMES = {
    "id_rsa", "id_ed25519", "id_ecdsa", "id_dsa", "known_hosts", "authorized_keys",
    ".npmrc", ".pypirc", ".netrc", ".git-credentials", "terraform.tfstate",
    "terraform.tfstate.backup",
}
_SECRET_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".ppk", ".secret", ".token", ".jks", ".keystore"}
_BINARY_SUFFIXES = {
    ".pyc", ".pyo", ".so", ".dll", ".exe", ".bin", ".dat", ".png", ".jpg", ".jpeg",
    ".gif", ".bmp", ".webp", ".ico", ".pdf", ".zip", ".gz", ".tar", ".whl", ".class",
    ".jar", ".mp4", ".mp3", ".wav", ".sqlite", ".sqlite3", ".db", ".pyd", ".dylib",
    ".o", ".obj", ".a", ".lib", ".7z", ".rar", ".doc", ".docx", ".xls", ".xlsx",
    ".ppt", ".pptx", ".wasm", ".iso", ".woff", ".woff2", ".ttf", ".otf", ".heic",
    ".tif", ".tiff",
}
_DEPENDENCY_NAMES = {
    "pyproject.toml", "setup.cfg", "setup.py", "pipfile", "pipfile.lock",
    "poetry.lock", "uv.lock", "pdm.lock", "requirements.txt",
}
_CONFIG_NAMES = {
    "tox.ini", "pytest.ini", "mypy.ini", ".flake8", "ruff.toml", ".ruff.toml",
    "setup.cfg", ".python-version", "makefile", "dockerfile", "compose.yaml",
    "docker-compose.yml",
}
_MAX_WARNINGS = 1_000


def _is_sensitive_filename(name: str) -> bool:
    lower = name.lower()
    return (
        lower.startswith(".env")
        or lower == ".envrc"
        or lower in _SECRET_FILENAMES
        or Path(lower).suffix in _SECRET_SUFFIXES
        or "credential" in lower
        or "secret" in lower
        or "token" in lower
        or "api_key" in lower
        or "api-key" in lower
        or "apikey" in lower
        or "private_key" in lower
        or "private-key" in lower
        or lower.startswith("service-account") and lower.endswith(".json")
    )


def _is_sensitive_parts(parts: tuple[str, ...]) -> bool:
    return any(part.lower() in _PRUNED_DIRECTORIES or _is_sensitive_filename(part) for part in parts)


def _is_dependency_file(path: Path) -> bool:
    name = path.name.lower()
    return name in _DEPENDENCY_NAMES or (name.startswith("requirements") and name.endswith(".txt"))


def _is_configuration_file(path: Path) -> bool:
    name = path.name.lower()
    return name in _CONFIG_NAMES or name == "pyproject.toml" or name.endswith((".ini", ".cfg", ".toml", ".yaml", ".yml"))


def _is_test_file(path: Path) -> bool:
    lower_parts = tuple(part.lower() for part in path.parts)
    return path.suffix.lower() == ".py" and (
        "tests" in lower_parts or path.name.lower().startswith("test_") or path.name.lower().endswith("_test.py")
    )


def _module_name(path: Path) -> str:
    parts = list(path.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts) or path.parent.name or "__init__"


class _SymbolVisitor(ast.NodeVisitor):
    def __init__(self, path: str) -> None:
        self.path = path
        self.scope: list[str] = []
        self.functions: list[RepositoryFunction] = []
        self.classes: list[RepositoryClass] = []
        self.imports: list[ImportRelationship] = []
        self.module_name = ""

    def _reference(self, node: ast.AST) -> SourceReference:
        return SourceReference(
            path=self.path,
            line=getattr(node, "lineno", 1),
            end_line=getattr(node, "end_lineno", None),
        )

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        qualified = ".".join((*self.scope, node.name))
        kind = "async_function" if isinstance(node, ast.AsyncFunctionDef) else "function"
        self.functions.append(
            RepositoryFunction(name=node.name, qualified_name=qualified, kind=kind, source=self._reference(node))
        )
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        qualified = ".".join((*self.scope, node.name))
        self.classes.append(
            RepositoryClass(name=node.name, qualified_name=qualified, source=self._reference(node))
        )
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append(
                ImportRelationship(
                    source_path=self.path,
                    source_module=self.module_name,
                    line=node.lineno,
                    imported_module=alias.name,
                    kind="import",
                )
            )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self.imports.append(
            ImportRelationship(
                source_path=self.path,
                source_module=self.module_name,
                line=node.lineno,
                imported_module=("." * node.level) + (node.module or ""),
                imported_names=[alias.name for alias in node.names],
                kind="from_import",
            )
        )


class RepositoryScanner:
    """Analyze source and declarative files with explicit resource bounds."""

    def __init__(self, settings: Settings, clock=time.monotonic) -> None:
        self.settings = settings
        self._clock = clock

    def analyze(self, repository_id: str) -> RepositoryAnalysisResponse:
        root_config = self.settings.authorized_repositories.get(repository_id)
        if root_config is None:
            raise RepositoryNotAuthorizedError()
        try:
            root = root_config.resolve(strict=True)
        except (OSError, RuntimeError):
            raise RepositoryNotAuthorizedError() from None
        if not root.is_dir():
            raise RepositoryNotAuthorizedError()

        started = self._clock()
        files: list[RepositoryFile] = []
        modules: list[RepositoryModule] = []
        functions: list[RepositoryFunction] = []
        classes: list[RepositoryClass] = []
        imports: list[ImportRelationship] = []
        manifests: list[DependencyManifest] = []
        test_files: list[str] = []
        readme_files: list[str] = []
        configuration_files: list[str] = []
        warnings: list[AnalysisWarning] = []
        content_hashes: dict[str, str] = {}
        total_bytes = 0
        scanned_file_count = 0
        pending_directories: list[tuple[Path, int]] = [(root, 0)]

        def warn(code: str, message: str, path: str | None = None, line: int | None = None) -> None:
            if len(warnings) < _MAX_WARNINGS:
                warnings.append(AnalysisWarning(code=code, message=message, path=path, line=line))

        def check_time() -> None:
            if self._clock() - started > self.settings.repository_max_processing_seconds:
                raise RepositoryAnalysisTimeoutError()

        while pending_directories:
            check_time()
            directory, depth = pending_directories.pop()
            try:
                entries = os.scandir(directory)
            except OSError:
                warn("unreadable_directory", "A directory could not be inspected.", directory.relative_to(root).as_posix() or ".")
                continue

            with entries:
                for entry in entries:
                    check_time()
                    entry_path = Path(entry.path)
                    relative = entry_path.relative_to(root)
                    relative_text = relative.as_posix()
                    if _is_sensitive_filename(entry.name):
                        continue
                    try:
                        is_junction = getattr(entry, "is_junction", lambda: False)()
                        if entry.is_symlink() or is_junction:
                            warn("symlink_skipped", "Symbolic links and directory junctions are not analyzed.", relative_text)
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            if entry.name.lower() in _PRUNED_DIRECTORIES:
                                continue
                            child_depth = depth + 1
                            if child_depth > self.settings.repository_max_depth:
                                warn("depth_limit", "A directory exceeded the traversal depth limit.", relative_text)
                                continue
                            pending_directories.append((entry_path, child_depth))
                            continue
                        if not entry.is_file(follow_symlinks=False):
                            continue
                        if _is_sensitive_parts(relative.parts):
                            continue
                        resolved = entry_path.resolve(strict=True)
                        if not resolved.is_relative_to(root):
                            warn("path_escape_skipped", "A path resolving outside the repository was skipped.", relative_text)
                            continue
                        # Use the resolved path's metadata consistently: Windows
                        # scandir may report st_ino=0 while Path.stat reports the
                        # actual file index, so comparing those values falsely
                        # classifies every file as changing during analysis.
                        stat = resolved.stat()
                    except (OSError, RuntimeError):
                        warn("unreadable_file", "A file could not be inspected.", relative_text)
                        continue

                    if len(relative.parts) > self.settings.repository_max_depth:
                        warn("depth_limit", "A file exceeded the traversal depth limit.", relative_text)
                        continue
                    scanned_file_count += 1
                    if scanned_file_count > self.settings.repository_max_files:
                        raise RepositoryLimitError("Repository exceeds the configured file-count limit.")
                    if stat.st_size > self.settings.repository_max_file_size_bytes:
                        raise RepositoryLimitError("A repository file exceeds the configured file-size limit.")
                    total_bytes += stat.st_size
                    if total_bytes > self.settings.repository_max_total_bytes:
                        raise RepositoryLimitError("Repository exceeds the configured total-size limit.")
                    if relative.suffix.lower() in _BINARY_SUFFIXES:
                        continue
                    try:
                        digest = hashlib.sha256()
                        has_nul = False
                        actual_size = 0
                        prefix = bytearray()
                        with resolved.open("rb") as stream:
                            while chunk := stream.read(64 * 1024):
                                check_time()
                                actual_size += len(chunk)
                                if actual_size > self.settings.repository_max_file_size_bytes:
                                    raise RepositoryLimitError("A repository file exceeds the configured file-size limit.")
                                digest.update(chunk)
                                has_nul = has_nul or b"\x00" in chunk
                                if len(prefix) < 8_192:
                                    prefix.extend(chunk[: 8_192 - len(prefix)])
                        after = resolved.stat()
                        if (
                            actual_size != stat.st_size
                            or (stat.st_ino, stat.st_size, stat.st_mtime_ns)
                            != (after.st_ino, after.st_size, after.st_mtime_ns)
                        ):
                            warn("file_changed_during_analysis", "A file changed while it was being analyzed.", relative_text)
                            continue
                    except OSError:
                        warn("unreadable_file", "A file could not be inspected.", relative_text)
                        continue
                    if has_nul:
                        continue
                    try:
                        prefix.decode("utf-8")
                    except UnicodeError:
                        continue
                    content_hashes[relative_text] = digest.hexdigest()

                    category = self._category(relative)
                    file_info = RepositoryFile(
                        path=relative_text,
                        size_bytes=stat.st_size,
                        modified_at=datetime.fromtimestamp(stat.st_mtime, timezone.utc),
                        category=category,
                    )
                    files.append(file_info)
                    if category == "readme":
                        readme_files.append(relative_text)
                    if _is_configuration_file(relative):
                        configuration_files.append(relative_text)
                    if _is_test_file(relative):
                        test_files.append(relative_text)
                    if relative.name.lower() == "setup.py":
                        manifests.append(
                            DependencyManifest(
                                path=relative_text,
                                format="setup.py (not executed)",
                            )
                        )

                    if category == "python":
                        try:
                            source, actual_size = self._read_text(resolved)
                        except (OSError, UnicodeError):
                            warn("unreadable_python", "A Python source file could not be decoded as UTF-8.", relative_text)
                            continue
                        total_bytes += actual_size - stat.st_size
                        if total_bytes > self.settings.repository_max_total_bytes:
                            raise RepositoryLimitError("Repository exceeds the configured total-size limit.")
                        check_time()
                        try:
                            tree = ast.parse(source, filename=relative_text)
                        except (SyntaxError, ValueError, RecursionError):
                            warn("python_parse_error", "A Python source file could not be parsed.", relative_text)
                            continue
                        visitor = _SymbolVisitor(relative_text)
                        visitor.module_name = _module_name(relative)
                        visitor.visit(tree)
                        functions.extend(visitor.functions)
                        classes.extend(visitor.classes)
                        imports.extend(visitor.imports)
                        modules.append(
                            RepositoryModule(
                                name=visitor.module_name,
                                path=relative_text,
                                imports=len(visitor.imports),
                                functions=len(visitor.functions),
                                classes=len(visitor.classes),
                            )
                        )
                        check_time()
                    elif _is_dependency_file(relative):
                        try:
                            text, actual_size = self._read_text(resolved)
                            total_bytes += actual_size - stat.st_size
                            if total_bytes > self.settings.repository_max_total_bytes:
                                raise RepositoryLimitError("Repository exceeds the configured total-size limit.")
                            manifests.append(self._parse_manifest(relative_text, relative.name, text))
                        except RepositoryLimitError:
                            raise
                        except (OSError, UnicodeError, ValueError, configparser.Error, tomllib.TOMLDecodeError):
                            manifests.append(
                                DependencyManifest(path=relative_text, format=self._manifest_format(relative.name))
                            )
                            warn("manifest_parse_error", "A dependency manifest could not be parsed.", relative_text)

        check_time()
        duration_ms = round((self._clock() - started) * 1_000, 3)
        dependency_count = sum(len(manifest.dependencies) for manifest in manifests)
        snapshot_payload = json.dumps(
            sorted(content_hashes.items()), ensure_ascii=True, separators=(",", ":")
        ).encode("ascii")
        snapshot_id = hashlib.sha256(snapshot_payload).hexdigest()
        summary = RepositorySummary(
            repository_id=repository_id,
            file_count=len(files),
            python_file_count=sum(file.category == "python" for file in files),
            module_count=len(modules),
            function_count=len(functions),
            class_count=len(classes),
            import_count=len(imports),
            dependency_count=dependency_count,
            test_file_count=len(test_files),
            duration_ms=duration_ms,
        )
        return RepositoryAnalysisResponse(
            summary=summary,
            files=sorted(files, key=lambda item: item.path),
            modules=sorted(modules, key=lambda item: item.path),
            functions=sorted(functions, key=lambda item: (item.source.path, item.source.line, item.qualified_name)),
            classes=sorted(classes, key=lambda item: (item.source.path, item.source.line, item.qualified_name)),
            imports=sorted(imports, key=lambda item: (item.source_path, item.line, item.imported_module)),
            dependency_manifests=sorted(manifests, key=lambda item: item.path),
            test_files=sorted(test_files),
            readme_files=sorted(readme_files),
            configuration_files=sorted(configuration_files),
            warnings=sorted(warnings, key=lambda item: (item.path or "", item.line or 0, item.code)),
            snapshot_id=snapshot_id,
            content_hashes=content_hashes,
        )

    @staticmethod
    def _category(relative: Path) -> str:
        name = relative.name.lower()
        if relative.suffix.lower() == ".py":
            return "python"
        if name.startswith("readme"):
            return "readme"
        if _is_dependency_file(relative):
            return "dependency"
        if name in _CONFIG_NAMES or name.endswith((".ini", ".cfg", ".toml", ".yaml", ".yml")):
            return "configuration"
        return "other"

    def _read_text(self, path: Path) -> tuple[str, int]:
        """Read at most one byte beyond the configured per-file limit."""
        with path.open("rb") as stream:
            contents = stream.read(self.settings.repository_max_file_size_bytes + 1)
        if len(contents) > self.settings.repository_max_file_size_bytes:
            raise RepositoryLimitError("A repository file exceeds the configured file-size limit.")
        return contents.decode("utf-8"), len(contents)

    @staticmethod
    def _manifest_format(name: str) -> str:
        lower = name.lower()
        if lower == "pyproject.toml":
            return "pyproject.toml"
        if lower == "setup.cfg":
            return "setup.cfg"
        if lower == "pipfile":
            return "Pipfile"
        if lower.endswith(".lock"):
            return "lockfile"
        if lower == "setup.py":
            return "setup.py (not executed)"
        return "requirements.txt"

    @classmethod
    def _parse_manifest(cls, path: str, name: str, text: str) -> DependencyManifest:
        lower = name.lower()
        dependencies: list[str] = []
        format_name = cls._manifest_format(name)
        if lower == "pyproject.toml":
            data = tomllib.loads(text)
            project = data.get("project", {})
            dependencies.extend(str(item) for item in project.get("dependencies", []))
            for group in project.get("optional-dependencies", {}).values():
                dependencies.extend(str(item) for item in group)
            poetry = data.get("tool", {}).get("poetry", {})
            dependencies.extend(str(key) for key in poetry.get("dependencies", {}) if key.lower() != "python")
            for group in poetry.get("group", {}).values():
                dependencies.extend(str(key) for key in group.get("dependencies", {}))
        elif lower.startswith("requirements") and lower.endswith(".txt"):
            for line in text.splitlines():
                item = line.split("#", 1)[0].strip()
                if item and not item.startswith(("-", ".")):
                    dependencies.append(item)
        elif lower == "setup.cfg":
            parser = configparser.ConfigParser()
            parser.read_string(text)
            if parser.has_option("options", "install_requires"):
                dependencies.extend(line.strip() for line in parser.get("options", "install_requires").splitlines() if line.strip())
            if parser.has_section("options.extras_require"):
                for _, raw in parser.items("options.extras_require"):
                    dependencies.extend(line.strip() for line in raw.splitlines() if line.strip())
        elif lower == "pipfile":
            data = tomllib.loads(text)
            for section in ("packages", "dev-packages"):
                dependencies.extend(str(name) for name in data.get(section, {}))
        elif lower in {"poetry.lock", "uv.lock", "pdm.lock", "pipfile.lock"}:
            if lower == "pipfile.lock":
                data = json.loads(text)
                for section in ("default", "develop"):
                    dependencies.extend(str(name) for name in data.get(section, {}))
            else:
                data = tomllib.loads(text)
                dependencies.extend(
                    str(package["name"])
                    for package in data.get("package", [])
                    if isinstance(package, dict) and "name" in package
                )
        # setup.py is recorded for traceability but intentionally never imported or executed.
        return DependencyManifest(path=path, format=format_name, dependencies=sorted(set(dependencies)))
