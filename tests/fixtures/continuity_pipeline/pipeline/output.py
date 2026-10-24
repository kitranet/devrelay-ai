"""Publish the generated report as JSON."""

import json
from pathlib import Path

from pipeline.models import BatchResult


def publish_report(path: str, result: BatchResult) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "expected_count": result.expected_count,
        "accepted_count": result.accepted_count,
        "rejected_count": result.rejected_count,
        "rows": [row.model_dump() for row in result.rows],
    }
    destination.write_text(json.dumps(payload, indent=2), encoding="utf-8")
