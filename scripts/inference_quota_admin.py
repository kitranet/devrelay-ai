"""Local operator CLI for changing the durable live-inference allowance."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from app.services.inference_quota import SQLiteInferenceQuota
from app.services.inference_quota import MAX_CONFIGURED_QUOTA


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("show", help="show the current durable request allowance")
    set_total = actions.add_parser("set-total", help="set the total allowance (cannot lower below used count)")
    set_total.add_argument("total", type=int)
    args = parser.parse_args()

    if args.action == "set-total" and not 0 <= args.total <= MAX_CONFIGURED_QUOTA:
        parser.error(f"total must be between 0 and {MAX_CONFIGURED_QUOTA}")

    database_path = Path(os.getenv("NEBIUS_QUOTA_DB_PATH", ".devrelay-state/nebius-quota.sqlite3"))
    initial_total = int(os.getenv("NEBIUS_TOTAL_INFERENCE_QUOTA", "0"))
    quota = SQLiteInferenceQuota(database_path, initial_total)
    snapshot = quota.snapshot() if args.action == "show" else quota.set_total(args.total)
    print(f"Quota requests: total={snapshot.total}, used={snapshot.used}, remaining={snapshot.remaining}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
