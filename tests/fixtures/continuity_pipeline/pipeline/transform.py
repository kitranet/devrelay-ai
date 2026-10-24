"""Normalize validated records into report rows."""

from pipeline.models import RawRecord, ReportRow


def transform_record(record: RawRecord) -> ReportRow:
    cents = round(float(record.amount) * 100)
    return ReportRow(
        record_id=record.record_id.strip(),
        account_code=record.account_code.strip().upper(),
        amount_cents=cents,
    )
