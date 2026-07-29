---
name: ingest-conversation
description: Ingest a conversation transcript into a context-mesh — distill it into typed chunks, propose a placement for each against the mesh's indexes, validate against the locked vocabulary, and write them to staging after a human checkpoint. Use when asked to ingest, distill, or route a transcript, meeting notes, or a design session into a mesh.
---

# Ingest a conversation into the mesh

Turn a transcript into a staged set of routed context. One run, straight through:

```
transcript → distilled typed chunks → proposed placements → checkpoint → validate → staging
```

The **in-run checkpoint is the human gate** (`approve` / `retry N` / `drop N`), shown before
anything is written and while the transcript is still in hand. On approval, chunks are written
**straight to `staging/candidates/` — no PR.** Nothing here writes canonical context;
promotion into it is a separate human act, and *that* is where the PR gate lives.

## Inputs

- **The transcript** — a path, or pasted text.
- **The Hub root** — the one repo where all context lives. Ask if not given.
- **Where the transcript came from** — **inferred from the input**, then confirmed (stage 1a).
  Not configured; it decides whether the raw material survives the run.

**If the Hub or a domain isn't set up** — no `context-index.md`, or no workflow so `Todo`s
can't route — that is the **`setup-mesh` skill's** job, not this one. Check with
`python3 "${CLAUDE_PLUGIN_ROOT}/skills/setup-mesh/scripts/check_setup.py" <dir>`. Ingestion assumes a mesh that is ready
to receive; it reports gaps, it does not fix them mid-run.

## The one rule that matters most

**Route using the indexes only.** Read the Hub root's and each domain's `context-index.md` and route against the
file descriptions and load conditions written there. **Do not open the context files to
decide where a chunk goes.**

This is not a performance shortcut, it is the design under test. The index is the
progressive-disclosure contract the whole project rests on; if a chunk cannot be routed from
the index alone, that is a **finding worth reporting**, not a licence to go read the target
files. Loading the whole mesh to route one chunk is the exact anti-pattern context-mesh
exists to kill.

If you catch yourself wanting to open a context file to decide a placement: stop, place it
with lower confidence, and say so at the checkpoint and in the commit summary.

### The one exception: dedup reads the target, *after* routing has chosen it

Once a chunk has a target, **read that target file** before writing — to check the claim
isn't already there (stage 3.5). This is bounded and it does not weaken the rule above:

| | Routing | Dedup |
|---|---|---|
| **When** | Before a target exists | After the target is fixed |
| **Reads** | Indexes only | The one file routing chose |
| **Asks** | What is this file *about*? | What does this file already *say*? |
| **Cost** | N domains → 1 index each | ≤ N chunks, and only existing files |

**The order is what makes it safe.** Reading after the decision cannot influence the
decision. Reading *before* — opening candidate files to work out where something fits —
is the whole-mesh load in slow motion, and it would also make this rule untestable, since
routing would always have the bodies to fall back on.

**Never widen the read.** Not "one more file to be sure," not a sibling, not a grep across
the mesh. If a placement's target is wrong, the fix is at the checkpoint, not a wider read.
`scripts/collect_dedup_targets.py` computes the permitted read set from the placements so
the bound is auditable rather than a matter of restraint.

## Stage 1 — Ingest, identify the source, sanitize

### 1a. Establish where it came from — *before* reading it for content

The `Conversation` node is the provenance root: **every fact this run produces hangs off it**
via `derives-from`. If it can't point at something a human can go and read, then six months
from now "where did this come from?" is answered by a node the agent wrote about a file that
no longer exists.

**Infer it from the input, then confirm — don't interrogate.** The input usually answers this
already:

| The input is… | Infer | Confirm by saying |
|---|---|---|
| A Granola export / note ID | `referenced`, `source_ref: granola:note/<id>` | "Taking this as Granola note `<id>` — nothing archived." |
| A Slack permalink / thread | `referenced`, `source_ref: slack:<permalink>` | "Referencing the Slack thread." |
| A file path | **`archived`** — a path is not a datastore | "This is a file path, so I'll archive a sanitized copy unless it's an export from something I should reference instead." |
| Pasted text | **`ephemeral`** | "No source to point at — provenance will be weak. Tell me if it's from somewhere I can reference." |

**There is no config file for this**, deliberately. A saved default would be a hint you'd have
to second-guess: an org can run Granola *and* Otter *and* Zoom, and the same person pastes ad
hoc text some days. The value varies per *transcript*, not per person — so it is read off the
actual input, every run. Getting it wrong is expensive (it decides whether the raw transcript
survives), so **infer, state the inference, and let the human correct it.**

