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

**If the Hub or a domain isn't set up** — no `context-index.md`, or an index that lists
nothing, so a fact has nowhere to land — that is the **`setup-mesh` skill's** job, not this
one. Check with
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

| | Routing | Member resolution | Dedup |
|---|---|---|---|
| **When** | Before a target exists | After the folder is fixed | After the target is fixed |
| **Reads** | Indexes only | Members of the collection routing chose (frontmatter first) | The file routing chose, **plus unpromoted staging** |
| **Asks** | What is this file *about*? | *Which* member is this about? | What does the mesh already *say*? |
| **Cost** | N domains → 1 index each | folder-bounded, warns at 40 | ≤ N chunks (canonical) + the staged pool |

**Member resolution (stage 3.4) only runs when routing chose a collection** — a target ending
in `/`. Routing picks the *folder* from the index; it cannot pick the member, because a
collection is one index row describing the folder, not one row per file. Reading the members
afterwards cannot change which folder was chosen, so the rule above holds for exactly the same
reason dedup does: **the order is what makes it safe.**

**Its cost is the one read here that is not chunk-bounded.** A chunk routed to a 40-member
collection expands to 40 reads — folder-bounded, growing with the folder rather than the
transcript. Frontmatter is read first and bodies only on demand, which is what keeps it small.
Scoping the read by guessing at filenames was **rejected** for the reason the staged pool gives
below, and because the taxonomy makes a member's naming pattern *opaque*: it generates a name,
it never parses meaning out of an existing one.

**The staged pool is bounded differently, and deliberately so.** Candidates run ~2 KB and a
human actively drains the pool, so even a neglected 100 is ~200 KB — a fixed-size pool, not
the mesh. Scoping it to same-target candidates was considered and **rejected**: it would
silently miss the case that most needs catching, where two conversations describe the same
fact and get routed to *different* files. A scoped read fails silently; a pool-size warning
fails loudly.

**The order is what makes it safe.** Reading after the decision cannot influence the
decision. Reading *before* — opening candidate files to work out where something fits —
is the whole-mesh load in slow motion, and it would also make this rule untestable, since
routing would always have the bodies to fall back on.

**Never widen the read.** Not "one more file to be sure," not a sibling, not a grep across
the mesh. If a placement's target is wrong, the fix is at the checkpoint, not a wider read.
`scripts/collect_dedup_targets.py` computes the permitted read set from the placements so
the bound is auditable rather than a matter of restraint.

## Stage 1 — Ingest and identify the source

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
| A file path | **`archived`** — a path is not a datastore | "This is a file path, so I'll archive a copy unless it's an export from something I should reference instead." |
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

### 1b. The transcript is not modified

**Ingestion does nothing to the transcript before extracting from it.** No redaction, no
anonymization, no substitution of speaker names. What arrives is what gets read, and — for
`archived` — what gets written.

This was a `strip | enrich` PII policy through v2.3, and stage 1b redacted unconditionally.
It is gone. Transcripts come from meetings whose participants are internal or have consented
to recording, and **normalizing a transcript before extraction is a transcript-quality
concern, not a privacy posture** — the useful version of it resolves a speaker to the right
person rather than replacing them with a label. That work is expected to arrive as a
**pre-pass** (see the structurer, which occupies the same slot), not as a redaction stage
buried in ingestion.

**Retention is the team's lever, not this skill's.** A mesh that does not want transcripts in
its history can `.gitignore` them; that is a decision about the repo, made by the people who
own it, and it is more honest than a pipeline that quietly rewrites their content.

**If the input is already structured** — by the `structure-transcript` skill, by
[its underlying prompt](../../prompts/structure-transcript.md) run elsewhere, or by a Granola
template — it needs no special handling. Structured input is still just a transcript, and
flows through this same stage-1 path.

### 1c. Archive — only when nothing else will hold it

For `archived` only: write the transcript next to the `Conversation` node
(`staging/candidates/<conv-id>-transcript.md`) and record the path as `source_archive`.

The rule everywhere else is **no transcript stored** — not because the content is dangerous,
but because a copy the mesh does not need is a copy that drifts from the system that owns it.
That holds when a datastore keeps the original and fails when someone pastes in the only copy.
So: **archive the exception, never the default.**

Say plainly at the checkpoint and in the commit summary that an archive was written, and that
it is the transcript **as received**. Retention period, access control, and deletion path are
the team's call — this skill does not invent them, and a team that does not want transcripts
in its history can `.gitignore` the archive path.

### 1d. Emit the `Conversation` node

The provenance root, per [vocabulary.md](../../docs/vocabulary.md) v1.1: `source_ref`,
`source_kind`, `content_hash` (idempotency — same hash re-ingested updates, not duplicates),
plus source, date, and participants **as the transcript gives them**.

Then **discard the working copy of the transcript.** Only the distilled version — and, for
`archived`, the archived copy — survives the run.

