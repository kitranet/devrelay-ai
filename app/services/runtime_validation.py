"""Fail-closed runtime validation orchestration and sandbox executor boundary."""

from __future__ import annotations

import hashlib
import platform
import re
import shutil
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4

from app.core.config import Settings
from app.core.errors import (
    ProposalNotFoundError,
    ProposalSourceConflictError,
    ProposalValidationError,
    ProposalVersionConflictError,
    RepositoryNotAuthorizedError,
    RuntimeAuthorizationConflictError,
    RuntimeValidationDisabledError,
    RuntimeValidationNotFoundError,
    TaskPlanNotFoundError,
)
from app.models.proposal import CodeChangeProposal
from app.models.runtime_validation import (
    RUNTIME_TEST_COMMAND_ID,
    RuntimeValidationEvidence,
    RuntimeValidationRequest,
    SandboxExecutionResult,
    SandboxReadiness,
    SandboxReadinessCheck,
)
from app.services.proposal_generation import TARGET_PATH, validate_unified_diff, verify_current_source_revision
from app.services.proposal_store import (
    InMemoryProposalStore,
    InMemoryReviewStore,
    InMemoryRuntimeValidationStore,
    InMemoryTaskPlanStore,
)

SUPPORTED_REPOSITORY_ID = "planning-fixture"
SUPPORTED_TEST_CASE = "calculator_unit_tests"
TEST_FILE_PATH = "tests/test_calculator.py"
MAX_SNAPSHOT_FILE_BYTES = 256_000
MAX_LOG_BYTES = 8_192
_EXPECTED_TEST_SOURCE = (
    "from package.calculator import divide\n\n\n"
    "def test_divide():\n    assert divide(6, 2) == 3\n"
).encode("utf-8")
_SECRET_LIKE = re.compile(
    r"(?i)(?:-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"(?:api[_-]?key|access[_-]?token|password|secret)\s*[:=]\s*\S+|"
    r"nvapi-[A-Za-z0-9_-]{16,}|sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,})"
)
_WINDOWS_ABSOLUTE_PATH = re.compile(r"(?i)\b[A-Z]:\\[^\s\"'<>|]+")
_UNIX_ABSOLUTE_PATH = re.compile(r"(?<![\w.])/(?:[^\s\"'<>|]+/)*[^\s\"'<>|]+")


@dataclass(frozen=True)
class SandboxInput:
    """Bounded in-memory source snapshot and patch; it contains no host mount path."""

    files: dict[str, bytes]
    target_path: str
    unified_diff: str
    test_case: str
    test_command_id: str
    source_sha256: str
    diff_sha256: str


class SandboxExecutor(Protocol):
    def readiness(self, *, enabled: bool, environment: str) -> SandboxReadiness: ...

    def execute(self, evidence_id: UUID, sandbox_input: SandboxInput) -> SandboxExecutionResult: ...

    def cleanup(self, evidence_id: UUID) -> bool: ...


class UnavailableSandboxExecutor:
    """Production executor for this checkout: reports readiness and never launches code."""

    def readiness(self, *, enabled: bool, environment: str) -> SandboxReadiness:
        linux_host = platform.system() == "Linux"
        docker_cli = shutil.which("docker") is not None
        checks = [
            SandboxReadinessCheck(
                name="development_feature_flag",
                status="passed" if enabled and environment.strip().lower() == "development" else "failed",
                detail="Dedicated runtime-validation flag is enabled in development." if enabled and environment.strip().lower() == "development" else "ENABLE_ISOLATED_RUNTIME_VALIDATION is disabled or the environment is not development.",
            ),
            SandboxReadinessCheck(
                name="linux_sandbox_host",
                status="passed" if linux_host else "failed",
                detail="Linux host detected." if linux_host else "A dedicated Linux sandbox host is required; this host is not Linux.",
            ),
            SandboxReadinessCheck(
                name="docker_cli",
                status="passed" if docker_cli else "failed",
                detail="Docker CLI is available." if docker_cli else "Docker CLI is unavailable; daemon and image checks were not attempted.",
            ),
            SandboxReadinessCheck(
                name="pinned_local_image",
                status="failed",
                detail="No immutable sandbox image digest has been verified as locally available.",
            ),
            SandboxReadinessCheck(
                name="hardened_executor",
                status="failed",
                detail="No production sandbox launcher is configured to enforce and verify all required controls.",
            ),
        ]
        available = all(check.status == "passed" for check in checks)
        status = "ready" if available else "disabled" if not enabled or environment.strip().lower() != "development" else "sandbox_unavailable"
        return SandboxReadiness(
            enabled=enabled and environment.strip().lower() == "development",
            environment=environment,
            available=available,
            status=status,
            checks=checks,
            limitations=[
                "No repository test code is run on the host.",
                "No trusted disposable sandbox is configured in this checkout.",
                "Container isolation would still share the host kernel and is not a complete security boundary.",
            ],
        )

    def execute(self, evidence_id: UUID, sandbox_input: SandboxInput) -> SandboxExecutionResult:
        del evidence_id, sandbox_input
        return SandboxExecutionResult(
            status="sandbox_unavailable",
            failure_reason="No verified isolated sandbox executor is configured; test code was not run.",
            sandbox_summary="Runtime execution refused because sandbox readiness checks failed.",
        )

    def cleanup(self, evidence_id: UUID) -> bool:
        del evidence_id
        return True


