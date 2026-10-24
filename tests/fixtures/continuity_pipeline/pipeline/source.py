"""Read newline-delimited records from the configured inbound location."""

import json
from pathlib import Path

from pipeline.models import RawRecord


def load_batch(path: str) -> list[RawRecord]:
    records: list[RawRecord] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        records.append(RawRecord(**item))
    return records