| `source_kind` | When | What to record |
|---|---|---|
| `referenced` | The transcript lives in a system with its own retention — Granola, Slack, Zoom, a ticket | `source_ref`: the note ID / permalink / URL. **Store nothing else.** |
| `archived` | Hand-provided; **no datastore behind it** | `source_ref`: how it arrived. `source_archive`: where you archived it (1c). |
| `ephemeral` | Source is gone and wasn't archived | Say so. Weak provenance — flag it at the checkpoint. |

**Default to `referenced` only when you can name the datastore.** "It's in Granola somewhere"
is not a `source_ref`; a note ID is. If you cannot name where it lives, it is `archived` —
which means *this run is the only thing standing between that transcript and oblivion*.

**A file path is not a datastore.** A path someone passed you is not durable: it is one
`rm` from gone, and the skill doesn't own it. Ingesting from a path is `archived` unless
that path is a synced export from a real system you can name.

### 1b. Sanitize — before anything is written, in every case

- Strip PII: names of real people outside the participant list, emails, phone numbers,
  addresses, account numbers, customer identifiers.
- Redact secrets: keys, tokens, passwords, connection strings.
- Anonymize client names per the project convention (Client A / Client B) unless the mesh
  already names them.

**This is unconditional.** `source_kind` decides whether a *copy is kept*, never whether PII
is stripped. **No path through this skill writes raw PII to disk.**

**Read the mesh's `PII policy` from the Hub root `context-index.md`** (Identity section:
`strip` or `enrich`). Under `strip` — the default — redact speaker identity as above. Under
`enrich`, keep participant names and roles (the mesh has chosen to hold that data), but still
redact secrets and non-participant PII. `enrich` narrows *what* counts as PII here; it never
turns sanitization off.

**If the input is already structured** — by [the transcript structurer](../../prompts/structure-transcript.md)
or a Granola template — this pass is *lighter*, because a first sanitization already ran. It is
**never skipped.** The structurer may run entirely outside the mesh's control, so stage 1b stays
unconditional and authoritative: it is the last sanitizer, not the only one. Structured input is
still just a transcript — it flows through this same stage-1 path, no special case.

### 1c. Archive — only when nothing else will hold it

For `archived` only: write the **sanitized** transcript next to the `Conversation` node
(`staging/candidates/<conv-id>-transcript.md`) and record the path as `source_archive`.

The rule everywhere else is **no raw transcript stored** — a transcript is the highest-PII
artifact in the system, and the cheapest way not to leak it is not to hold it. That rule
assumed the raw material was disposable, which is true when a datastore keeps it and false
when someone pastes in the only copy. So: **archive the exception, never the default.**

Say plainly at the checkpoint and in the commit summary that an archive was written.
Retention period, access control, and deletion path are the client's call — this skill does
not invent them.

### 1d. Emit the `Conversation` node

The provenance root, per [vocabulary.md](../../docs/vocabulary.md) v1.1: `source_ref`,
`source_kind`, `content_hash` (idempotency — same hash re-ingested updates, not duplicates),
plus source, date, and role-anonymized participants.

Then **discard the raw transcript.** Only the distilled version — and, for `archived`, the
sanitized copy — survives the run.

## Stage 2 — Distill into typed chunks

Break the conversation into atomic chunks. For each, assign **one node type** from Group A of
the vocabulary:

| Type | It's this when… |
|---|---|
| `Knowledge` | A durable fact about the product, users, or system. |
| `Requirement` | A capability or constraint someone wants built. |
| `Todo` | An action item someone has to do. |
| `DomainFact` | A fact specific to one domain — its code, quirks, conventions. |
| `OpenQuestion` | A point raised and left undecided. Needs a human decision. |

**Chunk granularity — the default:** one chunk = **one durable claim**, with enough context
to stand alone once the conversation is gone. Err coarse. A chunk a reader can't understand
without the transcript is too fine, and the transcript won't be there. If a chunk would
produce two different placements, it's two chunks.

**Tag every chunk `decided` or `undecided`.** Decided = a durable fact, settled. Undecided =
speculation, a feature request, ideation, an open question. Both land in staging; the tag
controls where and how promotion later treats it. **Talking about a thing is not deciding
it** — if the transcript shows it being weighed, it's `undecided`, however confident the
speaker sounded.

Discard: pleasantries, thinking-aloud that got abandoned, restatements, anything with no
durable claim in it. **Most of a transcript is not context.** A run that keeps everything has
failed. Say how many chunks you dropped.

## Stage 3 — Propose placements

For each chunk, propose a complete placement. Read the mesh's indexes first (and only).

**Node** — the chunk rewritten as a context-file-shaped entry: a title, a body that stands
alone, frontmatter. Write it as context, not as a transcript excerpt. No "Mike said."

**Typed edges** — real targets, legal for the type. The legal-edge matrix:

