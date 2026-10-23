"""Traceable schemas returned by static repository analysis."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class RepositoryAnalysisRequest(BaseModel):
    repository_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class AnalysisWarning(BaseModel):
    code: str
    message: str
    path: str | None = None
    line: int | None = None


class RepositoryFile(BaseModel):
    path: str
    size_bytes: int
    modified_at: datetime
    category: Literal["python", "readme", "dependency", "configuration", "other"]


class SourceReference(BaseModel):
    path: str
    line: int = Field(ge=1)
    end_line: int | None = Field(default=None, ge=1)


class RepositoryFunction(BaseModel):
    name: str
    qualified_name: str
    kind: Literal["function", "async_function"]
    source: SourceReference


class RepositoryClass(BaseModel):
    name: str
    qualified_name: str
    source: SourceReference


class RepositoryModule(BaseModel):
    name: str
    path: str
    imports: int
    functions: int
    classes: int


class ImportRelationship(BaseModel):
    source_path: str
    source_module: str
    line: int
    imported_module: str
    imported_names: list[str] = Field(default_factory=list)
    kind: Literal["import", "from_import"]


class DependencyManifest(BaseModel):
    path: str
    format: str
    dependencies: list[str] = Field(default_factory=list)


class RepositorySummary(BaseModel):
    repository_id: str
    file_count: int
    python_file_count: int
    module_count: int
    function_count: int
    class_count: int
    import_count: int
    dependency_count: int
    test_file_count: int
    duration_ms: float


class RepositoryAnalysisResponse(BaseModel):
    summary: RepositorySummary
    files: list[RepositoryFile]
    modules: list[RepositoryModule]
    functions: list[RepositoryFunction]
    classes: list[RepositoryClass]
    imports: list[ImportRelationship]
    dependency_manifests: list[DependencyManifest]
    test_files: list[str]
    readme_files: list[str]
    configuration_files: list[str]
    warnings: list[AnalysisWarning]
    # Internal identity and content hashes used to bind plans to the scan that
    # produced their evidence. Pydantic excludes these fields from API output.
    snapshot_id: str = Field(exclude=True, repr=False)
    content_hashes: dict[str, str] = Field(exclude=True, repr=False)