## Stage 2 — Distill into typed chunks

Break the conversation into atomic chunks. For each, assign **one node type** from Group A of
the vocabulary:

| Type | It's this when… |
|---|---|
| `Knowledge` | A durable fact about the product, users, or system. |
| `Requirement` | A capability or constraint someone wants built. |
| `DomainFact` | A fact specific to one domain — its code, quirks, conventions. |
| `OpenQuestion` | A point raised and left undecided. Needs a human decision. |

**Action items are out of scope — do not type them.** "Chase the DPA", "book the workshop",
"file a ticket for X" are *the work*, not context about it. The mesh supports context; where
work gets queued is the team's tracker's job, and every team's is different.

**Report them, don't drop them silently.** List the action items the transcript contained in
the run summary, so the human can put them wherever they actually track work. Noticing one is
useful; filing it is not this system's job.

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
| `Requirement` | `derives-from`, `references`, `contradicts` |
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

**No good home is a legal answer.** If the index shows no file this belongs in, say so:
`target_path: null`, with a note on what file would need to exist. A mesh with a gap is
normal. Forcing a chunk into the nearest surviving file is how a taxonomy rots — and the gap
is a finding the client needs.

**Check the "Not in this mesh" section before reporting a gap.** A file named there is
*deliberately* absent, so `target_path: null` is the correct and final answer — not a
manifest gap someone should fix. A file that is missing but *not* named there may simply not
be written yet.

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
- `member_resolution` — set by **member resolution only** (stage 3.4), and only for a chunk
  routed to a collection: `resolved`, `created`, or `created-near-match`. With `resolved` the
  chunk's `target` is rewritten to the member's path; with either `created` value it stays the
  folder. `member_near_match` names the member that was considered and rejected.
- `duplicate_of` — set by **dedup only** (stage 3.5) to whatever already carries the claim:
  a Hub-relative **path** (canonical context says it) or a **candidate ID** (an unpromoted
  candidate from an earlier ingestion says it). A chunk with this set is not written; it is
  reported as dropped. `check_references.py` walks it, so a broken pointer is caught.

## Stage 3.4 — Member resolution (collections only)

**Runs only for chunks whose target ends in `/`.** Routing chose a *folder*; this decides
*which member* — modify an existing one, or create a new one. Skip this stage entirely if no
chunk routed to a collection.

The read set comes from the same script as dedup, which lists members under
**COLLECTION MEMBERS** with each member's `type` and key (`slug`/`id`) from its frontmatter.
Read frontmatter first; open a body only when the frontmatter cannot settle it.

Three outcomes, and the default is the important one:

| The collection… | Do this | `member_resolution` |
|---|---|---|
| **has a member this fact is clearly about** | Retarget the chunk at that member's path. It becomes an ordinary file target. | `resolved` |
| **has no member this fact is about** | Leave the target as the folder. Promotion creates a new member. | `created` |
| **has a member this *might* be about** | **Create.** Leave the target as the folder, and record what it nearly matched. | `created-near-match` |

**Ambiguity resolves to CREATE — never to merge.** A spurious new member is visible on disk
and named at the checkpoint; a wrong merge is buried inside a file nobody re-reads. Those
errors are not equal. Set `member_near_match` to the member you rejected so the human can
overturn it at the gate with `retry` — a near-match is flagged **NEAR-MATCH** and sorts to the
top of its group, because nothing downstream re-examines this judgement.

This is also why the default is safe: creating is *adding*, and **ingestion only ever adds.**
Silently merging a fact into an existing member would be the one place ingestion edited
something a human had already accepted.

**If a collection directory cannot be read, the run stops.** An unreadable folder yields zero
members, which is indistinguishable from an empty one — and would resolve every chunk to
CREATE, manufacturing duplicates of members that were already there.

## Stage 3.5 — Dedup against canonical context *and* unpromoted staging

