"""Validate raw records before transformation."""

from pipeline.models import RawRecord


def validate_record(record: RawRecord) -> tuple[bool, str | None]:
    if not record.record_id.strip():
        return False, "missing record id"
    if not record.account_code.strip():
        return False, "missing account code"
    try:
        amount = float(record.amount)
    except (TypeError, ValueError):
        return False, "amount is not numeric"
    if amount < 0:
        return False, "amount is negative"
    return True, None
