---
name: promote-candidate
description: Promote approved staging candidates into canonical context — merge facts into their target files (batched per file), flag contradictions for a human, and resolve open questions. Use when asked to promote, land, or accept staged context, or to clear the Hub's staging/candidates.
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
| **MERGE** | The claim lands in a section of the target file. |
| **APPEND** | The target is a **collection** (a trailing-slash folder). Create a **new member file** in it; nothing existing is edited. |
| **CONTRADICTS** | The target says the opposite. **A human decides which moves — the doc, or the world.** Never auto-apply. |
| **RESOLVE** | An `OpenQuestion` doesn't promote — it *resolves* into another type first. |
| **NO-HOME** | `target: null`. Nothing to promote into until the manifest grows a file. |
| **NEVER** | A `Conversation` is a provenance root. It stays in staging permanently. |

**Count against the script, not this table.** This table has been wrong before, and so has the
script's docstring, in opposite directions. `classify()` is the only one of the three that
decides anything.

## Duplicates ingestion already linked

A candidate carrying `duplicate_of` was matched at ingestion against a claim that already
existed — in canonical context, or in an **unpromoted candidate from an earlier
conversation**. Dedup linked it and **deliberately did not resolve it**: ingestion only ever
adds, so nothing already in staging was rewritten or deleted.

The classifier groups these with their batch and marks them `DUPLICATE OF <id>`. What to do:

- **Merge the claim once.** The linked duplicate does not get merged again — that is the
  double-merge the link exists to prevent.
- **Mark the duplicate `state: canonical` anyway.** It stays as the audit trail of the second
  conversation that produced the claim: the fact was independently corroborated, and the
  provenance of both is worth keeping.
- **If the two are not actually the same claim, say so and merge both.** Dedup was
  instructed to be conservative, but a false link is possible and this is where it gets
  caught. A human overriding it here is the design working, not a failure.

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

0. **If the target file does not exist, create it** — see below. A listed-but-missing file is
   a **pending home**, not an error: the index row is a human's declaration of *where this
   kind of context goes*, made before anyone wrote it. Promotion is what fills it.
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

### Creating a pending home

**A row in the index whose file does not exist is a declaration, not a defect.** The index
says where a kind of context belongs; it does not claim the home is occupied. Setup
deliberately never creates context files — an empty file it wrote would read as *answered*
when nothing has been answered. Promotion is different: it has **content in hand**, so the
file it creates says something the moment it exists.

**The guard, and it is the important part:**

> **Create the file only if the index row already existed before this run.** Never create a
> file *and* the row that justifies it in the same motion.

Creating the file satisfies a human's declaration. Creating both would be the tool inventing
its own target — and it would make a typo self-certifying: a row reading
`technical/sytem-behavior.md` would get a file created at the misspelling, and the index then
updated to confirm it exists. Nothing would ever report the error. **If the target has no
index row, that is `NO-HOME`** and the fix is upstream, unchanged.

**Follow the conventions already in the repo — do not invent a house style.** In order:

1. **Sibling files in the same directory** are the strongest signal. A new
   `technical/system-behavior.md` should look like the `technical/repo-overview.md` beside
   it: same frontmatter keys, same heading depth, same presence or absence of an H1.
2. **The index row's *About* text** gives the title and framing — it is what a human already
   said this file is for.
3. **If there are no siblings, say so** and use the plainest possible shape: an H1 from the
   *About* text, and the content. Do not import a convention from another domain, and do not
   invent frontmatter no neighbouring file has.

**State what you inferred**, at the PR, so a human can correct it: which sibling you patterned
it on, or that there was none.

### Updating the index

A file that now exists is a different state from one that was only declared, and **the index
is the routing input** — leaving it stale means the next run re-derives the same "missing"
finding forever.

**The row change goes in the same PR as the content, and is called out in the summary.**
Not a silent rewrite: a tool editing the routing input without comment is exactly how a
manifest drifts away from what the team thinks it says. The PR summary says plainly:

> Created `technical/system-behavior.md` (pending home, declared in the index but never
> written), patterned on `technical/repo-overview.md`. Marked present in `context-index.md`.

If the index row already reads as present and correct, there is nothing to update — say that
rather than touching the file.

## APPEND — a new member in a collection

The target ends in `/`, so it is a **collection**: a folder of same-typed files where nothing
traverses a member (ADRs are the usual case). This does not edit an existing document — it
**creates a new file**.

For each batch:

1. **Read the collection's row in the index.** It carries the `Members` pattern — one of
   `{slug}.md`, `{date}-{slug}.md`, or `NNN-{slug}.md`. **The pattern is the naming rule and
   nothing else**: never read meaning back out of an existing member's filename.
2. **Generate the member's name** from that pattern:
   - `{slug}` — kebab-case, from the claim's subject. Keep it short and specific.
   - `{date}` — today, `YYYY-MM-DD`.
   - `NNN` — **read the directory and take the next unused number**, zero-padded to match its
     siblings. If the folder is empty, start at `001`.
3. **Draft the member.** Pattern it on sibling members in the same folder — same frontmatter
   keys, same heading shape. If there are none, use the plainest shape that fits the
   collection's *About* text, and **say that you had no sibling to follow**.
4. **Show the human the whole new file**, plus its generated name.
5. On approval: write it, mark the candidate `state: canonical`, open one PR for the batch.

**The guard is the same as a pending home:** the collection's **row must already exist**.
Promotion never creates a collection and the row justifying it in one motion — that would let
the tool invent its own destination. **No row, no collection: that is `NO-HOME`.**

**The index is not edited.** One row already covers the folder, which is the point of a
collection — adding a member changes nothing about what the index says. (Contrast a pending
home, where the row's *file* first comes into existence and the row must be updated.)

> **Run promotion single-threaded.** `NNN-{slug}.md` numbers by reading the directory, so two
> promotions running at once can both take `004`. This is not enforced anywhere — it is a
> requirement of using this plugin. `{date}-{slug}.md` and `{slug}.md` cannot collide this way.

## CONTRADICTS — stop

The target file and the candidate disagree about the same thing. Ingestion found this at
stage 3.5 and flagged it precisely so a human would see it.

**Do not merge. Do not edit the target. Do not pick a side.** Present:

- what the target currently says, quoted, with its location,
- what the candidate says,
- and the actual question: **is the doc wrong, or is the world wrong?**

Those have completely different consequences. A doc that's wrong gets edited. A *world*
that's wrong — code doing something the doc says it shouldn't — is a bug, and the fix is a
a fix in the team's tracker, not a doc edit. Run 1's `rf-0003` is exactly this:
`system-behavior.md` says
`payment.failed` publishes on decline; the conversation established the service publishes too
early. The doc describes the intent, the code has a bug. **Merging the candidate would have
quietly rewritten the intent to match the bug.**

Only after a human decides does anything move.

## RESOLVE — an OpenQuestion isn't ready

It has no promotion path. It isn't undecided about *where* it goes; it's undecided **full
stop** — there is no fact yet. Run the guided-resolution flow:

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
