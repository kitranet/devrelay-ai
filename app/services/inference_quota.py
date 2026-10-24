"""Durable, fail-closed request allowance for live Nebius inference."""

from __future__ import annotations

import sqlite3
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.core.errors import InferenceQuotaExceededError, InferenceQuotaUnavailableError

MAX_CONFIGURED_QUOTA = 100_000


@dataclass(frozen=True)
class QuotaSnapshot:
    total: int
    used: int

    @property
    def remaining(self) -> int:
        return max(0, self.total - self.used)


class InferenceQuota(Protocol):
    def reserve(self) -> QuotaSnapshot: ...
    def snapshot(self) -> QuotaSnapshot: ...


class SQLiteInferenceQuota:
    """An atomic single-host counter. Reservations are never refunded automatically."""

    def __init__(self, database_path: Path, initial_total: int) -> None:
        if not 0 <= initial_total <= MAX_CONFIGURED_QUOTA:
            raise ValueError("initial_total is outside the supported range")
        self.database_path = database_path
        self.initial_total = initial_total

    def _connect(self) -> sqlite3.Connection:
        connection: sqlite3.Connection | None = None
        try:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.database_path, timeout=5, isolation_level=None)
            if os.name == "posix":
                os.chmod(self.database_path, 0o600)
            connection.execute("PRAGMA busy_timeout=5000")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS inference_quota ("
                "singleton INTEGER PRIMARY KEY CHECK (singleton = 1), "
                "total INTEGER NOT NULL CHECK (total >= 0), "
                "used INTEGER NOT NULL CHECK (used >= 0 AND used <= total))"
            )
            connection.execute(
                "INSERT OR IGNORE INTO inference_quota(singleton, total, used) VALUES (1, ?, 0)",
                (self.initial_total,),
            )
            return connection
        except (OSError, sqlite3.Error) as exc:
            if connection is not None:
                connection.close()
            raise InferenceQuotaUnavailableError() from exc

    def snapshot(self) -> QuotaSnapshot:
        connection = self._connect()
        try:
            row = connection.execute("SELECT total, used FROM inference_quota WHERE singleton = 1").fetchone()
            if row is None:
                raise InferenceQuotaUnavailableError()
            return QuotaSnapshot(total=int(row[0]), used=int(row[1]))
        except sqlite3.Error as exc:
            raise InferenceQuotaUnavailableError() from exc
        finally:
            connection.close()

    def reserve(self) -> QuotaSnapshot:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT total, used FROM inference_quota WHERE singleton = 1").fetchone()
            if row is None:
                raise InferenceQuotaUnavailableError()
            total, used = int(row[0]), int(row[1])
            if used >= total:
                connection.execute("ROLLBACK")
                raise InferenceQuotaExceededError()
            used += 1
            connection.execute("UPDATE inference_quota SET used = ? WHERE singleton = 1", (used,))
            connection.execute("COMMIT")
            return QuotaSnapshot(total=total, used=used)
        except (InferenceQuotaExceededError, InferenceQuotaUnavailableError):
            raise
        except sqlite3.Error as exc:
            try:
                connection.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise InferenceQuotaUnavailableError() from exc
        finally:
            connection.close()

    def set_total(self, total: int) -> QuotaSnapshot:
        if not 0 <= total <= MAX_CONFIGURED_QUOTA:
            raise ValueError("total is outside the supported range")
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT used FROM inference_quota WHERE singleton = 1").fetchone()
            if row is None or total < int(row[0]):
                connection.execute("ROLLBACK")
                raise ValueError("total cannot be lower than already reserved requests")
            connection.execute("UPDATE inference_quota SET total = ? WHERE singleton = 1", (total,))
            connection.execute("COMMIT")
        except ValueError:
            raise
        except sqlite3.Error as exc:
            try:
                connection.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise InferenceQuotaUnavailableError() from exc
        finally:
            connection.close()
        return self.snapshot()


class InMemoryInferenceQuota:
    """Explicit test double; never used by application configuration."""

    def __init__(self, total: int) -> None:
        self._snapshot = QuotaSnapshot(total=total, used=0)

    def reserve(self) -> QuotaSnapshot:
        if self._snapshot.used >= self._snapshot.total:
            raise InferenceQuotaExceededError()
        self._snapshot = QuotaSnapshot(self._snapshot.total, self._snapshot.used + 1)
        return self._snapshot

    def snapshot(self) -> QuotaSnapshot:
        return self._snapshot
