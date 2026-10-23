"""Deterministic proposal generation and fail-closed static patch validation.

This module never writes to an authorized repository and never executes target code.
"""

from __future__ import annotations

import ast
import difflib
import hashlib
import logging
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
from uuid import uuid4

from app.core.config import Settings
from app.core.errors import (
    ProposalNotFoundError,
    ProposalSourceConflictError,
    ProposalValidationError,
    RepositoryNotAuthorizedError,
    TaskPlanNotFoundError,
)
from app.models.proposal import (
    CodeChangeProposal,
    CreateProposalRequest,
    ProposalTargetFile,
    ProposalValidationFinding,
)
from app.models.repository import SourceReference
from app.models.task import TaskPlan
from app.services.proposal_store import InMemoryProposalStore, InMemoryTaskPlanStore
from app.services.repository_analysis import RepositoryScanner

logger = logging.getLogger(__name__)

TARGET_PATH = "package/calculator.py"
AUTHORIZED_REPOSITORY_ID = "planning-fixture"
AUTHORIZED_TASK = "fix the division by zero defect in the calculator"
AUTHORIZED_TRANSFORMATION = "calculator-zero-denominator-value-error-v1"
MAX_SOURCE_BYTES = 256_000
MAX_PATCH_BYTES = 16_384
MAX_CHANGED_LINES = 80
_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?: .*)?$")
_SENSITIVE_PARTS = {
    ".aws", ".ssh", ".gnupg", "credentials", "credential", "secrets", "secret",
}
_SENSITIVE_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".p7b", ".p7c", ".token", ".secret"}
_SENSITIVE_NAMES = {"id_rsa", "id_ed25519", "credentials.json", "service-account.json", ".npmrc"}
_EXPECTED_ORIGINAL = (
    "def divide(numerator, denominator):\n"
    "    return numerator / denominator\n"
)
_PROPOSED_SOURCE = (
    "def divide(numerator, denominator):\n"
    "    if denominator == 0:\n"
    "        raise ValueError(\"denominator must not be zero\")\n"
    "    return numerator / denominator\n"
)
_RUNTIME_NOT_RUN = (
    "Runtime tests were not run: no trusted isolated executor is configured. "
    "Repository code was not executed on the host."
)


def validate_relative_paths(paths: list[str]) -> list[str]:
    """Validate path syntax and uniqueness before any filesystem access."""
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_path in paths:
        if not isinstance(raw_path, str) or not raw_path or "\x00" in raw_path:
            raise ProposalValidationError("A patch contains an invalid file path.")
        if "\\" in raw_path or raw_path.startswith("/") or PureWindowsPath(raw_path).is_absolute() or PureWindowsPath(raw_path).drive:
            raise ProposalValidationError("Absolute and non-portable patch paths are not allowed.")
        parts = raw_path.split("/")
        if any(part in {"", ".", ".."} for part in parts):
            raise ProposalValidationError("Patch paths cannot contain traversal segments.")
        lower_parts = [part.lower() for part in parts]
        name = lower_parts[-1]
        if any(part in _SENSITIVE_PARTS for part in lower_parts) or name in _SENSITIVE_NAMES:
            raise ProposalValidationError("Sensitive files are outside the proposal scope.")
        if Path(name).suffix.lower() in _SENSITIVE_SUFFIXES or name.startswith(".env"):
            raise ProposalValidationError("Sensitive files are outside the proposal scope.")
        if raw_path in seen:
            raise ProposalValidationError("A patch cannot modify the same file more than once.")
        seen.add(raw_path)
        normalized.append(raw_path)
    return normalized


