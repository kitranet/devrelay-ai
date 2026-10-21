"""Interface for a future trusted, isolated runtime-validation service.

No local implementation executes repository code. Deployments can inject an
implementation only after providing a disposable sandbox with strict limits.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True)
class RuntimeValidationResult:
    status: Literal["passed", "failed", "not_run"]
    detail: str


class IsolatedRuntimeValidator(Protocol):
    """Validate a proposed snapshot without granting access to the host."""

    async def validate(self, *, source_snapshot: bytes, unified_diff: str) -> RuntimeValidationResult:
        """Run checks in an isolated, bounded environment and return a result."""


class UnavailableRuntimeValidator:
    """Fail-closed marker used while no trusted sandbox is configured."""

    async def validate(self, *, source_snapshot: bytes, unified_diff: str) -> RuntimeValidationResult:
        del source_snapshot, unified_diff
        return RuntimeValidationResult(
            status="not_run",
            detail="No trusted isolated executor is configured; repository code was not executed on the host.",
        )
