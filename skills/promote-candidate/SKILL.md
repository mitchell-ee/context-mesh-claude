---
name: promote-candidate
description: Promote approved staging candidates into canonical context — merge facts into their target files (batched per file), hand to-dos over to the tracker, and resolve open questions. Use when asked to promote, land, or accept staged context, or to clear the Hub's staging/candidates.
---

# Promote a candidate out of staging

The back half of the lifecycle. Ingestion ends at "approved and sitting in staging"; this is
the **separate, human-initiated act** that moves a fact into the context everyone reads.

**This is the first thing that writes canonical context.** Ingestion only ever wrote to
staging, so every mistake so far has been cheap — a bad candidate is one file nobody loads.
A bad promotion edits the file every agent in the org reads. Treat it accordingly: read-only
until a human approves, and never resolve a contradiction on your own.

## Promotion is not one verb

Six outcomes. `scripts/classify_candidates.py <hub-root>` decides which:

| Verdict | Means |
|---|---|
| **MERGE** | The claim lands in a section of the target file. The only one that resembles "moving" it. |
| **CONTRADICTS** | The target says the opposite. **A human decides which moves — the doc, or the world.** Never auto-apply. |
| **HANDOVER** | Target is a `Workflow` → the item belongs in Jira/Linear. Hand it over; **the mesh does not file.** |
| **RESOLVE** | An `OpenQuestion` doesn't promote — it *resolves* into another type first. |
| **NO-HOME** | `target: null`. Nothing to promote into until the manifest grows a file. |
| **NEVER** | A `Conversation` is a provenance root. It stays in staging permanently. |

## Batching — by target file, always

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/promote-candidate/scripts/classify_candidates.py" <hub-root>          # one staging dir
python3 "${CLAUDE_PLUGIN_ROOT}/skills/promote-candidate/scripts/classify_candidates.py" <hub-root> --mesh   # root + every domain's staging
```

Candidates landing in **one document are one edit**, reviewed whole.

**The Hub has one `staging/candidates/` per domain, plus one at the root** — ingestion writes
each candidate into the domain that owns the fact, and cross-cutting facts to the root.
`--mesh` walks them all. A batch spanning several domains is still **one PR**: everything
lives in one repo.

**The batch key is the bare `target`, which is now unambiguous.** It used to have to be
`(repo, target)`, because a `target` was *repo-relative* and `technical/system-behavior.md`
existed in most repos — keying on the path alone silently merged one service's facts into
another's document. That was a real bug (**cross-repo fact corruption, under a confident
review**), and the single-Hub collapse makes it impossible by construction: targets are
Hub-relative and unique.

**Why this matters more than it looks:** run 1 put three candidates into
`technical/system-behavior.md`. Promoting them one at a time means three sequential PRs
against the same file, each conflicting with the last, and a human reading the same document
three times. Worse — one of those three was a `contradicts`. **A contradiction in a batch can
change what the other candidates in that batch should say**, so it is resolved *first*, not
merged around. The classifier flags this.

## MERGE — the main path

For each batch:

1. **Read the target file.** Where does each claim belong — which section, and does it
   extend, qualify, or replace what's there?
2. **Draft the merged result.** Write it as if it had always been there: the target is
   canonical context, not a changelog. **No "as of 2026-07-16" and no "the team decided" —
   state the fact.** A reader six months out wants the fact, not its minutes.
3. **Preserve provenance.** The canonical file doesn't carry `derives-from` frontmatter, but
   the trail must survive: the candidate stays in staging marked `state: canonical` with its
   `derives-from` intact. **The candidate is the audit trail; the context file is the answer.**
4. **Show the human the merged file**, not just the diff hunks — the point of batching is
   seeing the document whole.
5. On approval: write, mark each candidate `state: canonical`, open one PR for the batch.

**Never silently drop a claim.** If two candidates in a batch conflict *with each other*,
that is the same problem as a `contradicts` — surface it, don't pick.

## CONTRADICTS — stop

The target file and the candidate disagree about the same thing. Ingestion found this at
stage 3.5 and flagged it precisely so a human would see it.

**Do not merge. Do not edit the target. Do not pick a side.** Present:

- what the target currently says, quoted, with its location,
- what the candidate says,
- and the actual question: **is the doc wrong, or is the world wrong?**

Those have completely different consequences. A doc that's wrong gets edited. A *world*
that's wrong — code doing something the doc says it shouldn't — is a bug, and the fix is a
`Todo`, not a doc edit. Run 1's `rf-0003` is exactly this: `system-behavior.md` says
`payment.failed` publishes on decline; the conversation established the service publishes too
early. The doc describes the intent, the code has a bug. **Merging the candidate would have
quietly rewritten the intent to match the bug.**

Only after a human decides does anything move.

## HANDOVER — the mesh doesn't file

The target is a `Workflow`, which is a **pointer to the system that really runs the process**
(Jira, Linear). There is no file to merge into.

Produce a ready-to-file item and **hand it over**:

- **Title and body** — what to file.
- **Destination** — from the workflow's `system` + `external_ref`. e.g. Jira project `PAY`.
- **Provenance** — the conversation it came from, and the `references` edges (an OST ID makes
  it traceable work, not a loose chore).

Then **stop**. Filing is an outward-facing write to a system the mesh doesn't own and can't
undo — wrong `source_kind` costs a stale pointer; a wrongly-filed ticket is in someone's
sprint. A human files it.

**The candidate is kept**, marked `state: resolved`, with `resolved_to: <ticket ref>` once the
human says it's filed. Not deleted: it carries the `derives-from` chain back to the
conversation — what was said, who raised it, which meeting. **Jira cannot hold that**, and
that provenance is what this project exists to preserve. The ticket is the work; the candidate
is the record of where the work came from.

## RESOLVE — an OpenQuestion isn't ready

It has no promotion path. It isn't undecided about *where* it goes; it's undecided **full
stop** — there is no fact yet. Run the guided-resolution flow
([ingestion-pipeline.md](../../docs/ingestion-pipeline.md)):

1. Surface the question with the context that raised it (`derives-from` the `Conversation`).
2. Offer the options you can infer, and **what each would route to if chosen**.
3. On a decision, convert it to a decided node with its now-legal edges.

Only then is there something to promote.

## NO-HOME and NEVER

**NO-HOME** — `target: null`. The mesh has no file for this. **Do not force it somewhere
close.** The fix is upstream: a human adds the file to an index (a manifest decision), then
the chunk is re-routed. Run 1's `k-0001` — a cross-cutting 402 quirk with no
`integration-map.md` to land in — is the live example. The gap is the finding.

**NEVER** — a `Conversation` stays in staging. It's the provenance root every fact hangs off.

## The gate

Same shape as ingestion: **a PR per batch**, and this skill never merges its own. Show the
merged file, get approval, open the PR, stop.

## What this skill does not do

- **Resolve contradictions.** Ever. It surfaces them.
- **File tickets.** It hands over; a human files.
- **Delete candidates.** They're the audit trail — marked, kept.
  (There used to be a second thing called "promotion" — leaf→Hub snapshots, marked by a
  `promoted-from` edge. It no longer exists; "promotion" now means only staging → canonical.
  See [vocabulary.md](../../docs/vocabulary.md) v2.0.)