def validate_unified_diff(diff: str, expected_paths: list[str]) -> None:
    """Validate a single-file unified diff's headers, path scope, hunks, and size."""
    paths = validate_relative_paths(expected_paths)
    if len(paths) != 1:
        raise ProposalValidationError("A proposal must modify exactly one authorized file.")
    if not isinstance(diff, str) or not diff or len(diff.encode("utf-8")) > MAX_PATCH_BYTES:
        raise ProposalValidationError("The proposed patch is empty or exceeds the size limit.")

    lines = diff.splitlines()
    if len(lines) < 4 or not lines[0].startswith("--- a/") or not lines[1].startswith("+++ b/"):
        raise ProposalValidationError("The patch is not a valid unified diff.")
    old_path = lines[0][6:]
    new_path = lines[1][6:]
    if old_path != paths[0] or new_path != paths[0]:
        raise ProposalValidationError("The diff modifies a path outside the authorized proposal scope.")

    hunk_count = 0
    old_seen = 0
    new_seen = 0
    changed_lines = 0
    for line in lines[2:]:
        if line.startswith("@@ "):
            if hunk_count and (old_seen != old_expected or new_seen != new_expected):
                raise ProposalValidationError("The unified diff contains inconsistent hunk counts.")
            match = _HUNK_HEADER.fullmatch(line)
            if not match:
                raise ProposalValidationError("The unified diff contains a malformed hunk header.")
            old_expected = int(match.group(2) or "1")
            new_expected = int(match.group(4) or "1")
            old_seen = new_seen = 0
            hunk_count += 1
            continue
        if not hunk_count:
            raise ProposalValidationError("The unified diff has content before its first hunk.")
        if line.startswith("\\ No newline at end of file"):
            continue
        if not line or line[0] not in {" ", "+", "-"}:
            raise ProposalValidationError("The unified diff contains an invalid hunk line.")
        if line[0] in {" ", "-"}:
            old_seen += 1
        if line[0] in {" ", "+"}:
            new_seen += 1
        if line[0] in {"+", "-"}:
            changed_lines += 1
    if not hunk_count or old_seen != old_expected or new_seen != new_expected:
        raise ProposalValidationError("The unified diff is incomplete or has inconsistent hunk counts.")
    if changed_lines > MAX_CHANGED_LINES:
        raise ProposalValidationError("The patch exceeds the changed-line limit.")


def validate_python_syntax(source: str) -> bool:
    try:
        ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return False
    return True


def validate_calculator_acceptance(source: str) -> bool:
    try:
        module = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return False
    function = next(
        (node for node in module.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "divide"),
        None,
    )
    if function is None or not function.body:
        return False
    first = function.body[0]
    if not isinstance(first, ast.If):
        return False
    test = first.test
    valid_test = (
        isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Name)
        and test.left.id == "denominator"
        and len(test.ops) == 1
        and isinstance(test.ops[0], ast.Eq)
        and len(test.comparators) == 1
        and isinstance(test.comparators[0], ast.Constant)
        and test.comparators[0].value == 0
    )
    if not valid_test or len(first.body) != 1 or not isinstance(first.body[0], ast.Raise):
        return False
    raised = first.body[0].exc
    if not isinstance(raised, ast.Call) or not isinstance(raised.func, ast.Name) or raised.func.id != "ValueError":
        return False
    if not raised.args or not isinstance(raised.args[0], ast.Constant) or not isinstance(raised.args[0].value, str):
        return False
    return bool(raised.args[0].value.strip())


def _has_reparse_point(info: os.stat_result) -> bool:
    attributes = getattr(info, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse_flag)


