# Staged for Collective — the gap-write path

These files implement the **lighter gap-write path** designed in
[`../gaps/GAP_WRITE_PATH.md`](../gaps/GAP_WRITE_PATH.md). They are built and tested here in
`Testing-new-brain` but are meant to live in the **Collective** repo — this repo has no write
access to Collective, so landing them is a separate PR to that repo (mirrors how Collective
itself was staged in a scratchpad before being dropped in).

**Nothing here is live.** It's verified, droppable content.

## What's proven

`gap_steward.py` is pure standard library and reuses `intake_steward.py`'s scans, rate limiter,
and account model verbatim — a gap submission gets the exact same injection/secret/moderation
screening an entry does. The suite passes:

```
# with intake_steward.py on the path (its home is Collective's root)
python3 -m unittest test_gap_steward.py -v
# Ran 24 tests, OK
```

Also dry-run end-to-end through `cli_gap.py` against a rendered issue-form body: a valid append
`accept`ed and committed to rate-limit state; a submission with a `../intake_steward.py` target
and a `SYSTEM: ignore all previous instructions` payload `reject`ed with no state written.

Not exercisable without a live Action (same gaps as Collective's own workflows): the `gh`/App-
token steps, the auto-merge, and `gap-diff-shape-check.yml`'s `on: pull_request` trigger.

## Where each file lands in Collective

| Staged path | Lands at (Collective root) |
|---|---|
| `gap_steward.py` | `gap_steward.py` |
| `cli_gap.py` | `cli_gap.py` |
| `test_gap_steward.py` | `test_gap_steward.py` |
| `.github/workflows/gap-intake.yml` | `.github/workflows/gap-intake.yml` |
| `.github/workflows/gap-diff-shape-check.yml` | `.github/workflows/gap-diff-shape-check.yml` |
| `.github/ISSUE_TEMPLATE/gap-log.yml` | `.github/ISSUE_TEMPLATE/gap-log.yml` |

Plus: move the `gaps/` folder (from this repo) to Collective's root, and add
`gaps/_state/ratelimit.json` (start it as `{}`).

## Repo config the auto-merge needs (Collective-side)

The "lighter" gate is auto-merge — but only *after* the independent `gap-diff-shape-check`
passes. For that to hold, Collective must:

1. **Register the `intake:gap` label** (and `gap:auto`, `flagged:moderation` if not present).
2. **Enable auto-merge** on the repo (Settings → General → Allow auto-merge).
3. **Protect `main`** with a required status check = `collective-gap-diff-shape` for `gap/*`
   PRs, so `gh pr merge --auto` cannot land a PR until that check is green. Without this, the
   independent check is advisory and the sandbox loses its second enforcement point.
4. Confirm the `COLLECTIVE_BOT` App can write to Collective (already true for entry intake).

## Security model (why auto-merge is acceptable here)

Four invariants, enforced in two independent places (the steward, and the diff-shape check):

- **Path-scoped** — writes only under `gaps/`; a bare lowercase-slug `.md`. The steward derives
  the name (create) or regex-validates it (append); the workflow re-asserts; the diff check
  rejects any file outside `gaps/`. Uppercase reserved files (`README.md`, `TEMPLATE.md`,
  `GAP_WRITE_PATH.md`) can't be targets — they fail the lowercase slug regex.
- **Append-only** — the diff check allows at most one deleted line (the single `Status` header
  an append may advance); prior session blocks can't be rewritten.
- **Never closes** — steward rejects `closed`/`closed:pending-review`; the diff check re-rejects
  any committed `closed` status. Closure stays with the entry pipeline or a human.
- **Screened + rate-limited** — same injection/secret/moderation scans and per-account caps as
  entry intake, re-run against the committed file by the second actor.

## After it lands

`TRAINING_MODE.md` Gate 7 changes from "append to the local `gaps/` folder" to "open an
`intake:gap` issue to append to Collective's gaps folder" — same user-confirmation and
no-direct-write discipline as entry submission.