Routing is done and every chunk has a target. A claim can already exist in **two** places,
and missing either one ships a duplicate:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/ingest-conversation/scripts/collect_dedup_targets.py" <placements.json> <mesh-root> --explain
```

That prints the **permitted read set**, in two labeled parts:

| Set | What it is | Asks |
|---|---|---|
| **CANONICAL** | The existing files routing chose. Bounded by chunk count. | Does decided context already say this? |
| **STAGED** | Unpromoted candidates from **earlier ingestions**. Bounded by the pool. | Did a previous conversation already produce this claim? |

Read both, and nothing outside them. If it exits non-zero, a target didn't resolve **or a
staging directory couldn't be read** — fix that before writing anything. Both failures look
exactly like "no duplicates found."

**Why the staged set exists:** a candidate that hasn't been promoted is by definition *not*
in canonical context, so the canonical read cannot see it. Without this, two conversations
three weeks apart could each produce the same claim, and both would sit in staging unlinked
until a human noticed at promotion time.

Three outcomes per chunk, against **either** set:

| The target file or staged candidate… | Do this |
|---|---|
| **doesn't contain the claim** | Write the candidate as normal. |
| **already makes the same claim** | **Drop the chunk.** Set `duplicate_of:` to the canonical `<path>` or the staged `<candidate-id>`. Don't write a candidate — report it at the checkpoint and in the commit summary. |
| **makes a *different* claim about the same thing** | **A contradiction, not a duplicate.** Keep the chunk, add a `contradicts` edge pointing at the path or candidate ID, flag it. |

**Same claim vs. different claim is a judgement — make it conservatively.** Reworded but
identical → duplicate. Different substance → contradiction. Genuinely unsure → keep it and
flag it. A false duplicate silently deletes a real fact; a false contradiction costs a human
thirty seconds. Those errors are not equal, so do not treat them as such.

**Never edit the target file, and never edit a staged candidate.** Dedup reads and *links*;
it does not resolve. Writing to canonical context is promotion. Rewriting a candidate an
earlier run wrote — and a human may already have reviewed — is not ingestion's to do:
**ingestion only ever adds.** The link is what lets promotion present a pre-collapsed batch.

**A large pool is a note, never a blocker.** Above the warning threshold the script says the
pool is worth draining and carries on. Surface it at the checkpoint; do not stop the run.

## Stage 4a — The checkpoint (approve before the PR)

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/ingest-conversation/scripts/render_checkpoint.py" <placements.json>
python3 "${CLAUDE_PLUGIN_ROOT}/skills/ingest-conversation/scripts/render_checkpoint.py" <placements.json> --full
```

**Two steps: show the shape, then ask how they want to read it.** Do not dump 26 chunk
bodies at someone who has not yet seen what the run produced.

**1. The overview** (the default invocation) gives them, before any detail:

- **how many chunks need approval, broken down by type** — and that `Conversation` nodes are
  provenance roots, so they are *not* reviewed. Say it, or the numbers look like a bug.
- **a table grouped by destination file** — chunk count, the group's lowest confidence, and
  the chunk IDs (consecutive runs collapse: `k-0001-0004`).
- **which chunks need their eye** — the low-confidence and flagged ones, by ID.

**Grouped by destination, because that is how a document gets reviewed.** Everything landing
in `technical/integration-map.md` is one judgment about one file, and it is how promotion
batches later too.

**Risk still leads, through the group order.** Groups sort by their *riskiest member*, and
every chunk carries its own confidence inline. The `Lowest` column says why a group sits
where it does — otherwise a 3-chunk group above a 6-chunk one looks arbitrary.

**2. Ask how they want to review**, and honour the answer:

| Mode | What you do |
|---|---|
| **1 — live, one group at a time** | Full bodies for one destination file; take approve/retry/drop; then the next group. |
| **2 — async, one review file** | Write every chunk in full to a single markdown file for them to read at their own pace. |
| **3 — live, risky first, depth on request** | Flagged and low-confidence chunks in full; the rest listed by ID/title/target, and they pull any into full view. |

**Mode 2 costs the retry loop, and you must say so before they choose it.** The transcript is
discarded when the run ends, so `retry` stops being available once they leave. A placement
they dislike later is a **hand-edit against a transcript that no longer exists**, not a
re-proposal. Modes 1 and 3 keep the run live, where a retry is nearly free. Either offer to
hold the run open, or state the trade plainly.

**Nothing is hidden in any mode.** Confidence sets *order* and *depth*, never visibility — a
placement marked high-confidence and wrong is precisely the failure that matters, and a
filter would hide exactly that. Every mode at minimum **names every chunk** with its target
and confidence. Mode 3 is a depth control the reviewer operates, not a filter you apply.

Whatever the mode, they can:

- **approve** → validate, then write to staging (Stage 5)
- **retry `<id>` [reason]** → re-propose that chunk with their correction
- **drop `<id>`** → discard that chunk

Address chunks **by ID**, not by position — the list is grouped now, so a positional index
means something different depending on which group is on screen.

**This checkpoint is the human gate — there is no later PR into staging.** It has to be here,
because right now the transcript is still in context and re-proposing is nearly free. After
the run it is **gone** — never persisted, unless `archived` — and a wrong placement could
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
1  ingest                 transcript in, unmodified, never persisted unless `archived`
2  distill                typed chunks, decided/undecided, most of the transcript discarded
3  propose placements     INDEXES ONLY -- target + legal edges + confidence
3.4 resolve members       COLLECTIONS ONLY -- which member? ambiguous -> CREATE, flag it
3.5 dedup                 read ONLY the targets routing chose; drop dupes, flag conflicts
4a checkpoint             overview grouped by destination (riskiest group first), then
                          the reviewer picks a mode; approve / retry <id> / drop <id>  (THE human gate)
4b validate               legal-edge matrix; must pass
5  write to staging       approved chunks -> staging/candidates/ -> commit  (no PR; PR is at promotion)
```