def _read_authorized_source(settings: Settings, repository_id: str, relative_path: str) -> tuple[Path, bytes]:
    validate_relative_paths([relative_path])
    if relative_path != TARGET_PATH:
        raise ProposalValidationError("The requested file is outside the supported proposal scenario.")
    configured_root = settings.authorized_repositories.get(repository_id)
    if configured_root is None:
        raise RepositoryNotAuthorizedError()
    try:
        root = configured_root.resolve(strict=True)
        if not root.is_dir():
            raise OSError("Repository root is not a directory.")
        candidate = root
        components = relative_path.split("/")
        for index, component in enumerate(components):
            candidate = candidate / component
            info = candidate.lstat()
            if stat.S_ISLNK(info.st_mode) or _has_reparse_point(info):
                raise ProposalValidationError("Symbolic links and junctions are not valid proposal targets.")
            if index < len(components) - 1 and not stat.S_ISDIR(info.st_mode):
                raise ProposalValidationError("The target path contains a non-directory component.")
        resolved = candidate.resolve(strict=True)
        if not resolved.is_relative_to(root):
            raise ProposalValidationError("The target file escapes the authorized repository.")
        before = candidate.stat(follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_SOURCE_BYTES:
            raise ProposalValidationError("The target is not a bounded regular source file.")
        content = candidate.read_bytes()
        after = candidate.stat(follow_symlinks=False)
        if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
            raise ProposalSourceConflictError()
        if len(content) > MAX_SOURCE_BYTES or b"\x00" in content:
            raise ProposalValidationError("The target source is binary or exceeds the source-size limit.")
        content.decode("utf-8", errors="strict")
    except (UnicodeError, OSError, RuntimeError):
        raise ProposalValidationError("The authorized target source could not be safely read.") from None
    return candidate, content


class ProposalGenerationService:
    def __init__(
        self,
        settings: Settings,
        scanner: RepositoryScanner,
        task_store: InMemoryTaskPlanStore,
        proposal_store: InMemoryProposalStore,
    ) -> None:
        self.settings = settings
        self.scanner = scanner
        self.task_store = task_store
        self.proposal_store = proposal_store

    def create(self, request: CreateProposalRequest) -> CodeChangeProposal:
        stored = self.task_store.get(request.task_id)
        if stored is None:
            raise TaskPlanNotFoundError()
        plan = stored.plan
        if stored.plan_digest != self.task_store.digest_plan(plan):
            raise ProposalValidationError("The stored plan integrity check failed.")
        if (
            stored.validated_provider != plan.provider
            or stored.validated_is_mock != plan.is_mock
            or stored.analysis_snapshot_id == ""
            or not self._provider_provenance_is_valid(stored, plan, self.settings.nebius_model)
            or self.settings.inference_provider != plan.provider
        ):
            raise ProposalValidationError("The stored plan provenance could not be verified.")
        if plan.repository_id != request.repository_id:
            raise RepositoryNotAuthorizedError()
        if request.repository_id != AUTHORIZED_REPOSITORY_ID:
            raise RepositoryNotAuthorizedError()
        if request.transformation_id != AUTHORIZED_TRANSFORMATION:
            raise ProposalValidationError("The requested transformation is not allowlisted.")
        if plan.status != "planned" or not plan.human_approval_required or plan.execution_status != "not_started":
            raise ProposalValidationError("Only a valid, unstarted engineering plan can receive a proposal.")
        if plan.unsupported_references:
            raise ProposalValidationError("A plan with unsupported evidence cannot receive a proposal.")
        if " ".join(plan.task_description.casefold().split()) != AUTHORIZED_TASK:
            raise ProposalValidationError("This task is outside the predefined calculator proposal scenario.")
        if TARGET_PATH not in plan.relevant_files or not any(change.path == TARGET_PATH for change in plan.expected_code_changes):
            raise ProposalValidationError("The plan does not authorize the predefined calculator target.")
        source_reference = next((ref for ref in plan.source_references if ref.path == TARGET_PATH), None)
        if source_reference is None:
            raise ProposalValidationError("The plan has no traceable reference to the calculator source.")

        # Re-scan at proposal time. This revalidates repository authorization and that the
        # target remains within the scanner's bounded, non-symlink source inventory.
        analysis = self.scanner.analyze(request.repository_id)
        target_metadata = next((item for item in analysis.files if item.path == TARGET_PATH), None)
        if target_metadata is not None and target_metadata.size_bytes > MAX_SOURCE_BYTES:
            raise ProposalValidationError("The authorized target exceeds the proposal source-size limit.")
        if analysis.snapshot_id != stored.analysis_snapshot_id:
            raise ProposalSourceConflictError()
        if TARGET_PATH not in {item.path for item in analysis.files}:
            raise ProposalValidationError("The target file is no longer in the authorized source inventory.")
        self._validate_plan_evidence(plan, analysis)

        _, original_bytes = _read_authorized_source(self.settings, request.repository_id, TARGET_PATH)
        original_hash = hashlib.sha256(original_bytes).hexdigest()
        plan_hash = stored.source_hashes.get(TARGET_PATH)
        if not plan_hash or original_hash != plan_hash:
            raise ProposalSourceConflictError()
        try:
            original_source = original_bytes.decode("utf-8", errors="strict")
        except UnicodeError:
            raise ProposalValidationError("The target source is not valid UTF-8 text.") from None
        normalized_source = original_source.replace("\r\n", "\n")
        if normalized_source != _EXPECTED_ORIGINAL:
            raise ProposalValidationError("The calculator source does not match the supported synthetic scenario.")
        newline = "\r\n" if "\r\n" in original_source else "\n"
        proposed_source = _PROPOSED_SOURCE.replace("\n", newline)

        paths = validate_relative_paths([TARGET_PATH])
        if not validate_python_syntax(proposed_source):
            raise ProposalValidationError("The proposed Python source is syntactically invalid.")
        if not validate_calculator_acceptance(proposed_source):
            raise ProposalValidationError("The proposed source does not satisfy the calculator acceptance criterion.")
        diff = "\n".join(difflib.unified_diff(
            original_source.splitlines(),
            proposed_source.splitlines(),
            fromfile=f"a/{TARGET_PATH}",
            tofile=f"b/{TARGET_PATH}",
            lineterm="",
        )) + "\n"
        validate_unified_diff(diff, paths)
        logger.info("Generated deterministic calculator proposal task_id=%s provider=mock", plan.task_id)

        now = datetime.now(timezone.utc)
        proposal = CodeChangeProposal(
            proposal_id=uuid4(),
            repository_id=request.repository_id,
            originating_task_id=plan.task_id,
            originating_plan_provider=plan.provider,
            transformation_id=request.transformation_id,
            task_description=plan.task_description,
            target_files=[ProposalTargetFile(
                path=TARGET_PATH,
                original_sha256=original_hash,
                source_reference=source_reference,
            )],
            proposed_change_summary="Raise ValueError with a clear message when divide receives a zero denominator.",
            unified_diff=diff,
            diff_sha256=hashlib.sha256(diff.encode("utf-8")).hexdigest(),
            risk_classification="low",
            validation_findings=[
                ProposalValidationFinding(check="authorized_scope", status="passed", detail="Only the predefined authorized calculator source is targeted."),
                ProposalValidationFinding(check="source_revision", status="passed", detail="The source hash still matches the revision captured with the task plan."),
                ProposalValidationFinding(check="patch_format", status="passed", detail="The unified diff has one authorized file and consistent hunk counts."),
                ProposalValidationFinding(check="change_size", status="passed", detail="The patch is within source, byte, and changed-line limits."),
                ProposalValidationFinding(check="python_syntax", status="passed", detail="The proposed source parses successfully with Python AST; no code was executed."),
                ProposalValidationFinding(check="acceptance_criterion", status="passed", detail="The zero denominator branch raises ValueError with a non-empty message before division."),
                ProposalValidationFinding(check="runtime_isolation", status="not_run", detail="No trusted isolated executor is configured; repository tests were not run."),
            ],
            static_validation_status="passed",
            runtime_validation_status="not_run",
            runtime_validation_reason=_RUNTIME_NOT_RUN,
            provider="mock",
            is_mock=True,
            created_at=now,
            lifecycle_state="awaiting_review",
            human_approval_required=True,
        )
        self.proposal_store.put(proposal)
        return proposal

    @staticmethod
    def _provider_provenance_is_valid(stored, plan: TaskPlan, configured_model: str) -> bool:
        diagnostics = plan.inference_diagnostics
        if diagnostics is None or diagnostics.provider != plan.provider or diagnostics.is_mock != plan.is_mock:
            return False
        if stored.validated_model != diagnostics.model or not stored.provider_model_verified:
            return False
        if diagnostics.completion_status != "completed" or diagnostics.finish_reason not in {"stop", "mock_complete"}:
            return False
        if plan.provider == "mock":
            return plan.is_mock and diagnostics.model == "devrelay-mock-v1" and diagnostics.finish_reason == "mock_complete"
        return (
            plan.provider == "nebius"
            and not plan.is_mock
            and diagnostics.model == stored.validated_model == configured_model
            and diagnostics.finish_reason == "stop"
        )

    @staticmethod
    def _validate_plan_evidence(plan: TaskPlan, analysis) -> None:
        paths = {item.path for item in analysis.files}
        if any(path not in paths for path in plan.relevant_files):
            raise ProposalValidationError("The plan contains a file outside the current analysis snapshot.")
        references = {
            (item.source.path, item.source.line, item.source.end_line)
            for item in analysis.functions + analysis.classes
        }
        references.update((item.source_path, item.line, None) for item in analysis.imports)
        starts = {(path, line) for path, line, _ in references}

        def valid(reference) -> bool:
            key = (reference.path, reference.line, reference.end_line)
            return key in references if reference.end_line is not None else key in references or key[:2] in starts

        plan_references = list(plan.source_references)
        for step in plan.implementation_steps:
            plan_references.extend(step.source_references)
        if not plan_references or any(not valid(reference) for reference in plan_references):
            raise ProposalValidationError("The plan contains evidence that is not present in the current analysis snapshot.")
        if not any(reference.path == TARGET_PATH and valid(reference) for reference in plan.source_references):
            raise ProposalValidationError("The plan has no verified calculator source reference.")
        if any(change.path not in paths for change in plan.expected_code_changes):
            raise ProposalValidationError("The plan proposes a path outside the current analysis snapshot.")

    def get(self, proposal_id):
        proposal = self.proposal_store.get(proposal_id)
        if proposal is None:
            raise ProposalNotFoundError()
        return proposal


def verify_current_source_revision(settings: Settings, proposal: CodeChangeProposal) -> None:
    """Fail closed if a proposal's authorized target has changed since generation."""
    for target in proposal.target_files:
        try:
            _, source = _read_authorized_source(settings, proposal.repository_id, target.path)
        except (ProposalValidationError, RepositoryNotAuthorizedError, ProposalSourceConflictError):
            raise ProposalSourceConflictError() from None
        if hashlib.sha256(source).hexdigest() != target.original_sha256:
            raise ProposalSourceConflictError()
