#!/usr/bin/env python3
"""CLI entry point wrapping gap_steward.validate_gap_write for gap-intake.yml.
Parallels cli_validate.py: reads the issue body + account / rate-limit / existing-
gaps state from files (the Action owns all I/O; this script has no GitHub API
access of its own), writes a single JSON result to stdout.

Usage:
    python3 cli_gap.py \\
        --body-file body.txt \\
        --login alice --created-at 2024-01-01T00:00:00+00:00 \\
        --existing-gaps-file gaps_listing.json \\
        --ratelimit-file ratelimit.json \\
        --form-file .github/ISSUE_TEMPLATE/gap-log.yml

Exit code 0 always — the caller branches on the JSON "status" field, not on
exit code, so a rejection is not treated as a crash.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime

from intake_steward import AccountInfo, RateLimiter, derive_label_map, parse_issue_form_body
from gap_steward import validate_gap_write


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--body-file", required=True)
    p.add_argument("--login", required=True)
    p.add_argument("--created-at", required=True, help="ISO 8601, e.g. 2024-01-01T00:00:00+00:00")
    p.add_argument("--existing-gaps-file", required=True,
                    help="JSON list of the .md filenames currently in gaps/")
    p.add_argument("--ratelimit-file", required=True, help="JSON rate-limiter state, read AND rewritten")
    p.add_argument("--form-file", required=True,
                    help="Path to ISSUE_TEMPLATE/gap-log.yml — the label->id map is derived from it")
    args = p.parse_args()

    with open(args.body_file, encoding="utf-8") as f:
        body = f.read()
    with open(args.existing_gaps_file, encoding="utf-8") as f:
        existing_gaps = set(json.load(f))
    with open(args.ratelimit_file, encoding="utf-8") as f:
        limiter = RateLimiter.from_json(f.read())
    with open(args.form_file, encoding="utf-8") as f:
        label_to_id = derive_label_map(f.read())

    fields = parse_issue_form_body(body, label_to_id)
    account = AccountInfo(login=args.login, created_at=datetime.fromisoformat(args.created_at))

    result = validate_gap_write(
        fields,
        account=account,
        existing_gaps=existing_gaps,
        limiter=limiter,
    )

    # limiter mutated in place on accept — persist for the next run
    with open(args.ratelimit_file, "w", encoding="utf-8") as f:
        f.write(limiter.to_json())

    print(json.dumps({
        "status": result.status,
        "reasons": result.reasons,
        "operation": result.operation,
        "filename": result.filename,
        "record_text": result.record_text,
        "new_status": result.new_status,
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
