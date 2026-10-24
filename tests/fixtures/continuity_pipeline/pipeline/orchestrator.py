"""Coordinate the nightly ingestion and report workflow."""

import logging

from pipeline.config import PipelineConfig
from pipeline.models import BatchResult
from pipeline.output import publish_report
from pipeline.retry import retry_transient
from pipeline.source import load_batch
from pipeline.transform import transform_record
from pipeline.validation import validate_record

logger = logging.getLogger(__name__)


def run_nightly(config: PipelineConfig) -> BatchResult:
    records = retry_transient(
        lambda: load_batch(config.input_path),
        config.retry_attempts,
        config.retry_delay_seconds,
    )
    accepted = []
    rejected = 0
    for record in records:
        valid, reason = validate_record(record)
        if not valid:
            rejected += 1
            logger.warning("Record rejected: %s", reason)
            continue
        accepted.append(transform_record(record))

    result = BatchResult(
        expected_count=len(records),
        accepted_count=len(accepted),
        rejected_count=rejected,
        rows=tuple(accepted),
    )
    publish_report(config.output_path, result)
    return result
