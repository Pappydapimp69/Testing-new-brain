# Gap write path — design (staged for Collective)

**Decision:** the gaps folder lives in **Collective** (shared, so gaps accumulate across users
and sessions — the only way Gate 7's cross-session convergence can work). A training session
writes to it through a **separate, lighter path** than the entry-intake pipeline.

**Status:** design staged here in `Testing-new-brain`. It is NOT live. Landing it means adding
the pieces below to the **Collective** repo (a PR to that repo — outside this repo's write
scope), plus configuring one label and one App-permission scope. Until then, `gaps/` in this
repo is the working copy.

## Lighter means lighter gating, not lighter credentials

The non-negotiable parts of Collective's model stay exactly as they are for entries:

- A session **never holds a git credential**. It only opens a GitHub issue. The commit is done
  by the workflow's bot token.
- That token is still an **App token, minted fresh per run, short-lived, scoped to Collective
  only** — the same `actions/create-github-app-token` mechanism `intake.yml` uses.
- **Injection and secret scans still run.** A gap record is attacker-controllable text like any
  submission; it gets the same screening the entry steward applies.

What the lighter path drops is only the **human-merge gate** — gap appends land automatically,
because a working note that updates every session can't wait on a person merging a PR each time.

## Mechanism

1. Session opens an issue labeled **`intake:gap`** (new 5th label), body = either a new gap
   record (header fields per `TEMPLATE.md`) or a single session block to append to an existing
   gap, identified by its filename/slug.
2. **`gap-intake.yml`** fires on `issues:[opened]`, gated to the `intake:gap` label — a
   sibling of `intake.yml`, not a modification of it.
3. **`gap_steward.py`** (steward-lite) validates and then commits directly to `gaps/` — no PR,
   no human merge. It reuses the entry steward's injection/secret/rate-limit checks and adds
   the gap-specific rules below.

## Security boundary — what makes a second, auto-merging write surface safe

A path that auto-commits without human review is only acceptable if it physically cannot touch
anything but gap scratch. All four must hold, or the path doesn't land:

1. **Path-scoped.** The workflow's token and `gap_steward.py` may write **only under `gaps/`**.
   Any diff touching `memory/`, `ideas/`, `tension/`, `creativity/`, `snapshot/`, `allowlist/`,
   `*.py`, or `.github/` is rejected outright. Canon is unreachable from this path.
2. **Append-only.** For an existing gap, the steward may only ADD a session block (and advance
   the header `Status`). It may never edit or delete a prior session block, or another gap
   file. History extends, never rewrites — which is what makes auto-merge non-destructive.
3. **Scans retained.** Injection and secret screening run on every gap submission, same as
   entries. A gap that trips them is rejected and commented, never committed.
4. **Rate-limited to the user's account**, same anchor as entry intake — a runaway session
   can't flood the folder.

Closure stays gated the hard way: `gap_steward.py` may set `Status` up to `converging`, but
**never to `closed`**. Only the entry-intake pipeline (a mined entry merged by a human) or a
human editing the gap directly can mark a gap closed. The lighter path can accumulate evidence;
it cannot declare a gap resolved.

## To land it (Collective-side, needs a PR to that repo)

- Add `gaps/` (with `README.md`, `TEMPLATE.md`, records) to Collective.
- Add `.github/workflows/gap-intake.yml` and `gap_steward.py` (+ tests, matching the existing
  steward's rigor).
- Register the `intake:gap` label.
- Confirm the App installation can write, but rely on the path-scope check as the real guard.

Once live, `TRAINING_MODE.md` Gate 7 changes from "append to the local `gaps/` folder" to "open
an `intake:gap` issue to append to Collective's gaps folder" — same user-confirmation and
no-direct-write discipline as entry submission.
