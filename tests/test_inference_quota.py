from concurrent.futures import ThreadPoolExecutor

import pytest

from app.core.errors import InferenceQuotaExceededError, InferenceQuotaUnavailableError
from app.services.inference_quota import SQLiteInferenceQuota


def test_quota_reservations_persist_across_instances_and_configuration_changes(tmp_path):
    path = tmp_path / "quota.sqlite3"
    first = SQLiteInferenceQuota(path, initial_total=2)
    assert first.snapshot().remaining == 2
    assert first.reserve().used == 1

    restarted = SQLiteInferenceQuota(path, initial_total=99)
    assert restarted.snapshot().total == 2
    assert restarted.reserve().remaining == 0
    with pytest.raises(InferenceQuotaExceededError):
        restarted.reserve()


def test_concurrent_reservations_never_exceed_quota(tmp_path):
    quota = SQLiteInferenceQuota(tmp_path / "quota.sqlite3", initial_total=4)

    def reserve(_):
        try:
            quota.reserve()
            return "reserved"
        except InferenceQuotaExceededError:
            return "denied"

    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(reserve, range(24)))

    assert results.count("reserved") == 4
    assert results.count("denied") == 20
    assert quota.snapshot().used == 4


def test_quota_total_cannot_be_lowered_below_already_reserved_requests(tmp_path):
    quota = SQLiteInferenceQuota(tmp_path / "quota.sqlite3", initial_total=3)
    quota.reserve()
    quota.reserve()
    with pytest.raises(ValueError):
        quota.set_total(1)
    assert quota.snapshot().total == 3


def test_unavailable_quota_storage_fails_closed(tmp_path):
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("file blocks quota directory", encoding="utf-8")
    quota = SQLiteInferenceQuota(blocker / "quota.sqlite3", initial_total=1)
    with pytest.raises(InferenceQuotaUnavailableError):
        quota.reserve()
