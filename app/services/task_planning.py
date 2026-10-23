"""Evidence-constrained planning over static repository analysis."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid

from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import ModelEmptyResponseError, ModelIncompleteResponseError, SensitiveInferenceContentError, TaskPlanValidationError, TaskPlanningContextLimitError, TaskPlanningTimeoutError
from app.models.inference import ChatMessage, InferenceRequest, InferenceResponse, diagnostics_for
from app.models.repository import RepositoryAnalysisResponse, SourceReference
from app.models.task import PlanGeneration, PlanStep, TaskPlan, TaskPlanningRequest
from app.services.inference import InferenceService
from app.services.repository_analysis import RepositoryScanner

logger = logging.getLogger(__name__)
_WORD = re.compile(r"[a-z0-9_]{3,}")
_STOP_WORDS = {"the", "and", "for", "with", "that", "this", "from", "into", "existing", "please", "add", "fix"}
_SECRET_LIKE = re.compile(
    r"(?i)(?:-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"(?:api[_-]?key|access[_-]?token|password|secret)\s*[:=]\s*\S+|"
    r"nvapi-[A-Za-z0-9_-]{16,}|sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,})"
)
_UNSAFE_TASK_PATTERNS = (
    re.compile(r"\b(exfiltrat(?:e|ion)|steal credentials|credential theft)\b", re.IGNORECASE),
    re.compile(r"\b(ransomware|deploy malware|credential stealer|keylogger)\b", re.IGNORECASE),
    re.compile(r"\b(bypass authentication|evade detection|disable audit logging)\b", re.IGNORECASE),
    re.compile(r"\b(run|execute) arbitrary shell commands?\b", re.IGNORECASE),
)
_PLAN_SCHEMA_PATHS = {
    ("status",),
    ("relevant_files",), ("relevant_files", "*"),
    ("source_references",), ("source_references", "*"),
    ("source_references", "*", "path"), ("source_references", "*", "line"),
    ("source_references", "*", "end_line"),
    ("implementation_steps",), ("implementation_steps", "*"),
    ("implementation_steps", "*", "step"), ("implementation_steps", "*", "description"),
    ("implementation_steps", "*", "source_references"),
    ("implementation_steps", "*", "source_references", "*"),
    ("implementation_steps", "*", "source_references", "*", "path"),
    ("implementation_steps", "*", "source_references", "*", "line"),
    ("implementation_steps", "*", "source_references", "*", "end_line"),
    ("expected_code_changes",), ("expected_code_changes", "*"),
    ("expected_code_changes", "*", "path"), ("expected_code_changes", "*", "description"),
    ("risks",), ("risks", "*"), ("dependencies",), ("dependencies", "*"),
    ("validation_requirements",), ("validation_requirements", "*"),
    ("assumptions",), ("assumptions", "*"),
}
_PLAN_ARRAY_PATHS = {
    "relevant_files", "source_references", "implementation_steps", "expected_code_changes",
    "risks", "dependencies", "validation_requirements", "assumptions",
    "implementation_steps[].source_references",
}


def _contains_sensitive_text(value: str, configured_key: str | None) -> bool:
    """Detect likely credentials without logging or returning the matched text."""
    return bool((configured_key and configured_key in value) or _SECRET_LIKE.search(value))


def _safe_schema_path(location: tuple[object, ...]) -> str:
    normalized = tuple("*" if isinstance(part, int) else part for part in location)
    if normalized not in _PLAN_SCHEMA_PATHS:
        return "unknown"
    rendered: list[str] = []
    for part in normalized:
        if part == "*" and rendered:
            rendered[-1] += "[]"
        else:
            rendered.append("[]" if part == "*" else str(part))
    return ".".join(rendered)


def _validation_diagnostics(error: ValidationError) -> tuple[list[str], list[dict[str, str]]]:
    categories: set[str] = set()
    details: list[dict[str, str]] = []
    for item in error.errors(include_input=False, include_url=False)[:10]:
        error_type = item.get("type", "")
        location = item.get("loc", ())
        path = _safe_schema_path(tuple(location))
        if error_type == "missing":
            category = "missing_required_field"
        elif error_type == "literal_error":
            category = "invalid_enum_value"
        elif error_type == "too_long":
            category = "excessive_item_count" if path in _PLAN_ARRAY_PATHS else "field_limit_exceeded"
        elif error_type == "extra_forbidden":
            category = "unexpected_field"
        elif error_type.endswith("_type") or error_type == "model_type":
            category = "incorrect_field_type"
        else:
            category = "schema_constraint_failed"
        categories.add(category)
        details.append({"path": path, "category": category})
    if not categories:
        categories.add("schema_constraint_failed")
    return sorted(categories), details


def _log_plan_validation_failure(
    *, provider: str, category: str, field_errors: list[dict[str, str]] | None = None,
    root_type: str | None = None,
) -> None:
    diagnostic: dict[str, object] = {"provider": provider, "category": category}
    if field_errors:
        diagnostic["field_errors"] = field_errors
    if root_type:
        diagnostic["root_type"] = root_type
    logger.warning("Planning response rejected; diagnostics=%s", json.dumps(diagnostic, separators=(",", ":")))


class TaskPlanningService:
    def __init__(self, settings: Settings, scanner: RepositoryScanner, inference: InferenceService) -> None:
        self.settings = settings
        self.scanner = scanner
        self.inference = inference

    async def plan(self, request: TaskPlanningRequest) -> TaskPlan:
        try:
            analysis = await asyncio.to_thread(self.scanner.analyze, request.repository_id)
            if any(pattern.search(request.task_description) for pattern in _UNSAFE_TASK_PATTERNS):
                return TaskPlan(
                    task_id=str(uuid.uuid4()), repository_id=request.repository_id,
                    task_description=request.task_description, status="unsupported",
                    human_approval_required=True, provider=self.settings.inference_provider,
                    is_mock=self.settings.inference_provider == "mock",
                    assumptions=["The request falls outside the supported engineering-planning scope."],
                )
            if not analysis.modules:
                return TaskPlan(
                    task_id=str(uuid.uuid4()), repository_id=request.repository_id,
                    task_description=request.task_description, status="insufficient_context",
                    human_approval_required=True, provider=self.settings.inference_provider,
                    is_mock=self.settings.inference_provider == "mock",
                    assumptions=["No analyzable Python modules were found in this repository."],
                )
            configured_key = self.settings.nebius_api_key.get_secret_value() if self.settings.nebius_api_key else None
            if _contains_sensitive_text(request.task_description, configured_key):
                raise SensitiveInferenceContentError()
            context = self._context(request.task_description, analysis)
            encoded = json.dumps(context, ensure_ascii=True, separators=(",", ":"))
            if len(encoded) > self.settings.task_context_max_chars:
                encoded = json.dumps(self._context(request.task_description, analysis, budget=self.settings.task_context_max_chars // 2), separators=(",", ":"))
            if len(encoded) > self.settings.task_context_max_chars:
                raise TaskPlanningContextLimitError()
            if _contains_sensitive_text(encoded, configured_key):
                raise SensitiveInferenceContentError()
            inference = await asyncio.wait_for(
                self.inference.generate(InferenceRequest(messages=[
                    ChatMessage(role="system", content=(
                        "Produce a compact engineering plan using only the supplied static repository analysis. "
                        "Return exactly one JSON object matching this shape: "
                        "{\"status\":\"planned\",\"relevant_files\":[\"path\"],"
                        "\"source_references\":[{\"path\":\"path\",\"line\":1,\"end_line\":null}],"
                        "\"implementation_steps\":[{\"step\":1,\"description\":\"text\",\"source_references\":[]}],"
                        "\"expected_code_changes\":[{\"path\":\"path\",\"description\":\"text\"}],"
                        "\"risks\":[],\"dependencies\":[],\"validation_requirements\":[],\"assumptions\":[]}. "
                        "Include every key. status must be exactly one of planned, insufficient_context, or unsupported; "
                        "use empty arrays when none apply. "
                        "Array item types are: strings for relevant_files, risks, dependencies, validation_requirements, "
                        "and assumptions; source-reference objects for source_references; step objects for "
                        "implementation_steps; and path/description objects for expected_code_changes. "
                        "Each source reference must copy an exact supplied path, positive integer line, and "
                        "positive integer end_line or null when absent. Copy the complete reference object exactly; "
                        "do not shorten a supplied range to its start line. A reference with end_line omitted is "
                        "treated as a line-only citation and is valid only when that exact start line is analyzed. "
                        "Step descriptions must be 1-1000 characters; "
                        "expected-code-change descriptions must be 1-500 characters. "
                        "Use at most 4 steps, 5 files, 5 top-level references, 20 references per step, "
                        "5 expected changes, 4 risks, 4 dependencies, "
                        "4 validation requirements, and 3 assumptions. Keep text brief. "
                        "Cite only supplied references and use only supplied file paths. Do not invent source, "
                        "code snippets, test results, or files. No Markdown, commentary, or internal reasoning."
                    )),
                    ChatMessage(role="user", content="DEVRELAY_PLAN_REQUEST\n" + encoded),
                ], max_tokens=self.settings.nebius_max_output_tokens,
                    json_mode=(
                        self.settings.inference_provider == "nebius"
                        and self.settings.nebius_model == "nvidia/Nemotron-3_5-Lightning"
                    ),
                    disable_thinking=(
                        self.settings.inference_provider == "nebius"
                        and self.settings.nebius_planning_disable_thinking
                        and self.settings.nebius_model == "nvidia/Nemotron-3_5-Lightning"
                    ))),
                timeout=self.settings.task_planning_timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise TaskPlanningTimeoutError() from exc
        configured_key = self.settings.nebius_api_key.get_secret_value() if self.settings.nebius_api_key else None
        if _contains_sensitive_text(inference.content, configured_key):
            raise SensitiveInferenceContentError()
        if inference.completion_status != "completed":
            raise ModelIncompleteResponseError()
        if not inference.content.strip():
            _log_plan_validation_failure(provider=inference.provider, category="empty_model_content")
            raise ModelEmptyResponseError()
        try:
            decoded = json.loads(inference.content)
        except json.JSONDecodeError:
            _log_plan_validation_failure(provider=inference.provider, category="invalid_json_syntax")
            raise TaskPlanValidationError() from None
        if not isinstance(decoded, dict):
            root_type = (
                "null" if decoded is None else "boolean" if isinstance(decoded, bool)
                else "number" if isinstance(decoded, (int, float))
                else "array" if isinstance(decoded, list) else "string"
            )
            _log_plan_validation_failure(
                provider=inference.provider, category="incorrect_json_root_type", root_type=root_type
            )
            raise TaskPlanValidationError()
        try:
            generation = PlanGeneration.model_validate(decoded)
        except ValidationError as exc:
            categories, field_errors = _validation_diagnostics(exc)
            _log_plan_validation_failure(
                provider=inference.provider,
                category="pydantic_validation_failed:" + ",".join(categories),
                field_errors=field_errors,
            )
            raise TaskPlanValidationError() from None

        if generation.status == "unsupported":
            return TaskPlan(
                task_id=str(uuid.uuid4()), repository_id=request.repository_id,
                task_description=request.task_description, status="unsupported",
                human_approval_required=True, provider=inference.provider, is_mock=inference.is_mock,
                assumptions=["The configured provider does not have a defined response for this request."],
                inference_diagnostics=diagnostics_for(inference),
            )

        return self._validate_evidence(generation, request, analysis, inference)

    def _context(self, task_description: str, analysis: RepositoryAnalysisResponse, budget: int | None = None) -> dict:
        tokens = {word for word in _WORD.findall(task_description.lower()) if word not in _STOP_WORDS}
        test_paths = set(analysis.test_files)
        file_candidates = []
        for file in analysis.files:
            score = sum(token in file.path.lower() for token in tokens)
            if file.path in test_paths:
                score += 1
            file_candidates.append((score, file.path))
        file_candidates.sort(key=lambda item: (-item[0], item[1]))
        chosen = [path for _, path in file_candidates[:40]]
        chosen_set = set(chosen)
        modules = [module.model_dump() for module in analysis.modules if module.path in chosen_set]
        symbols = [
            {"path": item.source.path, "line": item.source.line, "end_line": item.source.end_line, "name": item.qualified_name, "kind": item.kind}
            for item in analysis.functions if item.source.path in chosen_set
        ] + [
            {"path": item.source.path, "line": item.source.line, "end_line": item.source.end_line, "name": item.qualified_name, "kind": "class"}
            for item in analysis.classes if item.source.path in chosen_set
        ]
        imports = [item.model_dump() for item in analysis.imports if item.source_path in chosen_set]
        source_references = [
            {"path": item["path"], "line": item["line"], "end_line": item["end_line"]}
            for item in symbols
        ] + [
            {"path": item.source_path, "line": item.line, "end_line": None}
            for item in analysis.imports if item.source_path in chosen_set
        ]
        available = sorted(chosen_set)
        result = {
            "task_description": task_description,
            "summary": analysis.summary.model_dump(),
            "available_files": available,
            "modules": modules,
            "symbols": symbols,
            "imports": imports,
            "dependencies": [manifest.model_dump() for manifest in analysis.dependency_manifests],
            "test_files": analysis.test_files,
            "source_references": source_references,
            "warnings": [warning.model_dump() for warning in analysis.warnings[:50]],
        }
        if budget is not None:
            # Deterministically trim low-priority arrays until the context fits.
            for key in ("imports", "symbols", "source_references", "modules", "available_files", "dependencies", "warnings"):
                while result[key] and len(json.dumps(result, separators=(",", ":"))) > budget:
                    result[key].pop()
        return result

    @staticmethod
    def _validate_evidence(
        generation: PlanGeneration, request: TaskPlanningRequest, analysis: RepositoryAnalysisResponse,
        inference: InferenceResponse,
    ) -> TaskPlan:
        paths = {item.path for item in analysis.files}
        references = {
            (item.source.path, item.source.line, item.source.end_line)
            for item in analysis.functions + analysis.classes
        }
        references.update((item.source_path, item.line, None) for item in analysis.imports)
        reference_starts = {(path, line) for path, line, _ in references}

        unsupported: list[str] = []
        invalid_file_count = 0
        invalid_source_reference_count = 0
        invalid_change_count = 0
        seen_invalid_references: set[tuple[str, int, int | None]] = set()

        def valid_reference(reference: SourceReference) -> bool:
            nonlocal invalid_source_reference_count
            key = (reference.path, reference.line, reference.end_line)
            # A citation without an end line asserts only an analyzed start line.
            # A supplied range must still exactly match the AST/import evidence.
            is_valid = key in references if reference.end_line is not None else (key in references or key[:2] in reference_starts)
            if not is_valid:
                if key not in seen_invalid_references:
                    invalid_source_reference_count += 1
                    seen_invalid_references.add(key)
                unsupported.append(f"{reference.path}:{reference.line}")
                return False
            return True

        def validated_references(items: list[SourceReference]) -> list[SourceReference]:
            accepted: list[SourceReference] = []
            seen: set[tuple[str, int, int | None]] = set()
            for item in items:
                key = (item.path, item.line, item.end_line)
                if valid_reference(item) and key not in seen:
                    accepted.append(item)
                    seen.add(key)
            return accepted

        valid_files = []
        for path in generation.relevant_files:
            if path in paths and path not in valid_files:
                valid_files.append(path)
            else:
                invalid_file_count += 1
                unsupported.append(path)
        valid_refs = validated_references(generation.source_references)
        valid_steps = [
            PlanStep(step=step.step, description=step.description,
                     source_references=validated_references(step.source_references))
            for step in generation.implementation_steps
        ]
        valid_changes = []
        for change in generation.expected_code_changes:
            if change.path in paths:
                valid_changes.append(change)
            else:
                invalid_change_count += 1
                unsupported.append(change.path)

        if unsupported:
            categories = []
            if invalid_file_count:
                categories.append("unknown_file_path")
            if invalid_source_reference_count:
                categories.append("source_reference_not_in_analysis")
            if invalid_change_count:
                categories.append("expected_change_path_not_in_analysis")
            logger.warning(
                "Planning evidence rejected; diagnostics=%s",
                json.dumps({
                    "provider": inference.provider,
                    "categories": categories,
                    "invalid_file_count": invalid_file_count,
                    "invalid_source_reference_count": invalid_source_reference_count,
                    "invalid_change_count": invalid_change_count,
                }, separators=(",", ":")),
            )

        status = generation.status
        if unsupported:
            status = "insufficient_context"
        if status == "planned" and (not valid_files or not valid_refs or not valid_steps):
            status = "insufficient_context"
        return TaskPlan(
            task_id=str(uuid.uuid4()), repository_id=request.repository_id,
            task_description=request.task_description, status=status,
            relevant_files=valid_files, source_references=valid_refs,
            implementation_steps=valid_steps, expected_code_changes=valid_changes,
            risks=generation.risks, dependencies=generation.dependencies,
            validation_requirements=generation.validation_requirements,
            human_approval_required=True, assumptions=generation.assumptions,
            unsupported_references=sorted(set(unsupported)), provider=inference.provider, is_mock=inference.is_mock,
            inference_diagnostics=diagnostics_for(inference),
        )