class RuntimeValidationService:
    def __init__(
        self,
        settings: Settings,
        proposals: InMemoryProposalStore,
        plans: InMemoryTaskPlanStore,
        reviews: InMemoryReviewStore,
        evidence: InMemoryRuntimeValidationStore,
        executor: SandboxExecutor,
    ) -> None:
        self.settings = settings
        self.proposals = proposals
        self.plans = plans
        self.reviews = reviews
        self.evidence = evidence
        self.executor = executor

    def readiness(self) -> SandboxReadiness:
        return self.executor.readiness(
            enabled=self.settings.enable_isolated_runtime_validation,
            environment=self.settings.environment,
        )

    def request(self, request: RuntimeValidationRequest) -> RuntimeValidationEvidence:
        if not self.settings.enable_isolated_runtime_validation or self.settings.environment.strip().lower() != "development":
            raise RuntimeValidationDisabledError()
        proposal = self._validated_proposal(request)
        readiness = self.readiness()
        now = datetime.now(timezone.utc)
        evidence = RuntimeValidationEvidence(
            evidence_id=uuid4(),
            proposal_id=proposal.proposal_id,
            repository_id=proposal.repository_id,
            status="authorized" if readiness.available else "sandbox_unavailable",
            requested_at=now,
            completed_at=None if readiness.available else now,
            proposal_version=proposal.version,
            source_sha256=request.source_sha256,
            diff_sha256=request.diff_sha256,
            test_case=request.test_case,
            authorizer_identifier=request.authorization.authorizer_identifier,
            authorization_purpose=request.authorization.purpose,
            sandbox_summary=(
                "All configured readiness checks passed; execution is delegated to the isolated sandbox."
                if readiness.available else "Runtime execution refused because one or more sandbox readiness checks failed."
            ),
            readiness_checks=readiness.checks,
            failure_reason=None if readiness.available else "No trusted isolated sandbox is available; no test code was run.",
        )
        if not readiness.available:
            if not self.evidence.reserve(evidence):
                raise RuntimeAuthorizationConflictError()
            return evidence

        # The allowlisted source snapshot is read-only and bounded. The adapter receives
        # bytes, never a host path or mount point, and applies the patch inside its boundary.
        sandbox_input = self._build_input(proposal, request)
        if not self.evidence.reserve(evidence):
            raise RuntimeAuthorizationConflictError()
        running = evidence.model_copy(update={"status": "running"})
        self.evidence.update(running)
        result: SandboxExecutionResult
        cleanup_ok = False
        try:
            result = self.executor.execute(evidence.evidence_id, sandbox_input)
        except TimeoutError:
            result = SandboxExecutionResult(status="timed_out", failure_reason="The isolated test command exceeded its wall-clock timeout.")
        except Exception:
            result = SandboxExecutionResult(status="failed", failure_reason="The isolated sandbox failed without a safe result.")
        finally:
            try:
                cleanup_ok = self.executor.cleanup(evidence.evidence_id)
            except Exception:
                cleanup_ok = False
        if not cleanup_ok:
            result = SandboxExecutionResult(
                status="failed",
                failure_reason="Sandbox cleanup could not be verified; the run is not considered successful.",
                sandbox_summary="Isolated execution completed, but disposable environment cleanup could not be verified.",
            )
        completed = evidence.model_copy(update={
            "status": result.status,
            "completed_at": datetime.now(timezone.utc),
            "exit_code": result.exit_code,
            "duration_ms": result.duration_ms,
            "stdout": _safe_log(result.stdout),
            "stderr": _safe_log(result.stderr),
            "test_results": [_safe_text(item, 500) for item in result.test_results[:100]],
            "failure_reason": _safe_text(result.failure_reason, 500) if result.failure_reason else None,
            "sandbox_summary": _safe_text(result.sandbox_summary, 500),
        })
        self.evidence.update(completed)
        return completed

    def get(self, evidence_id: UUID) -> RuntimeValidationEvidence:
        item = self.evidence.get(evidence_id)
        if item is None:
            raise RuntimeValidationNotFoundError()
        return item

    def latest_for_proposal(self, proposal_id: UUID) -> RuntimeValidationEvidence | None:
        return self.evidence.latest_for_proposal(proposal_id)

    def _validated_proposal(self, request: RuntimeValidationRequest) -> CodeChangeProposal:
        proposal = self.proposals.get(request.proposal_id)
        if proposal is None:
            raise ProposalNotFoundError()
        if proposal.lifecycle_state != "review_approved" or not proposal.human_approval_required:
            raise ProposalValidationError("Only an approved, eligible proposal can be submitted for isolated validation.")
        if proposal.repository_id != SUPPORTED_REPOSITORY_ID or len(proposal.target_files) != 1 or proposal.target_files[0].path != TARGET_PATH:
            raise ProposalValidationError("Only the fixed synthetic calculator proposal is supported.")
        if request.proposal_version != proposal.version:
            raise ProposalVersionConflictError()
        target_hash = proposal.target_files[0].original_sha256
        diff_hash = hashlib.sha256(proposal.unified_diff.encode("utf-8")).hexdigest()
        if request.source_sha256 != target_hash or request.diff_sha256 != diff_hash or proposal.diff_sha256 != diff_hash:
            raise ProposalVersionConflictError()
        if proposal.static_validation_status != "passed" or proposal.provider != "mock" or not proposal.is_mock:
            raise ProposalValidationError("The proposal has not passed the required static checks.")
        reviews = self.reviews.history(proposal.proposal_id)
        approved = next((review for review in reversed(reviews) if review.proposal_lifecycle_state == "review_approved"), None)
        if approved is None or approved.decision != "approve" or approved.source_sha256 != target_hash or approved.diff_sha256 != diff_hash:
            raise ProposalValidationError("A matching recorded human review approval is required before execution authorization.")
        plan = self.plans.get(proposal.originating_task_id)
        if plan is None:
            raise TaskPlanNotFoundError()
        if plan.plan.repository_id != SUPPORTED_REPOSITORY_ID or plan.plan.provider != "mock" or not plan.plan.is_mock:
            raise ProposalValidationError("Only the fixed mock calculator task plan is supported.")
        verify_current_source_revision(self.settings, proposal)
        validate_unified_diff(proposal.unified_diff, [target.path for target in proposal.target_files])
        return proposal

    def _build_input(self, proposal: CodeChangeProposal, request: RuntimeValidationRequest) -> SandboxInput:
        if request.test_case != SUPPORTED_TEST_CASE:
            raise ProposalValidationError("The requested runtime test case is not allowlisted.")
        root = self.settings.authorized_repositories.get(SUPPORTED_REPOSITORY_ID)
        if root is None:
            raise RepositoryNotAuthorizedError()
        try:
            resolved_root = root.resolve(strict=True)
            files: dict[str, bytes] = {}
            for relative_path in (TARGET_PATH, TEST_FILE_PATH):
                candidate = resolved_root
                for index, part in enumerate(relative_path.split("/")):
                    candidate = candidate / part
                    info = candidate.lstat()
                    attributes = getattr(info, "st_file_attributes", 0)
                    if stat.S_ISLNK(info.st_mode) or attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
                        raise ProposalValidationError("The fixed sandbox snapshot contains a link or reparse point.")
                    if index < len(relative_path.split("/")) - 1 and not stat.S_ISDIR(info.st_mode):
                        raise ProposalValidationError("The fixed sandbox snapshot contains an invalid directory path.")
                if not candidate.resolve(strict=True).is_relative_to(resolved_root):
                    raise ProposalValidationError("The fixed sandbox snapshot escapes the authorized repository.")
                if not stat.S_ISREG(candidate.stat(follow_symlinks=False).st_mode) or candidate.stat().st_size > MAX_SNAPSHOT_FILE_BYTES:
                    raise ProposalValidationError("The fixed sandbox snapshot contains an unsupported file.")
                files[relative_path] = candidate.read_bytes()
            current_source = files[TARGET_PATH]
            if hashlib.sha256(current_source).hexdigest() != request.source_sha256:
                raise ProposalSourceConflictError()
            normalized_test = files[TEST_FILE_PATH].replace(b"\r\n", b"\n")
            if normalized_test != _EXPECTED_TEST_SOURCE:
                raise ProposalValidationError("The synthetic calculator test file differs from the fixed allowlisted case.")
        except (OSError, RuntimeError):
            raise ProposalValidationError("The fixed synthetic snapshot could not be safely prepared.") from None
        return SandboxInput(
            files=files,
            target_path=TARGET_PATH,
            unified_diff=proposal.unified_diff,
            test_case=request.test_case,
            test_command_id=RUNTIME_TEST_COMMAND_ID,
            source_sha256=request.source_sha256,
            diff_sha256=request.diff_sha256,
        )


def _safe_text(value: str, limit: int) -> str:
    sanitized = _SECRET_LIKE.sub("[redacted]", value)
    sanitized = _WINDOWS_ABSOLUTE_PATH.sub("[host path redacted]", sanitized)
    sanitized = _UNIX_ABSOLUTE_PATH.sub("[path redacted]", sanitized)
    encoded = sanitized.encode("utf-8")[:limit]
    return encoded.decode("utf-8", errors="ignore")


def _safe_log(value: str) -> str:
    return _safe_text(value, MAX_LOG_BYTES)
