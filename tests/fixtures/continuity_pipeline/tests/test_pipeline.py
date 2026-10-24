"""Characterization tests for the synthetic nightly pipeline."""

from pipeline.config import PipelineConfig
from pipeline.models import RawRecord
from pipeline.transform import transform_record
from pipeline.validation import validate_record


def test_validation_rejects_non_numeric_amount():
    valid, reason = validate_record(RawRecord("r-1", "acct", "unknown"))
    assert not valid
    assert reason == "amount is not numeric"


def test_transform_normalizes_account_and_amount():
    row = transform_record(RawRecord("r-1", "north-1", "12.50"))
    assert row.account_code == "NORTH-1"
    assert row.amount_cents == 1_250


def test_config_has_quality_threshold():
    assert PipelineConfig().minimum_valid_fraction == 0.98