| Source type | May originate |
|---|---|
| `Conversation` | `references` |
| `Knowledge` | `derives-from`, `applies-to`, `references`, `contradicts` |
| `Requirement` | `derives-from`, `triggers`, `creates`, `references`, `contradicts` |
| `Todo` | `derives-from`, `routed-to`, `references` |
| `DomainFact` | `derives-from`, `applies-to`, `references`, `contradicts` |
| `OpenQuestion` | `derives-from`, `references` |

Every Group-A node **must** carry `derives-from` back to the `Conversation`. Provenance is
mandatory — no exceptions, and the validator enforces it.

IDs are domain-prefixed and 4-digit: `payments:OPP-0042`. Only reference IDs that the
index actually lists. **Never invent one.**

**Target path** — the exact file the human would approve into. The chunk is written to
`staging/candidates/`, *tagged for* that eventual canonical path. Pick the **domain** by what
the fact is about (is this about one domain, or about everybody? — the latter goes to the Hub
root) and the file by the index's load conditions.

**A `Todo` routes to a workflow, not a file.** The index lists the domain's workflows
(`process/workflows/`) — usually **pointers to the system that really runs the process**
(Jira, Linear). Route the `Todo` there with `routed-to`; its `target_path` is its own staging
candidate, because a `Todo` has no canonical file to land in — the real destination is the
tracker.

Routing a `Todo` means **identified and attributed, not filed.** Filing is a human act in the
external system. Never write a list of todos into the mesh: that makes it a shadow issue
tracker with a second source of truth, rotting from the day it is written.

**No good home is a legal answer.** If the index shows no file this belongs in, say so:
`target_path: null`, with a note on what file would need to exist. A mesh with a gap is
normal. Forcing a chunk into the nearest surviving file is how a taxonomy rots — and the gap
is a finding the client needs. (If a `Todo` has nowhere to go, the index declares **no
workflow** — that is the gap to report.)

**Confidence + rationale** — high / medium / low, plus one line of why, so the human can skim
the confident ones and scrutinize the rest. Low confidence is useful; false confidence is
not.

**Contradictions** — if a chunk conflicts with something the index says exists, add a
`contradicts` edge and flag it. Never silently overwrite. A contradiction is for a human.

### The JSON the validator eats

Write the proposals to a JSON file:

```json
{
  "chunks": [
    {
      "id": "conv-0001",
      "type": "Conversation",
      "target_path": "staging/candidates/conv-0001.md",
      "source": "design session, 2026-07-16",
      "source_kind": "referenced",
      "source_ref": "granola:note/abc123",
      "content_hash": "sha256:…",
      "edges": []
    },
    {
      "id": "k-0001",
      "type": "Knowledge",
      "tag": "decided",
      "title": "Soft declines are retried once before the customer sees anything",
      "body": "…stands alone without the transcript…",
      "target_path": "payments/technical/system-behavior.md",
      "confidence": "high",
      "rationale": "Domain-specific runtime behavior; the index points system-behavior.md at exactly this.",
      "edges": [
        {"edge": "derives-from", "target": "conv-0001"},
        {"edge": "applies-to", "target": "payments"}
      ]
    }
  ],
  "dropped_count": 14
}
```

**Field notes:**

- `target_path` — **Hub-relative** (`payments/technical/x.md` for a domain file,
  `technical/x.md` for a cross-cutting one). Use
  `null`, plus a `rationale`, when the mesh has no home for the chunk.
- `dropped_count` — how many chunks distillation discarded as non-durable. Reported at the
  checkpoint, because "9 placed" means something different if 4 were dropped than if 40 were.
- `duplicate_of` — set by **dedup only** (stage 3.5) to the path already carrying the claim.
  A chunk with this set is not written; it is reported as dropped.

## Stage 3.5 — Dedup against the target file

Routing is done and every chunk has a target. Now read those targets — and only those.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/ingest-conversation/scripts/collect_dedup_targets.py" <placements.json> <mesh-root> --explain
```

That prints the **permitted read set**: the existing files routing chose. Read each one and
compare it against the chunks routed there. Nothing outside that list. If it exits non-zero,
a target didn't resolve — **fix that before writing anything**, because an unresolved target
looks exactly like "no duplicates found," and every duplicate would ship silently.

Three outcomes per chunk:

| The target file… | Do this |
|---|---|
| **doesn't contain the claim** | Write the candidate as normal. |
| **already makes the same claim** | **Drop the chunk.** Set `duplicate_of: <path>`. Don't write a candidate — report it at the checkpoint and in the commit summary. |
| **makes a *different* claim about the same thing** | **A contradiction, not a duplicate.** Keep the chunk, add a `contradicts` edge, flag it. |

**Same claim vs. different claim is a judgement — make it conservatively.** Reworded but
identical → duplicate. Different substance → contradiction. Genuinely unsure → keep it and
flag it. A false duplicate silently deletes a real fact; a false contradiction costs a human
thirty seconds. Those errors are not equal, so do not treat them as such.

**Never edit the target file.** Dedup reads. Writing to canonical context is promotion, and
that is a separate human act.

## Stage 4a — The checkpoint (approve before the PR)

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/ingest-conversation/scripts/render_checkpoint.py" <placements.json>
```

