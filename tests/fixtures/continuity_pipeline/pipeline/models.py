"""Data contracts shared across ingestion and report generation."""

from pydantic import BaseModel


class RawRecord(BaseModel):
    record_id: str
    account_code: str
    amount: str


class ReportRow(BaseModel):
    record_id: str
    account_code: str
    amount_cents: int


class BatchResult(BaseModel):
    expected_count: int
    accepted_count: int
    rejected_count: int
    rows: tuple[ReportRow, ...]
