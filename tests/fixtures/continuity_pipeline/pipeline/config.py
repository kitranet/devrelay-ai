"""Runtime configuration for the synthetic nightly pipeline."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PipelineConfig:
    input_path: str = "data/incoming.jsonl"
    output_path: str = "data/reports/nightly.json"
    retry_attempts: int = 3
    retry_delay_seconds: float = 0.25
    minimum_valid_fraction: float = 0.98