Show the human every proposed placement, **ordered least-confident first**, and stop.

**Show all of them, always.** Confidence sets the *order*, never what's visible — a
placement marked high-confidence and wrong is precisely the failure that matters, and a
filter would hide exactly that. Ordering gives full visibility while making the risky ones
impossible to miss.

They can:

- **approve** → validate, then write to staging (Stage 5)
- **retry N [reason]** → re-propose chunk N with their correction
- **drop N** → discard chunk N

**This checkpoint is the human gate — there is no later PR into staging.** It has to be here,
because right now the transcript is still in context and re-proposing is nearly free. After
the run it is **gone** — sanitized at ingest, never persisted — and a wrong placement could
only be hand-edited, without the source that produced it. So both jobs a reviewer needs,
*approve* and *repair*, happen here, while the source is still in hand. Staging is written
directly on approval; the next gate is promotion into canonical context.

Loop until they approve. Re-run the validator after any change.

## Stage 4b — Validate (before the PR, always)

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/ingest-conversation/scripts/validate_placements.py" <placements.json>
```

Exit 0 = legal. Exit 1 = violations, printed by rule.

**Fix violations by fixing the proposal, never by loosening the check.** The validator
encodes the locked vocabulary; if it says an edge is illegal, the edge is illegal. If you
genuinely believe the vocabulary is wrong, that is a finding for the commit summary — it is
not a thing to route around, and `docs/vocabulary.md` is the authority either way.

Do not write to staging if validation fails.

## Stage 5 — Write to staging

The checkpoint (4a) was the human gate. Once it's approved, **write directly to staging** —
no branch, no PR.

1. Write each chunk to its `staging/candidates/<id>.md` — at the Hub root for cross-cutting
   context, in the owning domain folder for domain context. Use the template in `templates/candidate.md`.
2. Commit. One commit for the run is fine.

**Why no PR here.** A PR does two jobs — coordinate concurrent edits, and provide a review
surface — and neither applies to a staging write. Each run is one person writing *new* files
with unique IDs, so two concurrent ingests never collide; there is nothing to merge. And the
review already happened at the checkpoint, over the same placements, while the transcript was
still in hand. A staging PR would be a second showing of a decision already made, gating a
holding pen nobody's tools read from. The PR belongs at **promotion** (the `promote-candidate`
skill), where *existing* canonical documents get edited, concurrent promotions can target the
same file, and the stakes are org-wide. Staging is cheap and private by design; the undo for a
bad candidate is deleting the file, not closing a PR.

### The commit carries the review surface

Generate the placement table and use it as the commit body, so the run is auditable after the
fact:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/ingest-conversation/scripts/render_checkpoint.py" <placements.json> --summary
```

This renders the placement table as markdown for the commit message body. The diff shows
*what*; the summary shows *why*. Record:

- **How many chunks you dropped in distillation**, and roughly what they were.
- **What changed at the checkpoint** — anything retried or dropped, and why. A reader should
  not have to guess whether a low-confidence placement was seen and accepted or simply missed.
- **Whether the index was sufficient to route** — the dogfooding finding. If you wanted to
  open a context file *to decide a placement*, say so and say which. (Reading a target file
  at dedup is expected and is not this.) The most valuable line in the summary.
- **What dedup found** — duplicates dropped, contradictions raised.

The facts now sit in staging, waiting for a separate, human-initiated promotion.

## What this skill does not do

- **Promote** anything to canonical. Separate human act, by design.
- **Edit target files.** Dedup reads them; only promotion writes them.
- **Dedup against staging.** It checks the *target file*, not other candidates. Two
  conversations covering the same ground produce two candidates, and the human sees both at
  the gate. Re-ingesting the *same* conversation is handled by the content hash.
- **Scaffold** a mesh. Assumes one exists.
- **Open a PR.** It writes to staging directly after the checkpoint; the PR gate lives at
  promotion into canonical context, not here.

## Pipeline at a glance

```
1  ingest & sanitize      raw transcript in, never persisted
2  distill                typed chunks, decided/undecided, most of the transcript discarded
3  propose placements     INDEXES ONLY -- target + legal edges + confidence
3.5 dedup                 read ONLY the targets routing chose; drop dupes, flag conflicts
4a checkpoint             show everything, least-confident first; approve / retry / drop  (THE human gate)
4b validate               legal-edge matrix; must pass
5  write to staging       approved chunks -> staging/candidates/ -> commit  (no PR; PR is at promotion)
```
