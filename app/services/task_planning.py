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


def _contains_sensitive_text(value: str, configured_key: str | None) -> bool:
    """Detect likely credentials without logging or returning the matched text."""
    return bool((configured_key and configured_key in value) or _SECRET_LIKE.search(value))


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
                        "Create a conservative engineering plan using only the supplied static repository analysis. "
                        "Return one JSON object matching the requested schema; do not include private chain-of-thought. "
                        "Cite only supplied source references. "
                        "Do not claim to inspect source content that is absent. Unknown or ambiguous tasks must use status unsupported or insufficient_context."
                    )),
                    ChatMessage(role="user", content="DEVRELAY_PLAN_REQUEST\n" + encoded),
                ], max_tokens=self.settings.nebius_max_output_tokens)),
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
            raise ModelEmptyResponseError()
        try:
            generation = PlanGeneration.model_validate_json(inference.content)
        except (ValidationError, ValueError):
            logger.warning("Planning provider returned invalid plan schema; provider=%s", inference.provider)
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

        unsupported: list[str] = []

        def valid_reference(reference: SourceReference) -> bool:
            key = (reference.path, reference.line, reference.end_line)
            if key not in references:
                unsupported.append(f"{reference.path}:{reference.line}")
                return False
            return True

        valid_files = []
        for path in generation.relevant_files:
            if path in paths and path not in valid_files:
                valid_files.append(path)
            else:
                unsupported.append(path)
        valid_refs = [ref for ref in generation.source_references if valid_reference(ref)]
        valid_steps = [
            PlanStep(step=step.step, description=step.description,
                     source_references=[ref for ref in step.source_references if valid_reference(ref)])
            for step in generation.implementation_steps
        ]
        valid_changes = []
        for change in generation.expected_code_changes:
            if change.path in paths:
                valid_changes.append(change)
            else:
                unsupported.append(change.path)

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
