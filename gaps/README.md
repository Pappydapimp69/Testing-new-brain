# Gaps folder

Persistent, append-only records of knowledge gaps surfaced during **training mode** (see
[`../TRAINING_MODE.md`](../TRAINING_MODE.md)). One file per gap. Sessions append what they
learn to a gap's record; a session never rewrites or deletes another session's log.

This folder is the memory between training sessions. It's what lets:
- **Gate 2** re-find a gap that a prior session opened but didn't close.
- **Playmate mode** offer "a gap already accumulating from prior sessions" as a pick.
- **Gate 7** enforce that a single session can't close a gap — closure needs *independent*
  sessions converging here, or a human confirming during Collective's mediated review.

## Lifecycle

A gap moves through states; only the log grows, never shrinks:

| Status | Meaning |
|---|---|
| `open` | Surfaced, no session has worked it yet |
| `accumulating` | One or more sessions have appended findings; no stable answer yet |
| `converging` | Independent sessions are landing on the same answer, not yet confirmed |
| `closed:pending-review` | A candidate entry was proposed to Collective; awaiting steward + human |
| `closed` | Confirmed — either merged into Collective, or a human marked it resolved |

`reaction`/subjective gaps may sit at `accumulating` indefinitely. That is a valid resting
state, not a stalled one — consensus on subjective terrain may never fully form.

## Record format

Copy [`TEMPLATE.md`](TEMPLATE.md) to `gaps/<domain>--<slug>.md` and fill the header once; every
session that works the gap appends one block under **Sessions**. The **Type** field is the
Gate 3 classification (`fact-lookup` / `fit` / `reaction`) and decides whether an artifact is
mandatory. **Provenance** on a mined nugget is `Assumed` for a lone opinion round, `Verified`
only when externally grounded with real citations.

Nothing here is a published Collective entry. These are working records; publishing still goes
through the issue → steward → PR → human pipeline described in `TRAINING_MODE.md`.
