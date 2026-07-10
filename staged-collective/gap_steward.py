#!/usr/bin/env python3
"""Collective gap steward — the lighter-gated write path for the `gaps/` folder.

Sibling to intake_steward.py. Where the entry steward gates a submission into a
human-merged PR, this one validates a gap-folder write and lets it AUTO-MERGE
(via gap-intake.yml + gap-diff-shape-check.yml), because a gap record is working
scratch that updates every training session, not permanent canon. That trade is
only safe because the write is physically sandboxed — the invariants below, plus
gap-diff-shape-check.yml's independent diff assertion, are what enforce it.

Reuses intake_steward's injection/secret/moderation scans, rate limiter, and
account model VERBATIM (single source of truth — a gap submission is untrusted
public text like any other). Adds only gap-specific rules:

  - Two operations: CREATE a new gap file, or APPEND a session block to one.
  - The target path is server-validated: it must be a bare "<slug>.md" living
    directly under gaps/. No subdirectories, no traversal, no writing anywhere
    but gaps/. A create derives its own filename; a caller never chooses a path.
  - Append-only: this path emits a session block to append; it never rewrites a
    prior block. (gap-diff-shape-check.yml enforces "no deletions" at the diff.)
  - Status may advance only to open / accumulating / converging. It can NEVER be
    set to closed (or closed:pending-review) here — closure is the entry
    pipeline's or a human's job (TRAINING_MODE.md Gate 7). The one write surface
    that can auto-merge must never be able to declare a gap resolved.

Pure standard library. Does not touch git or the filesystem beyond reading what
it is given — gap-intake.yml performs the actual append/commit. See
test_gap_steward.py for the adversarial suite this must survive.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone

# Reused verbatim from the entry steward — one source of truth for every scan
# and for identity/rate-limit logic. A gap submission gets the exact same
# screening an entry does; only the schema and the merge gate differ.
from intake_steward import (
    AccountInfo,
    DAILY_CAP,
    DAILY_CAP_NEW_ACCOUNT,
    MAX_FIELD_LEN,
    MAX_TOTAL_LEN,
    RateLimiter,
    is_new_account,
    scan_injection,
    scan_moderation,
    scan_secrets,
)

# --------------------------------------------------------------------------- vocab

# Gate 3 classification — decides whether an artifact was mandatory upstream;
# stored here so later sessions and the folder's own tooling can see it.
GAP_TYPES = {"fact-lookup", "fit", "reaction"}

# The ONLY statuses this lighter path may write. "closed" and
# "closed:pending-review" are excluded on purpose: a gap closes only via the
# entry-intake pipeline (a mined entry a human merged) or a human editing the
# file directly. A steward that can auto-merge must never be able to close a gap.
WRITABLE_STATUSES = {"open", "accumulating", "converging"}
FORBIDDEN_STATUSES = {"closed", "closed:pending-review"}

# A gap filename is always a bare slug + .md, directly under gaps/. This regex
# alone rejects any path separator or traversal (neither "/" nor "." other than
# the trailing ".md" can match); derive_gap_filename re-asserts it in depth.
GAP_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*\.md$")

CREATE_REQUIRED = ["gap", "domain", "gap-type", "origin", "closure"]
SESSION_REQUIRED = ["session-date", "session-mode", "scenario", "mined"]

_SLUG_SAFE_RE = re.compile(r"[^a-z0-9-]+")


# --------------------------------------------------------------------------- filename

def _gap_slugify(text: str, maxlen: int = 50) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_only.lower().strip()
    slug = _SLUG_SAFE_RE.sub("-", lowered).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)[:maxlen].strip("-")
    return slug or "untitled"


def derive_gap_filename(domain: str, gap_statement: str) -> str:
    """Server-derived gap filename: <domain-slug>--<statement-slug>.md. Never
    taken from user input as a path — same defense as the entry steward's
    derive_slug: the caller cannot choose where a write lands."""
    name = f"{_gap_slugify(domain)}--{_gap_slugify(gap_statement)}.md"
    if "/" in name or ".." in name or "\x00" in name:
        raise ValueError("derived gap filename failed path-safety assertion")
    return name


# --------------------------------------------------------------------------- schema

def check_gap_schema(
    fields: dict[str, str], existing_gaps: set[str]
) -> tuple[list[str], str | None, str | None]:
    """Validate a gap submission. Returns (errors, operation, filename).
    operation is 'create' or 'append'; filename is the target under gaps/."""
    errors: list[str] = []

    operation = fields.get("operation", "").strip().lower()
    if operation not in ("create", "append"):
        return (["operation must be 'create' or 'append'"], None, None)

    # length guards, same limits as entries
    total_len = sum(len(v) for v in fields.values())
    if total_len > MAX_TOTAL_LEN:
        errors.append(f"submission too large ({total_len} chars, max {MAX_TOTAL_LEN})")
    for name, value in fields.items():
        if len(value) > MAX_FIELD_LEN:
            errors.append(f"field '{name}' too large ({len(value)} chars, max {MAX_FIELD_LEN})")

    # status — the never-close invariant lives here
    status = fields.get("status", "").strip().lower()
    if status in FORBIDDEN_STATUSES:
        errors.append(
            "this path can never set a gap to 'closed' — closure needs a mined entry "
            "merged through the entry pipeline, or a human"
        )
    elif status not in WRITABLE_STATUSES:
        errors.append(f"status must be one of {', '.join(sorted(WRITABLE_STATUSES))}")

    filename: str | None = None

    if operation == "create":
        for name in CREATE_REQUIRED:
            if not fields.get(name, "").strip():
                errors.append(f"missing required field '{name}' for a new gap")
        gtype = fields.get("gap-type", "").strip().lower()
        if gtype and gtype not in GAP_TYPES:
            errors.append(f"gap type '{gtype}' is not one of {', '.join(sorted(GAP_TYPES))}")
        # a create may include an optional first session block; if a session
        # date is given, the whole block must be complete
        if fields.get("session-date", "").strip():
            errors.extend(_session_errors(fields))
        if not errors:
            try:
                filename = derive_gap_filename(fields.get("domain", ""), fields.get("gap", ""))
            except ValueError as e:
                return ([str(e)], None, None)
            if filename in existing_gaps:
                errors.append(
                    f"a gap named '{filename}' already exists — append to it instead of creating a duplicate"
                )

    else:  # append
        target = fields.get("target", "").strip()
        if not GAP_SLUG_RE.match(target):
            errors.append(
                "append target must be a bare '<slug>.md' filename under gaps/ — no paths, no traversal"
            )
        elif target not in existing_gaps:
            errors.append(f"append target '{target}' does not exist — create it first, or fix the name")
        else:
            filename = target
        # an append always logs a session — that's why you're appending
        errors.extend(_session_errors(fields))

    return (errors, operation, filename)


def _session_errors(fields: dict[str, str]) -> list[str]:
    errs = []
    for name in SESSION_REQUIRED:
        if not fields.get(name, "").strip():
            errs.append(f"missing required session field '{name}'")
    mode = fields.get("session-mode", "").strip().lower()
    if mode and mode not in ("teacher", "playmate"):
        errs.append("session-mode must be 'teacher' or 'playmate'")
    return errs


# --------------------------------------------------------------------------- record building
# Built only AFTER every scan has passed (see validate_gap_write), so the text
# committed is text already cleared by injection/secret/moderation screening.

def _build_session_block(f: dict[str, str]) -> str:
    date = f.get("session-date", "").strip()
    mode = f.get("session-mode", "").strip().lower()
    return (
        f"### {date} · {mode}\n"
        f"- **Scenario / mad-lib:** {f.get('scenario', '').strip()}\n"
        f"- **User inputs:** {f.get('user-inputs', '').strip()}\n"
        f"- **Artifacts:** {f.get('artifacts', '').strip()}\n"
        f"- **Steer / outcome:** {f.get('steer', '').strip()}\n"
        f"- **Mined:** {f.get('mined', '').strip()}\n"
        f"- **Left open:** {f.get('left-open', '').strip()}\n"
    )


def build_new_gap_file(f: dict[str, str]) -> str:
    status = f.get("status", "").strip().lower()
    text = (
        f"# Gap: {f.get('gap', '').strip()}\n\n"
        f"- **Domain:** {f.get('domain', '').strip()}\n"
        f"- **Type:** {f.get('gap-type', '').strip().lower()}\n"
        f"- **Status:** {status}\n"
        f"- **Origin:** {f.get('origin', '').strip()}\n"
        f"- **Closure condition:** {f.get('closure', '').strip()}\n\n"
        f"## Sessions\n\n"
    )
    if f.get("session-date", "").strip():
        text += _build_session_block(f)
    return text


# --------------------------------------------------------------------------- result

@dataclass
class GapResult:
    status: str  # "accept" | "reject" | "moderation_hold"
    reasons: list[str] = field(default_factory=list)
    operation: str | None = None  # "create" | "append"
    filename: str | None = None   # target file under gaps/
    record_text: str | None = None  # create: full file; append: the block to append
    new_status: str | None = None   # the header Status the append should set


def validate_gap_write(
    raw_fields: dict[str, str],
    *,
    account: AccountInfo,
    existing_gaps: set[str],
    limiter: RateLimiter,
    now: datetime | None = None,
) -> GapResult:
    now = now or datetime.now(timezone.utc)
    day = now.strftime("%Y-%m-%d")
    full_text = "\n".join(raw_fields.values())

    # 1. moderation first — never leak content, route to human queue, stop
    if scan_moderation(full_text):
        return GapResult("moderation_hold", ["content flagged for moderation review"])

    # 2. schema (includes the never-close invariant and the path guard)
    errors, operation, filename = check_gap_schema(raw_fields, existing_gaps)
    if errors:
        return GapResult("reject", errors)

    # 3. injection + secrets — identical screening to entry intake
    reasons = scan_injection(full_text) + scan_secrets(full_text)
    if reasons:
        return GapResult("reject", reasons)

    # 4. rate limit, anchored to the authenticated login (new accounts: tighter
    #    cap, but still auto-accepted — the sandbox, not a human, is the guard)
    new_acct = is_new_account(account, now)
    cap = DAILY_CAP_NEW_ACCOUNT if new_acct else DAILY_CAP
    if not limiter.check(account.login, day, cap):
        return GapResult("reject", [f"daily cap ({cap}) reached for this account"])

    # 5. build the exact text to write, now that it has cleared every scan
    if operation == "create":
        record_text = build_new_gap_file(raw_fields)
    else:
        record_text = _build_session_block(raw_fields)

    limiter.record(account.login, day)
    return GapResult(
        "accept",
        [],
        operation=operation,
        filename=filename,
        record_text=record_text,
        new_status=raw_fields.get("status", "").strip().lower(),
    )
