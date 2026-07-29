# context-mesh — build scope (first cut)

Status: scoping decision. Written 2026-07-16. The design is done deciding on paper
(see the [README](../README.md)); this is what gets built first and — just as importantly —
what does not.

## The goal

A **substantially working tool** for the client engagement, so it can iterate in place. The
demonstrable core is the ingestion pipeline end to end: **transcript → a reviewed set of
routed context in staging.** Everything else is downstream of having anything in the graph at
all.

## The insight that shrinks the scope

The [pipeline spec](ingestion-pipeline.md) lists five stages, but they are not five things to
build:

| Stage | What it actually is |
|---|---|
| 1 — Ingest & sanitize | a prompt |
| 2 — Distill into typed chunks | a prompt + the [vocabulary](vocabulary.md) as schema |
| 3 — Propose placements | the same LLM call; the legal-edge matrix is the validation |
| 4 — Human gate | **the in-run checkpoint** (decided below) |
| 5 — Commit | `git` — direct to staging, no PR |

So the first cut is a **prompt, a schema, and a thin wrapper** — not an application. Stages 2
and 3 are one call: the vocabulary already tells the model which types exist and which edges
are legal.

## Decisions

### 1. The human gate is the in-run checkpoint; staging is a direct write

The run stops at an **in-run checkpoint** before anything is written: every placement listed
**least-confident first**, and the human can `approve`, `retry N <reason>`, or `drop N`. On
`approve`, the tool validates and writes each chunk straight to `staging/candidates/` on a
commit. **No branch, no PR.**

| Spec's gate action | Checkpoint equivalent |
|---|---|
| approve | approve → validate → write to staging |
| edit | `retry N <reason>` — re-propose with the correction, transcript still in hand |
| reject | `drop N` |
| defer | leave the run unapproved |

**Why the checkpoint and not a PR.** An earlier cut opened a PR into staging as the gate. It
was the wrong gate in two ways. First, it was honest about `approve` and dishonest about
`edit`: "edit the file in the branch" means, for a wrong placement, hand-authoring
frontmatter, edges, and IDs — *redoing the agent's routing by hand, without the transcript,
which by design no longer exists.* The checkpoint has a real feedback channel (`retry`),
because it runs while the transcript is still in context and re-proposing is nearly free.
Second, a PR into staging does neither job a PR is for: there is **no concurrency** to manage
(each run writes *new* files with unique IDs, so two ingests never collide) and **no separate
review** to add (the checkpoint already reviewed the same placements). It would gate a private
holding pen nobody's tools read from.

**The PR lives at promotion instead.** `promote-candidate` edits *existing* canonical
documents — concurrent promotions can target the same file, and the content is org-wide — so
there the PR earns both its jobs. Staging is cheap and private; the undo for a bad candidate
is deleting the file. Canonical context is shared and expensive; that is where the deliberate,
diffed, PR-gated approval belongs. One gate, at the point where the stakes and the contention
actually are.

**Ordering, not filtering.** Everything is shown, always. Confidence sets the order, never
the visibility — a chunk marked high-confidence and wrong is exactly the failure that
matters, and a confidence filter would hide precisely that.

### 2. Routing input is the index only

To route a chunk, the agent reads each repo's **index/loader** — the file list plus
when-to-load conditions — and routes against those descriptions. It does **not** open the
target files, and it does **not** load the mesh.

**Why:** this is precisely what the index is for, and it is the progressive-disclosure
contract the whole design rests on. It stays cheap across ~100 repos. Loading the whole mesh
is the Client A "Team B" anti-pattern — rebuilding context at runtime, every query — that this
project exists to kill.

**This is the design eating its own dog food:** if the index is not sufficient to route by,
the progressive-disclosure contract is broken. Better to learn that here than at the client.

**Amended 2026-07-16 — the restriction is on *routing*, not on the whole run.** Dedup now
reads the target file **after** routing has chosen it (stage 3.5). The rule is unchanged
where it matters, and the distinction is the timing:

