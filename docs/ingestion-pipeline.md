# context-mesh — conversation ingestion & distillation pipeline

Status: draft / design note. Written 2026-06-25. Specs the **process half** of
context-mesh: turning a conversation transcript into proposed graph nodes and typed edges,
landed in staging behind a human gate. The structure half is
[file-taxonomy.md](file-taxonomy.md); this is
how it gets *populated*.

## Design commitments (carried from prior decisions)

- **Two-step at heart** (from the seeding conversation): distill into labeled chunks, then
  decide what to do with each. This spec expands "decide" into propose-placements +
  human-gate + commit.
- **Routing is typed edges, not flat labels** ([knowledge-graph-model.md](knowledge-graph-model.md)).
- **Everything lands in staging first** — no chunk routes straight to canonical, even
  obvious facts. One uniform flow, one review surface, one promotion path (the existing
  staging→canonical human act, out of scope here).
- **The agent proposes full placements** — node *and* typed edges *and* a concrete target
  path/ID — and the human is an **editor** at the gate (approve / edit / reject per chunk).
- **The transcript is not modified** — no redaction, no anonymization. What arrives is what
  gets read. Only the distilled version is persisted (plus the transcript itself when
  `archived`, because nothing else would hold it).

## The pipeline (4 stages + a separate promotion step)

```
 transcript
    │
 [1] INGEST ────────────► distilled Conversation node (staging); transcript unmodified
    │
 [2] DISTILL ───────────► typed chunks (Knowledge / Requirement / DomainFact / …)
    │
 [3] PROPOSE PLACEMENTS ─► for each chunk: node + typed edges + target path/ID, in staging
    │                      INDEXES ONLY — never the target files
    │
 [3.5] DEDUP ───────────► read ONLY the targets [3] chose: drop duplicates, flag
    │                      contradictions. (Added 2026-07-16 — see the dedup question below.)
    │
 [4] HUMAN GATE ────────► in-run checkpoint — grouped by destination, riskiest first;
    │                      approve / retry N / drop N. THE gate: catches bad ROUTING while
    │                      the transcript is still in context and a retry is cheap. No PR
    │                      here — staging is private and each run writes new, unique-ID files.
    │
 [5] COMMIT (background)─► write approved nodes+edges straight to staging/candidates; no PR
    ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄
 (separate, later, human-initiated) PROMOTE staging → canonical  ← the PR gate lives here
```

### Stage 1 — Ingest
- Accept a transcript (Granola export, Slack thread, meeting transcript, chat log).
- **Do nothing to it.** No redaction, no anonymization, no substitution of speaker names.
  This was a `strip | enrich` PII policy through v2.3, and stripping was the default; it is
  gone as of v2.4. Normalizing a transcript is a *quality* concern, not a privacy posture —
  the useful form of it resolves a speaker to the right person rather than replacing them
  with a label, and it belongs in a **pre-pass**, not buried in ingestion.
