"""Retry transient operations with a bounded attempt count."""

import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


def retry_transient(operation: Callable[[], T], attempts: int, delay_seconds: float) -> T:
    last_error: TimeoutError | None = None
    for attempt in range(attempts):
        try:
            return operation()
        except TimeoutError as error:
            last_error = error
            if attempt + 1 < attempts:
                time.sleep(delay_seconds)
    assert last_error is not None
    raise last_error