| | Routing | Dedup |
|---|---|---|
| **When** | Before a target exists | After the target is fixed |
| **Reads** | Indexes only | The one file routing chose |
| **Asks** | What is this file *about*? | What does it already *say*? |
| **Cost** | N repos → 1 index each | ≤ N chunks, existing files only |

Reading *after* the decision cannot influence the decision, so the index-only contract stays
testable — routing never gets the bodies to fall back on. Reading *before* (opening candidate
files to work out where something fits) is the whole-mesh load in slow motion, and remains
forbidden. `scripts/collect_dedup_targets.py` computes the permitted read set from the
placements, so the bound is auditable rather than a matter of the agent's restraint.

Run 1 re-checked with dedup on: **5 chunks → 2 file reads**, against a mesh of 3 repos and
13 context files. The bound holds.

### 3. The index **is** the manifest — *closes the open question*

One authored file per repo, listing every context file and when to load it. It serves three
roles at once:

- the **manifest** — what this implementation's file list is (see
  [file-taxonomy.md](file-taxonomy.md#the-manifest-split-what-varies-per-implementation))
- the **routing input** — what the ingestion agent reads (decision 2)
- the **progressive-disclosure contract** — what any harness reads to know what to load

**Why not a separate `mesh-manifest.yml`:** it would be a second copy of the same list, and
per the authored-vs-generated rule, two
*authored* copies drift. One authored file cannot.

### 4. The first cut assumes a mesh exists

No scaffolding. A small mesh is hand-authored to test against. Scaffolding ~100 repos is a
client-onboarding concern, not a demo concern.

**Refined 2026-07-16 — `setup-mesh` exists, and the line holds.** A second skill
(`skills/setup-mesh/`) prepares a repo *to receive* ingestion. It sits deliberately on this
side of the scaffolding line:

| Setup **does** | Setup **does not** |
|---|---|
| Find `context-index.md`, or declare one from what already exists | **Generate context files** |
| Declare the workflow — where to-dos go — and write the pointer | Author any file's content |
| Report which files are listed-but-missing / present-but-unlisted | Emit the default manifest |

**Why the line falls there.** Generating context files means generating the **manifest** —
per-implementation config the engagement decides, not something a wizard emits. And an **empty
context file is worse than an absent one**: the index would list a file that exists and says
nothing, and *routing reads the index*. Ingestion would confidently route a fact to
`business-context.md — why the platform exists` and land it in a stub. **An absent file is an
honest gap the skill reports; an empty file is a lie the skill believes.**

**Why setup is nonetheless needed.** The workflow half has no path today: a `Todo` may only be
`routed-to` a `Workflow`, and a real repo has no declared workflow and no way to get one short
of hand-authoring. That's not scaffolding — it's the thing ingestion needs to run at all
(v1.2, and run 1's two unroutable `Todo`s).

**Amended 2026-07-21 — scaffolding *is* setup, and the line above survives the scale-up.**
There is no separate `/mesh-init` (see [setup-scope.md](setup-scope.md)). Setup generalizes to a
prompted **set** of repos, stands up the Hub on every run if absent, and is **idempotent**, so
"run it again in a new repo" is the add path rather than a second mode. What that adds to the
right-hand column above is only **containers**: setup creates directories
(`staging/candidates/`, `process/workflows/`) and the index file itself, but still **never
creates a context file listed in that index**. An empty directory routes nothing and an empty
index honestly says "no context yet"; only a stub *listed as* holding something is the lie
decision 4 forbids. The distinction was always container-vs-claim, and only the claim was
banned.

**No transcript-source config, deliberately.** An early cut of this had a gitignored per-person
file holding "which transcription tool do I use." Dropped: an org can run Granola *and* Otter
*and* Zoom, and the same person pastes ad hoc text some days — so the value varies per
*transcript*, not per person. A saved default would be a hint the skill must second-guess, and
`source_kind` decides whether the raw transcript survives. Ingestion **infers the source from
the input and confirms it** (stage 1a). Same question, answered better, with no file to
maintain and no stale default to mislead.

## In scope

- **One command:** transcript → distilled typed chunks → proposed placements → checkpoint →
  staging.
- Chunks land in `staging/candidates/`, each with mandatory `derives-from` provenance back
  to the `Conversation` node, and each tagged `decided` / `undecided`.
- Placement legality validated against the [legal-edge matrix](vocabulary.md).
- A hand-authored **test mesh**: an index plus a few context files.

## Out of scope (deliberately)

Everything downstream of getting nodes into the graph:

- **Promotion** (staging → canonical) — a separate human act by design.
- ~~**The CI mirror** and Hub↔leaf sync.~~ **Deleted 2026-07-21** — there is one repo; nothing to sync.
- **Hub snapshot refresh** — now a manual re-promotion PR, no staleness gate (see
  [promotion-boundary.md](promotion-boundary.md)); still out of scope for the first cut.
- **Sidecars.**
- **Multi-repo setup** — ~~scaffolding (`/mesh-init`)~~. **Reframed 2026-07-21:** there is no
  separate scaffolding command; it collapses into `setup-mesh` taking a set of repos and
  standing up the Hub ([setup-scope.md](setup-scope.md)). Still out of scope for the first cut,
  which assumes one hand-authored mesh.
- ~~**Dedup against existing context**~~ — **moved in scope 2026-07-16.** It
  was deferred on the theory that it needs target-file reads and so conflicts with decision
  2. It does need them; it does not conflict, once the read happens *after* routing. Run 2
  forced this: a real transcript yielded one chunk, dedup killed it, and yield was zero — at
  that yield dedup is not downstream polish, it decides the entire output. Re-checking run 1
  found a duplicate (`rf-0005`, which had *predicted itself* a likely duplicate and could not
  check) and a contradiction (`rf-0003`, whose target documents the opposite behavior). Both
  would have shipped.
- **Dedup against *staging*** — still out. Stage 3.5 checks the target file, not sibling
  candidates. Two conversations covering the same ground produce two candidates and the human
  sees both; re-ingesting the same conversation is handled by the content hash.

## Still open — answered by building, not by discussion

- **Plugin or not** — the surface is now visible: a prompt plus file writes plus a checkpoint
  (and, at promotion, a PR). That shape fits a Claude Code plugin naturally, and the
  harness-agnostic constraint holds
  because everything it writes is markdown a human or another harness can read. **Not yet
  decided** — tied to the publish decision.
- **Chunk granularity** — one fact / one paragraph / one topic. Pick a default, tune against
  real transcripts.
- **Conflict handling** — a chunk that contradicts canonical context gets a `contradicts`
  edge and human attention; never a silent overwrite.

## The one real gap

**No realistic transcript to build against.** Candidate: dogfood this project's own design
sessions from `~/.claude/projects/` — real transcripts of real decisions that can be
independently verified. Avoid synthetic transcripts written against the locked vocabulary;
they route suspiciously well and teach nothing.

### Update (2026-07-16, after the first two runs) — the dogfooding candidate failed

**`~/.claude/projects/` is a poor source, and the plan above is retired.** Tested against
session `9fb6b926`: **yield was zero durable chunks.** Two structural reasons, neither fixable
by picking a better session:

- **These sessions are mostly retrieval.** The assistant reads a doc and reports it. Recited
  content is a copy of a file that already exists — ingesting it manufactures duplicates.
  Retrieval is not discovery.
- **The repo out-competes ingestion.** When a Claude Code session *does* decide something
  durable, that same session writes it into the docs immediately. By the time a transcript
  could be ingested, its content is already canonical. Ingestion arrives second, always.

**Granola meeting transcripts are the real source** — multi-human conversation, where the
decision happens in the room and *nobody writes the doc*. That is the gap ingestion exists to
fill, and it is the case still untested.

The synthetic-transcript warning above stands, and run 1 shows why it is not absolute: a
hand-written transcript in a domain the author knows, written *before* looking at the
vocabulary, surfaced three real gaps (`Todo` unroutable, cross-cutting facts homeless, the
validator wrong). Useful — but it cannot tell us whether the prompt generalizes, because the
same session wrote both the transcript and the router.