- Emit one `Conversation` node (the distilled record) into staging. It carries a
  **source reference** plus source, date, participants as given, and a
  content hash — see [vocabulary.md](vocabulary.md#conversation--required-properties-added-v11-2026-07-16)
  (v1.1). The transcript is **discarded** after distillation, unless `archived`.
- An **optional pre-pass** can clean and label the raw transcript *before* stage 1 — the
  `structure-transcript` skill, or equivalently
  [`prompts/structure-transcript.md`](../prompts/structure-transcript.md) run anywhere (the
  skill is a thin wrapper around that prompt, which stays the source of truth). It does what a
  good Granola template does, but for any transcript from any tool. It is
  a pre-pass, **not** stage 1: it only cleans and labels (never types, never routes), and its
  output is still just a transcript that enters stage 1 the same way raw input does. **The
  pre-pass is where transcript-quality work belongs** — including, in future, resolving a
  speaker who appears under several names to one person.

#### Source and retention (specified 2026-07-16)

Two questions the spec previously left implicit. **Where the transcript comes from** was
unstated; **what happens to it after** was stated ("discard") but rested on an assumption
that turns out to hold only sometimes.

**The source must be identified, not just accepted.** Ingestion records a durable
`source_ref` — the Granola note ID, the Slack permalink, the ticket URL — because
`Conversation` is the provenance root every canonical fact hangs off. Without it, the answer
to "where did this come from?" is a node the agent wrote about a file that no longer exists.

**Retention splits by whether the source is already durable** — the key realization: in the
normal case, *we don't need to keep the transcript, because someone else already is.*

| `source_kind` | When | Retention |
|---|---|---|
| `referenced` | Granola, Slack, Zoom, a ticket — a system with its own retention and access control | **Store nothing.** Point at it. The no-raw-storage rule below applies in full. |
| `archived` | Hand-provided material with no datastore behind it | **Archive the transcript** at `source_archive`. Reference-only would point at nothing and the source would simply vanish. |
| `ephemeral` | Source gone, never archived | Nothing to point at. Legal but weak — **flag it at the gate.** |

**This does not reverse "no transcript stored."** That rule holds wherever it can — not
because the content is dangerous, but because a copy the mesh does not need is a copy that
drifts from the system that owns it. It assumed the material was *disposable* — true when the
source datastore keeps it, false when someone pastes in the only copy. The `archived` case is
a **narrow, deliberate exception for material that would otherwise be lost**, not a general
licence to accumulate transcripts.

**The archive is the transcript as received.** Through v2.3 it was a sanitized copy; as of
v2.4 nothing in this pipeline modifies a transcript, so what is archived is what arrived.
**Retention is the team's call about their own repo** — a mesh that does not want transcripts
in its history can `.gitignore` the archive path, which is a more honest lever than a pipeline
that quietly rewrites their content.

**What the archive needs, and does not have yet:** a retention period, an access-control
model, and a deletion path. Those are the client's obligations and their DPO's call — not
defaults this project should pick. Until an engagement decides them, `archived` is
implemented as "write it next to the Conversation node and say so plainly." **Open.**

### Stage 2 — Distill into typed chunks
- Break the conversation into atomic **chunks**, each assigned a **node type** from the
  controlled vocabulary: `Knowledge`, `Requirement`, `DomainFact`, plus discovery
  types where relevant (`Opportunity`, `Solution`, `Assumption`) and `OpenQuestion` for
  unresolved decisions.
- A single conversation yields any mix of these. Each chunk records a `derives-from` edge
  back to the `Conversation` node — provenance is mandatory.
- **Crucial split: fact vs. speculation.** Each chunk is tagged `decided` vs. `undecided`.
  Decided = a durable fact about the product/users/system. Undecided = speculation,
  feature request, ideation, open question. (This drives the staging substructure, not a
  canonical bypass — see Stage 3.)

### Stage 3 — Propose placements
For each chunk, the agent proposes a **complete placement** — this is the high-leverage
step:

- **Node**: the chunk rewritten as a context-file-shaped entry (title, body, frontmatter).
- **Typed edges**: concrete, legal-for-the-type edges with real targets, e.g.
  - `Knowledge → applies-to → payments-svc:OPP-0042`
  - `Requirement → references → STORY-0007`
  - `DomainFact → applies-to → payments`
- **Target path/ID**: the exact destination the human would approve into — but it is
  written to **staging**, tagged with its eventual canonical target. e.g. a `Knowledge`
  chunk proposes `→ product/business-context.md` and lands at
  `staging/candidates/<id>.md` *tagged for* that path.
- **Confidence + rationale**: each proposal carries a confidence and a one-line why, so the
  human can triage fast (skim high-confidence, scrutinize low).
- The node type determines which edges are **legal** (the routing logic from
  knowledge-graph-model.md). An illegal edge is a validation error, surfaced pre-gate.

Decided vs. undecided both land in staging; the tag controls *where in staging* and how the
promotion step later treats it — decided chunks are promotion-ready candidates, undecided
chunks carry their `OpenQuestion`s and route through the guided-resolution flow before they
can be promoted.

### Stage 4 — Human validation gate (the in-run checkpoint)
- An interactive surface (Slack, an LLM console, a terminal list — harness-agnostic) shows
  the human what the run produced *before* anything is written and while the transcript is
  still in context: counts by type, then the placements **grouped by destination file**, with
  groups ordered by their **riskiest member** and each chunk's confidence shown inline.
- **Then it asks how they want to read them** — group by group, as one async review file, or
  risky-first with the depth on request. The modes differ in *depth*, never in coverage: every
  chunk is named in all of them. The async mode costs the retry loop (the transcript is gone
  once the run ends), and that trade is stated before it is chosen.
- Per chunk: **approve** (take as-is), **retry `<id>` [reason]** (re-propose with a correction
  — cheap here because the source is still in hand), or **drop `<id>`** (discard).
- The human is an editor, not an author — the agent did the routing work; the human
  corrects and confirms. Batch-approve high-confidence chunks to keep throughput up.
- Nothing is written to the graph until this gate passes. **This is the whole human gate for
  ingestion — there is no separate staging PR** (see below).

### Stage 5 — Commit (background)
- Only after approval: a background process **writes** the approved nodes and edges **straight
  into** `staging/candidates/`, with `derives-from` provenance intact, on a single commit.
- **No PR at this stage.** A PR into staging would do neither job a PR is for: there is no
  concurrency to manage (each run writes *new* files with unique IDs, so two ingests never
  collide) and no separate review to add (Stage 4 already reviewed the same placements over
  the same content). Staging is a private holding pen nobody's tools read from; the undo for a
  bad candidate is deleting the file. **The PR gate lives at promotion**, where *existing*
  canonical documents get edited and concurrent promotions can target the same file.
- Idempotent: re-running ingestion on the same conversation (same content hash) updates,
  not duplicates.

### Separate step — Promotion (**built 2026-07-16**: `skills/promote-candidate/`)
Moving an approved staging candidate into canonical context is the **existing
human-initiated promotion act** (file-taxonomy Layer C; aiviz `promote-from-inbox`).
Ingestion's job ends at "approved and sitting in staging." Promotion is deliberately a
distinct decision so ingestion never silently mutates canonical context.

**What building it corrected in this spec.** The taxonomy called promotion "the act of moving
it (and writing its edges)". Against ten real candidates, that is wrong twice over:

- **It is a merge, not a move.** Only one of ten resembled moving a file. A `DomainFact` lands
  *in a section of an existing document*, extending or qualifying what's there.
- **It is not one verb.** Five outcomes, and the classifier decides which:
  **MERGE** (into the target file) · **CONTRADICTS** (target says the opposite — a human
  decides whether the doc or the world moves; never auto-applied) ·
  **RESOLVE** (an `OpenQuestion` doesn't promote — it resolves into another type first, via
  the guided-resolution flow below) · **NO-HOME** (`target: null`; fix the manifest first) ·
  **NEVER** (a `Conversation` is a provenance root and stays).
  (A fifth, **HANDOVER**, routed an item to the `Workflow` that owned its queue; it went with
  the workflow layer in v2.2; the design is retained privately.)

**Batched by target file.** Three of run 1's candidates targeted one document; promoting them
singly would mean three conflicting PRs against the same file and a human reading it three
times. One of the three was a `contradicts` — and **a contradiction can change what the other
candidates in its batch should say**, so it is resolved before the rest are merged, not merged
around.

**Candidates are kept, never deleted** — marked `state: canonical` once merged. The context
file states the fact; **the candidate is the audit trail**, carrying the `derives-from` chain
back to the conversation, which a canonical context file cannot hold. (`state: resolved`, for
an item handed to an external tracker, went with the workflow layer in v2.2.)

## The guided-resolution flow (for undecided material)

Undecided chunks (`OpenQuestion`, speculative `Opportunity`/`Requirement`) need a human
*decision*, not just a routing confirmation. The agent guides that:

1. Surface the open question with the context that raised it (`derives-from` the Conversation).
2. Offer the decision options it can infer, and what each would route to if chosen.
3. On a human decision, convert the chunk to a decided node with its now-legal edges and
   move it from "open" staging into promotion-ready staging.

This is the agentic "guide humans through the steps to figure out where it goes" from
the project's core principles, made concrete.

## Controlled vocabulary touch-point

Stages 2–3 classify into and enforce the **node/edge type system**, now locked in
[vocabulary.md](vocabulary.md) (**v2.2**). Stage-3 placement legality is exactly that doc's
**legal-edge matrix** — an edge not in the matrix is the validation error mentioned above.
The types this spec surfaced (`OpenQuestion`; edges `rendered-on`, `contradicts`) are folded
into the lock. It also surfaced `routed-to`, which was locked in and then **deferred in v2.2**
with the rest of the workflow layer.

## Open questions

- **Chunk granularity:** what's an "atomic" chunk — one fact, one paragraph, one topic?
  Too fine fragments context; too coarse hides multiple placements in one chunk.
- **Dedup against existing context:** before proposing a new `Knowledge` node, should the
  agent check whether that fact already exists (update vs. create)? Strongly leaning yes —
  otherwise ingestion accretes duplicates. Needs a cheap "does this already exist" lookup
  over the index.

  **Sharpened by the first real run (2026-07-16).** Two things this question did not
  anticipate:

  1. **Dedup can be the whole run.** Session `9fb6b926` yielded exactly one candidate chunk,
     and dedup killed it — the question it raised had been resolved hours later by the
     manifest reframe. Yield was zero. When a realistic transcript produces ~1 chunk, dedup
     is not downstream polish that can be tuned at the client; it decides the entire output.
     Its deferral in [build-scope.md](build-scope.md) deserves revisiting.
  2. **"A cheap lookup over the index" is not enough, and this is the real problem.** The
     check that mattered needed the *body* of `file-taxonomy.md`. The index entry said only
     "the manifest-vs-framework split" — true, and useless for deciding whether a specific
     question had been dissolved. An index lists *what a file is about*; dedup asks *what a
     file already says*. Those are different questions and the index only answers the first.

  **RESOLVED 2026-07-16: dedup reads the target file, after routing picks it.**
  The tension was real but it was not between dedup and index-only — it was between dedup and
  a *misreading* of index-only as "never open a context file during a run." The rule is about
  **routing**. Once routing has chosen a target from the index, reading that one file cannot
  influence where the chunk goes, because the decision is already made.

  - **Routing:** indexes only. Unchanged. Cost: N domains → 1 index each.
  - **Dedup (stage 3.5):** opens only the files routing already chose. Cost: ≤ N chunks, and
    only files that exist.

  What stays forbidden is reading *to* route — opening candidate files to work out where
  something fits — which is the whole-mesh load in slow motion, and would also make the
  index-only contract untestable (routing would always have the bodies to fall back on).
  `skills/ingest-conversation/scripts/collect_dedup_targets.py` derives the permitted read set
  from the placements, so the bound is auditable rather than a matter of restraint.

  **Dedup and conflict-detection are the same read**, which is why doing this now was cheap:
  the target either already makes the claim (drop it as a duplicate) or makes a *different*
  claim about the same thing (a `contradicts` edge — see the conflict question below). One
  file read answers both.

  Validated against run 1 (5 chunks → 2 reads): caught `rf-0005`, which had predicted itself
  a likely duplicate and could not check, and `rf-0003`, whose target file documents the
  opposite behavior. Both would have shipped without this.

  **Still open:** dedup against *staging* (sibling candidates from another conversation) — out
  of scope; the human sees both at the gate.
- **Conflict handling:** a chunk that *contradicts* existing canonical context — flag for
  human as a conflict edge, don't silently overwrite. Likely a dedicated `contradicts` edge.
- **Surface choice:** which validation surface to build first (Slack vs. LLM console vs.
  PR-review). Andy left this open.

  **Answered 2026-07-16, revised 2026-07-20: ingestion has one gate — the in-run checkpoint.**
  The built skill stops at a scannable overview grouped by destination file, `approve` /
  `retry <id>` / `drop <id>`, *before anything is written*, while the transcript is still in
  context and a retry costs a sentence. On approval it writes **straight to staging — no PR**. An earlier cut
  opened a staging PR as a second surface, but it did neither job a PR is for: no concurrency
  (each run writes new, unique-ID files) and no new review (the checkpoint already saw the same
  placements). **The PR gate belongs at promotion**, where existing canonical documents are
  edited and concurrent promotions can collide. See [build-scope.md](build-scope.md) decision 1
  as revised.

- **Confidence threshold for batch-approve:** tune later against real transcripts.

  **Reframed 2026-07-16 — confidence orders, it does not filter.** A threshold that hid
  high-confidence chunks would hide exactly the failure that matters most: a placement the
  agent was **confidently wrong** about.
  **Extended 2026-08-06 — confidence now sets order *and depth*, still never visibility.**
  Placements are grouped by destination file (how a document is actually reviewed, and how
  promotion batches), groups sort by their riskiest member, and each chunk shows its own
  confidence. The reviewer picks how deeply to read, but **every mode names every chunk** — the
  depth control is theirs to operate, not a filter the skill applies.
  Full visibility, prioritized — not a subset.