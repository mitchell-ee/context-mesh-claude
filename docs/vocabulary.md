# context-mesh — node & edge vocabulary (the schema)

Status: **LOCKED v2.3** (v1 2026-06-25; v1.1–v1.3 2026-07-16; v2.0 2026-07-21 — the
single-Hub collapse; v2.1 2026-07-30; v2.2 2026-08-03 — workflow routing deferred,
domains under `domains/`; **v2.3 2026-08-04 — the mesh declares its own vocabulary
version**, see Versioning). This is the controlled vocabulary — the type system of
the knowledge graph. It is the schema the rest of the system references:
[ingestion-pipeline.md](ingestion-pipeline.md) stages 2–3 classify into these types and
[file-taxonomy.md](file-taxonomy.md) stores them. Changes here ripple everywhere —
version-bump and update dependents.

Locked per the starter vocabulary in
[knowledge-graph-model.md](knowledge-graph-model.md). What changed from the starter list:
- Node types are grouped by **lifecycle role** rather than listed flat — the three groups
  have different edge rules.
- Collapsed near-duplicate edges: `references`/`links-to` → **`references`**;
  `applies-to`/`applies-across` → **`applies-to`** (cardinality is a property of the
  target, not a separate edge).
- Dropped `Artifact` as a node type — it was a catch-all spanning two groups; the concrete
  discovery types replace it.
- Added types surfaced downstream: node `OpenQuestion`; edges `routed-to`, `rendered-on`,
  `contradicts`, `parent-of`.

**v2.0 in one line:** all context lives in the AI Hub, partitioned into **domain** folders, so
the node formerly called `Repo` is now `Domain`, `RepoFact` is now `DomainFact`, and the two
cross-repo provenance edges (`mirrored-from`, `promoted-from`) are **removed** — there is no
second repo to mirror from or promote across.

**v2.1 in one line:** work that has no discovery lineage gets a type (`Task`), a `Workflow`
now says **what it creates** as well as where it lives, and `Persona` admits it is keyed by
`slug` rather than inert. All additive.

**v2.2 in one line:** the mesh holds context, not work — `Todo`, `Task`, and `Workflow` and
their edges are **deferred out of the schema**, and domains now live under an
explicit `domains/` folder. Breaking.

---

## Node types

Three groups by lifecycle role. The group determines which edges are legal (see matrix).

### Group A — Ingestion types (what a distilled chunk *is*)
Transient by nature: produced by ingestion, live in staging, and either promote into a
Group-B/C node or are dropped. Every Group-A node **must** carry `derives-from`.

| Type | Meaning | Promotes toward |
|---|---|---|
| `Conversation` | A distilled, PII-cleared interaction. The provenance root. Carries a **source reference** — see below. | (stays; never promoted) |
| `Knowledge` | A durable fact about product/users/system. | canonical context file (Group C) |
| `Requirement` | A new capability/constraint to build. | `Opportunity`/`Solution`/`Story` (Group B) |
| `DomainFact` | A fact specific to one domain — its code, quirks, conventions. | that domain's canonical context (Group C) |
| `OpenQuestion` | An undecided point needing a human decision. | resolves into one of the above |

> **`Todo` was a Group-A type through v2.1** and is deferred as of v2.2 — the design is retained privately
> and may return as a future feature. A conversation that produces
> an action item still produces one; the mesh no longer types or routes it. Ingestion reports
> it as out of scope rather than placing it.

#### `Conversation` — required properties (added v1.1, 2026-07-16)

The `Conversation` node is the provenance root: every ingested node hangs off it via
`derives-from`. That makes it the **only** thing standing between a canonical fact and
"where did this come from?" — so it must point at something a human can actually go and
read. A provenance root that only summarizes is not provenance; it is the agent's word for it.

| Property | Required | Meaning |
|---|---|---|
| `source_ref` | **yes** | A durable pointer to the transcript in **its own datastore** — Granola note ID, Slack permalink, Zoom recording ID, ticket URL. |
| `source_kind` | **yes** | `referenced` \| `archived` \| `ephemeral` — see below. |
| `source_archive` | when `archived` | Path to the archived copy this project holds. |
| `content_hash` | **yes** | Hash of the raw input. Idempotency: re-ingesting the same conversation updates rather than duplicates. |
| `source` | **yes** | Human-readable description ("checkout/payments sync, 2026-07-14"). |
| `date`, `participants` | **yes** | Participants role-anonymized where required. |

**`source_kind` — the three cases, and why the distinction is the whole point:**

- **`referenced`** — *the normal case, and the one to design for.* The transcript already
  lives in a system with its own retention, access control, and deletion path (Granola,
  Slack, Zoom). context-mesh points at it and **takes no custody of PII**. Best of both:
  a real audit trail, none of the retention burden.
- **`archived`** — *the exception.* Someone hand-provided a transcript with no datastore
  behind it. Reference-only would point at nothing, so the raw material would simply vanish.
  It is archived (`source_archive`) **so it doesn't disappear** — see the retention note in
  [ingestion-pipeline.md](ingestion-pipeline.md).
- **`ephemeral`** — the source is gone and was never archived. **Legal but weak**: the facts
  derived from it cannot be checked against anything. Flag it at the gate; never let it be
  the silent default.

**This does not reverse the no-raw-storage rule** ([ingestion-pipeline.md](ingestion-pipeline.md)).
That rule stands for `referenced`, which is the case that should dominate: a transcript is
the highest-PII artifact in the system, and the cheapest way not to leak it is not to hold
it. `archived` is a deliberate, narrow exception for material that would otherwise be lost —
custody is the exception, not the default.

### Group B — Discovery & work artifacts (the board-object graph; multi-sibling, **ID'd**)
Durable, multi-instance, the aiviz model. 4-digit **domain-prefixed** IDs
(`payments:OPP-0042`). These form the outcome→story traceability chain via `parent-of`.

| Type | ID | Parent (via `parent-of`) |
|---|---|---|
| `Outcome` | `OUTCOME-NNNN` | — (top of tree) |
| `Opportunity` | `OPP-NNNN` | `Outcome` |
| `Solution` | `SOL-NNNN` | `Opportunity` |
| `Assumption` | `ASSUMPTION-NNNN` | `Solution` (optional — see below) |
| `Story` | `STORY-NNNN` | `Solution` (optional), and `Epic` within an iteration |
| `Epic` | `EPIC-NNNN` | (groups `Story`s) |
| `Interview` | per-iteration | — (feeds synthesis) |

ID numbering runs **`0000`–`9999`**. `0000` is legal and conventionally means "precedes
everything" — a foundational artifact that came before the numbered work.

#### A parent is optional everywhere (revised v2.2, 2026-08-03)

**Requiring a parent was a mistake.** A parentless `Story` is legal, and so is a parentless
`Assumption`. The chain is satisfied **as far up as it goes** — a team doing assumption
mapping without a full opportunity-solution tree is a legal, expected configuration, and so is
a team writing stories before any discovery has happened.

The case that forced it: an assumption whose operative content is *which solutions not to
design yet* ("defer the student home surface until students have been interviewed"). It
constrains **whether to build anything**, so it cannot have a parent solution — the tree has
zero solutions, by design. Requiring one gave it no legal home.

**Prefer an explicit absence over a blank field:**

```yaml
parent: none
parent-rationale: constrains whether to build at all; no solution exists to hang it from
```

A blank or missing `parent-*` key reads as *"not filled in yet."* `parent: none` plus a reason
says *"this genuinely has no discovery lineage,"* which is a **finding**, not an omission.

`check_references.py` only checks that a *named* parent resolves, so a parentless artifact was
already legal to the walker — this revision fixes the documentation and the authoring
convention, not the validator.

> **`Task` was a Group-B type in v2.1** — work with no discovery lineage, `TASK-NNNN`, no
> parent — and is deferred as of v2.2 alongside the rest of the workflow layer. The design is retained privately
> and may return as a future feature. Note that with parents now
> optional, the thing that distinguished a `Task` from a `Story` is parentless *by nature*
> versus *yet*, which the taxonomy cannot tell from the file; any restoration must
> re-establish why the type earns its place.

### Group C — Canonical context & structural (singletons, **path-referenced**)
The slow foundation. One authored instance each; referenced by path.

| Type | Meaning |
|---|---|
| `ContextFile` | A canonical context file (business-context, coding-standards, etc.). |
| `Persona` | A customer/stakeholder persona. **Keyed by `slug`** — see below. |
| `Architecture` | Cross-cutting technical architecture. |
| `Domain` | A namespace within the Hub — one folder under `domains/`, holding all context about one thing. See below. |
| `Board` | An external visual surface (Miro / Claude Design) — view only, never canonical. |

> **`Workflow` was a Group-C type through v2.1** — a triggerable process, usually a pointer to
> an external system — and is deferred as of v2.2. The design is retained privately
> and may return as a future feature.

#### `Domain` — the namespace node (replaces `Repo`, v2.0, 2026-07-21)

All context lives in the **AI Hub**, the one repo. A `Domain` is a **folder under `domains/`**
holding all context about one thing, and it is what `applies-to` targets — the answer to "what
is this context *about*."

| Property | Required | Meaning |
|---|---|---|
| `name` | **yes** | The folder name and the ID prefix (`payments` → `payments:OPP-0042`). |
| `about` | **yes** | What this domain covers, in a line. Declared in the index. |

**A domain lives at `domains/<name>/` and nowhere else (v2.2, 2026-08-03).** Through v2.1
domains sat at the Hub root beside the cross-cutting folders, and tooling had to *guess* which
top-level directories were domains — `survey_mesh.py` did it by looking for a `product/`,
`technical/`, or `process/` subdirectory. That heuristic misfired in the first third-party run:
a `docs/product/` folder holding market research was reported as a domain, while the real
domain tree, having no such subdirectory, was missed. **The heuristic found the wrong one of
the two.**

An explicit container removes the guess. Anything under `domains/` is a domain; nothing else
is one, whatever it is called. There is no ignore list to maintain and no detection rule to
tune, because there is no detection.

**A `Domain` is not necessarily a code repository.** It may map 1:1 to one repo, span several
(a `payments` domain covering payments-svc, ledger-svc, refunds-svc), or be finer than one.
**Which domains exist is *manifest*** — per-implementation config, decided per engagement, the
same treatment the context-file lists get ([file-taxonomy.md](file-taxonomy.md)). **That
domains exist, are folders, and own their context exclusively is *framework*** and does not
vary.

The rename from `Repo` is not cosmetic. `Repo` asserted a physical fact (this context sits in
that git repository) that is no longer true — **code repos hold no context and are unaware of
the mesh**. `Domain` asserts a logical one (this context is *about* that thing), which is what
every edge actually meant.

**Ownership is declared, not structural.** When context lived in many repos, "authored in
exactly one place" was enforced by repo boundaries. In one Hub it is true by default, so
*which team owns a domain* is now a declaration (`owned-by`, CODEOWNERS) rather than something
the filesystem enforces.

#### `Persona` — keyed by `slug`, one file each (added v2.1, 2026-07-30)

`Persona` is the one Group-C type that is **not inert**. Other singletons are referenced by
path and nothing validates their name; a persona is referenced **by `slug`** from every
`Story` that names an actor, so the slug is load-bearing and a missing persona is a real
dangling reference.

| Property | Required | Meaning |
|---|---|---|
| `slug` | **yes** | The key stories reference (`mentor`, `courier`). Unique within the mesh. |
| `name` | **yes** | Display name. |
| `emoji` | no | A single emoji for board rendering. Absent → renders without a prefix. |

**One file per persona**, at `product/personas/{slug}.md`. There is **no legend file.** A
slug→emoji table living apart from the personas is a second source of truth: it goes stale,
and detecting the staleness needs machinery that exists only because the table exists. With
`emoji` on the persona, the failure mode becomes "persona file missing" — a real, actionable
error a validator can check — instead of "legend is out of date."

Rendering surfaces (a Miro story-map legend, say) **derive** the mapping by reading the
persona files. Derived views are fine; a stored second copy is not.

---

## Edge types

All edges are **directed and named**. `source —edge→ target`.

| Edge | Direction | Meaning |
|---|---|---|
| `derives-from` | Group-A node → `Conversation` | Provenance. Mandatory on every ingested node. |
| `references` | any → `Domain` / Group-B node | A soft mention/link (collapses old `references`+`links-to`). |
| `applies-to` | `Persona`/`Architecture`/`Knowledge`/`DomainFact` → `Domain` | This context governs that domain. Cardinality (one vs. many domains) is a property of the edge set, not a separate edge (old `applies-across` removed). |
| `parent-of` | Group-B → Group-B | The traceability chain (Outcome→Opp→Sol→Story; Epic→Story). Inverse of the aiviz `Parent X` frontmatter. **Optional** — see Group B. |
| `contradicts` | any → any | This node conflicts with that one. Flagged for human, never auto-resolved. |
| `rendered-on` | Group-B node → `Board` | An optional visual view. Dropping it loses no context. |
| `owned-by` | any → team | The single authoring owner. Declared, not inferred from location. |
| `loaded-by` | `ContextFile` → index/loader | Progressive-disclosure: when this file loads. |

> **Three edges were deferred in v2.2:** `triggers` (`Requirement` → `Workflow`), `routed-to`
> (`Todo`/`Task` → `Workflow`), and `creates` (`Requirement`/`Workflow` →
> `Story`/`Epic`/`Task`). All three existed only to move an action item into a queue. The design is retained privately
> and may return as a future feature.

---

## Legal-edge matrix (the routing logic)

For each **source** node type, the edges it may legally originate. This *is* the routing
logic the ingestion agent enforces at propose-time (stage 3) — an edge not in this matrix
is a validation error.

| Source type | Legal outgoing edges |
|---|---|
| `Conversation` | `references` |
| `Knowledge` | `derives-from`, `applies-to`, `references`, `contradicts` |
| `Requirement` | `derives-from`, `references`, `contradicts` |
| `DomainFact` | `derives-from`, `applies-to`, `references`, `contradicts` |
| `OpenQuestion` | `derives-from`, `references` |
| `Outcome` | `parent-of`, `rendered-on` |
| `Opportunity` | `parent-of`, `references`, `rendered-on` |
| `Solution` | `parent-of`, `references`, `rendered-on` |
| `Assumption` | `references`, `rendered-on` |
| `Story` | `parent-of`, `references`, `rendered-on` |
| `Epic` | `parent-of`, `rendered-on` |
| `Interview` | `references` |
| `ContextFile` | `applies-to`, `references`, `loaded-by`, `owned-by` |
| `Persona` | `applies-to`, `references` |
| `Architecture` | `applies-to`, `references` |
| `Domain` | `owned-by` |
| `Board` | (none — terminal; only a `rendered-on` target) |

Reading the matrix as routing: a `Knowledge` chunk `applies-to` a domain and may `contradict`
existing context (flagging a conflict). A `Requirement` records a capability or constraint and
may contradict what is already documented, but the mesh does not route it into a process —
that is the work, and the work is out of scope (v2.2). This is the type system "doing real work
as a schema," as knowledge-graph-model.md put it.

---

## Tags (not edges)

Two boolean/enum tags ride on nodes; they are not relationships:
- `decided` | `undecided` — drives where in staging a chunk sits (ingestion stage 2).
- `state: staging | canonical` — promotion lifecycle position.

> **`state: resolved` was a third value through v2.1** — a candidate promoted *out of* the
> mesh, into the external system its `Workflow` named. It existed only for workflow handover
> and is deferred with it (v2.2). The design is retained privately
> and may return as a future feature.

### There is now exactly one "promotion" (v2.0)

Through v1.3 two unrelated things were both called promotion, and the vocabulary had to warn
against conflating them: staging → canonical (marked by `state:`) and leaf → Hub (marked by
`promoted-from`). **The second no longer exists.** With all context in one Hub there is no
access boundary to cross and no second repo to snapshot into, so `promoted-from` is removed
and the name collision is gone with it.

**"Promotion" now unambiguously means staging → canonical**: a human accepting an ingested
candidate into a context file, recorded by the `state:` tag and the candidate's own
frontmatter.

---

## Versioning

This vocabulary is **v2.3**. Adding a type is a minor bump; changing an edge's legality or
removing a type is a major bump and requires updating every dependent doc. **Adding a
required property to an existing type is a minor bump** — it constrains what a valid
instance looks like without changing what the graph traverses. (This case was unspecified
until v1.1 needed it.) The lock exists so ingestion and storage agree on one schema.

### v2.3 (2026-08-04) — the mesh declares its own vocabulary version. **Additive.**

**The Hub root's `context-index.md` carries a `**Mesh vocabulary:**` line** in its Identity
block, beside `**PII policy:**`. It names the schema version the mesh's content is written
in. Additive: a mesh without the line is valid, and reads as *unknown*, never as *current*.

**It is a prompt trigger, not a selector.** Setup reads it to decide whether to *say*
something; every migration decides whether it applies by inspecting content shape. If the
marker selected migrations, an unmarked mesh — every mesh built before this version — would
silently skip all of them. Migrations run in full, always, and guard themselves.

**Root only.** One marker per mesh: a domain-level copy could disagree with the root's, and
there is nothing a per-domain vocabulary version would mean.

The mesh does not migrate itself. `skills/setup-mesh/migrations/` holds one guarded,
idempotent file per convention change, under a rule stricter than the schema requires:

> **A migration only ever edits an index, or reports. It never moves, deletes, or rewrites
> content in the mesh.**

The plugin only ever *adds*. Mesh content is the team's, often the only copy, and worth more
than the tooling — so a migration that would relocate a directory it might have
misidentified **reports instead**, and the human moves it.

**Two v2.2 changes need no migration**, recorded so nobody writes a no-op later: parents
becoming optional and IDs widening to `0000`–`9999` are both pure loosenings. Existing
content stays valid. A convention change needs a migration only when existing content becomes
**wrong**, not when it becomes non-mandatory.

### v2.2 (2026-08-03) — workflow routing deferred; domains under `domains/`. **Breaking.**

Two unrelated changes, bumped together because both are breaking and both landed in one pass.

#### 1. The mesh holds context, not work

**`Todo`, `Task`, and `Workflow` are removed from the schema**, along with the edges
`routed-to`, `triggers`, and `creates`, and the `state: resolved` tag value. The complete
design — property tables, storage rule, template, findings — is retained privately as a deferred feature spec.

| Change | Detail |
|---|---|
| Remove type | `Todo` (Group A) |
| Remove type | `Task` (Group B) — added v2.1, removed four days later |
| Remove type | `Workflow` (Group C) |
| Remove edges | `routed-to`, `triggers`, `creates` |
| Remove tag value | `state: resolved` |
| Narrow | `Requirement` keeps `derives-from`, `references`, `contradicts`; loses `triggers`, `creates` |

**Why.** The mesh is about **supporting context, not about the work**. A queue is not context;
it is the work itself. `Workflow` entered the vocabulary as a *pointer* to respect that line,
but it entered at all because it was a defined part of the `ee-pm` plugin — **and ee-pm
combines context and workflow natively.** The mesh inherited a distinction that was never its
own.

Three things followed: everyone handles work items differently (Jira, Linear, GitHub, a
markdown file), so modelling "where work goes" means modelling all of them for no contextual
return; the *nature* of the content differs (durable and decided vs. transient and in-flight),
so one schema holding both keeps bending toward whichever it was last asked about; and
`creates:` described **what the receiving system does with an item**, which is that system's
business, not the mesh's.

**Why removal rather than deprecation.** Same reasoning as v2.0's removal of `mirrored-from`:
a deprecated-but-legal type is a fail-open trap. A validator would accept it and check nothing,
an author would find it documented and use it, and neither would be wrong to. Moving it to a
proposal makes the deferral unambiguous while keeping it recoverable.

**Two Minotaur findings dissolve rather than get fixed** — finding 3 (a single-domain Hub had
nowhere legal for a `Todo` to route) and finding 5 (`survey_mesh.py` promised a
`process/workflows/` directory the scaffold correctly refused to create). Both are recorded in
the proposal, since a restoration would reintroduce them.

#### 2. Domains live under `domains/`

| Change | From | To |
|---|---|---|
| Domain location | `<hub-root>/<name>/` | **`<hub-root>/domains/<name>/`** |
| Domain detection | heuristic (a dir containing `product/`, `technical/`, or `process/`) | **none — the path is the declaration** |

**Why.** Domains sat beside the cross-cutting folders at the Hub root, so tooling had to guess
which top-level directories were domains. In the first third-party run, `looks_like_domain()`
reported a `docs/product/` folder holding market research as a BLOCKED domain, while the actual
domain tree — having no `product/` subdirectory of its own — was **not detected at all**. The
heuristic found the wrong one of the two, exited 1, and printed scaffold instructions that
would have committed the repo to a structure it never wanted.

An explicit container deletes the problem class rather than tuning it: anything under
`domains/` is a domain, nothing else is, and there is no ignore mechanism to maintain because
there is nothing to ignore.

**No compatibility shim.** A tolerated legacy location would keep the ambiguous detection alive
in the code, which is the bug. Existing meshes move their domain folders under `domains/`.

#### 3. Parents are optional (documentation fix, not a schema change)

`parent-of` was never enforced as required by the walker — `check_references.py` only checks
that a *named* parent resolves — but [file-taxonomy.md](file-taxonomy.md) marked `Parent
Solution` **required** on assumptions, and ee-pm enforced it. **Requiring a parent was a
mistake.** A parentless `Story` and a parentless `Assumption` are both legal; the chain is
satisfied as far up as it goes. Prefer explicit `parent: none` + a rationale over a blank
field. See Group B.

**Also settled:** ID numbering runs `0000`–`9999`. `0000` is legal and conventionally means
"precedes everything."

**Dependents updated:** [file-taxonomy.md](file-taxonomy.md),
[ingestion-pipeline.md](ingestion-pipeline.md), [setup-scope.md](setup-scope.md),
[build-scope.md](build-scope.md), [knowledge-graph-model.md](knowledge-graph-model.md),
`skills/setup-mesh/` (`check_setup.py`, `survey_mesh.py`, `scaffold_domain.py`,
`check_references.py`, `SKILL.md`, templates), `skills/ingest-conversation/`
(`validate_placements.py`, `SKILL.md`, `templates/candidate.md`),
`skills/promote-candidate/` (`classify_candidates.py`, `SKILL.md`), `test-mesh/`, `README.md`,
`CLAUDE.md`, `prompts/structure-transcript.md`.

### v2.1 (2026-07-30) — `Task`, keyed `Persona`, `Workflow` creation targets

> **Superseded in part by v2.2.** `Task`, `Workflow.creates`, and `Workflow.via` were all
> deferred out of the schema on 2026-08-03 — the design is retained privately
> and may return as a future feature. The `Persona` and
> `Assumption` changes below remain live (the assumption's parent is now optional, per v2.2).
> Kept as the record of why they were added.

Prompted by reconciling this schema with the `ee-pm` plugin, which stores the same discovery
artifacts and disagreed with it in four places. Two of those disagreements were ee-pm trailing
an older convention and are fixed there; two were **gaps here**, fixed in this bump.

**Schema changes (all additive — no existing type, edge, or property changes meaning):**

| Change | Detail |
|---|---|
| Add type | `Task` — `TASK-NNNN`, Group B, **no parent** |
| Add edges | `Task`: `references`, `routed-to`, `rendered-on` |
| Extend | `creates` may target `Task`; `routed-to` may originate from `Task` |
| Add properties | `Workflow.creates`, `Workflow.via` (both optional) |
| Promote to required | `Workflow.system`, `Workflow.external_ref` (were "when external") |
| Widen | `Workflow.system` accepts `repo`; `external_ref` accepts a repo-relative path |
| Add properties | `Persona.slug` (**required**), `Persona.name` (**required**), `Persona.emoji` (optional) |
| Clarify | `Assumption`'s required parent is a `Solution`, **not** a full OST |

**Why `Task`.** `Story` was the only work artifact in the schema, so all non-dev work — run
the workshop, chase the DPA — had nowhere to go, and a `Todo` routed to a backlog landed as an
untyped line. Since `Story` is already a tracked Group-B type, tracking one kind of work and
not the other was arbitrary. `Task` is defined by the **absence** of a discovery parent.

**Why `Workflow.creates`.** `Workflow` said where work goes but not what it becomes there, so
one queue could not be distinguished from another. With `creates`, a `Todo` routed to a
`creates: Story` workflow is destined for a real story — ID, template, parent, backlog entry —
and a `creates: Task` workflow takes the rest. Several workflows per mesh is the intended
shape.

**Why the anti-shadow rule was restated.** It was written as "no mesh-native lists" and
implemented as a **checkbox-character check**. That test was wrong in both directions: it
blocked a repo-native backlog that is legitimately the single record of work, and it would
pass a genuine shadow copy written without checkboxes. The hazard is a **second source of
truth**, so the test is now "does this declare an owning system, and does its `external_ref`
resolve?" This is the seventh instance of the fail-open validator pattern this project keeps
finding — it reported a pass by checking the wrong thing.

**Why `Persona` gains required properties.** It was documented as an inert path-referenced
singleton, but `Story` references personas **by slug**, so the slug was already load-bearing
and a missing persona was already a dangling reference the schema did not describe. `emoji`
moves onto the persona so no separate slug→emoji legend has to be kept in sync.

**Not breaking, with one caveat.** Every change is additive. The caveat: `Workflow.system` and
`external_ref` become required, so a pre-v2.1 `Workflow` with neither is now invalid — which
is exactly the shadow-tracker case the rule targets, and the intended effect.

**Dependents to update:** [file-taxonomy.md](file-taxonomy.md) (assumption + persona +
`Task` storage, the setup-boundary invariant), [setup-scope.md](setup-scope.md),
`skills/setup-mesh/` (`check_setup.py`, `survey_mesh.py`, `check_references.py`, `SKILL.md`),
`skills/ingest-conversation/` (stage-3 routing on `creates`), `test-mesh/`, `CLAUDE.md`.

### v2.0 (2026-07-21) — the single-Hub collapse. **Breaking.**

The decision: **the AI Hub is the only place context lives.** Domain-specific context sits in a
domain folder *inside the Hub*, not in the code repo it describes. Code repos hold no context
and are unaware of the mesh. All Hub content — domain-specific included — is readable by
everyone.

**Schema changes (breaking):**

| Change | From | To |
|---|---|---|
| Rename | `Repo` | `Domain` |
| Rename | `RepoFact` | `DomainFact` |
| Remove | `mirrored-from` | — |
| Remove | `promoted-from` | — |
| Retarget | `applies-to` → `Repo` | `applies-to` → `Domain` |
| Retarget | `owned-by` → `Repo`/team | `owned-by` → team |
| IDs | repo-prefixed `payments-svc:OPP-0042` | domain-prefixed `payments:OPP-0042` |

**Everything else is deliberately untouched** — the three node groups, the discovery-artifact
shape and parent chain, `derives-from` provenance, the `Conversation` source rules, the
`state` tag, and every other row of the legal-edge matrix. This is a **narrow collapse, not a
redesign**: the type system was already correct about *what* it modelled, and wrong only in
asserting *where* things physically lived.

**Why the edges go rather than being deprecated.** `mirrored-from` and `promoted-from` both
encode "this node is a generated read-only copy of a node in another repo." With one repo,
they cannot have a valid instance — a deprecated-but-legal edge that can never be satisfied is
a fail-open trap of exactly the kind this project keeps finding: a validator would accept it
and check nothing.

**What this dissolves entirely:** the CI mirror, leaf→Hub promotion, the partitioned/uniform
access model, the promotion allow-list, and the whole class of bugs where **a repo-relative
reference stops meaning what it meant once it leaves its repo** (four documented instances,
one of them cross-domain data corruption). `technical/system-behavior.md` is unambiguous
because there is only one.

**Dependents updated:** [file-taxonomy.md](file-taxonomy.md),
[promotion-boundary.md](promotion-boundary.md), [setup-scope.md](setup-scope.md),
[ingestion-pipeline.md](ingestion-pipeline.md), `hub-leaf-meshing.md` (retired),
`skills/ingest-conversation/`, `skills/promote-candidate/`, `skills/setup-mesh/`,
`skills/promote-to-hub/` (deleted), `test-mesh/`, `CLAUDE.md`.

### v1.3 (2026-07-16) — `state: resolved`

> **Superseded by v2.2** — `state: resolved` is deferred with the workflow layer it served.
> The design is retained privately.

The `state` tag gains a third value for a candidate promoted **out of** the mesh rather than
into it: a `Todo` handed over to the Jira/Linear project its `Workflow` names. Minor bump — a
tag value, no type or edge touched.

**Why:** such a candidate is in neither existing state. Never `canonical` (no file exists for
it — the backlog lives in Jira), no longer `staging` (the decision is made). It is kept rather
than deleted so the `derives-from` chain survives: the ticket is the work, the candidate is
the record of where the work came from, and a Jira ticket cannot hold that.

Also documented here: **`promoted-from` is not the staging→canonical marker.** It is Hub↔leaf
snapshot provenance. Two unrelated things are called "promotion" in this system and the
vocabulary now says so explicitly.

**Dependents updated:** `skills/promote-candidate/`.

### v1.2 (2026-07-16) — `Workflow` properties and storage

> **Superseded by v2.2** — the whole `Workflow` layer is deferred. See
> The retained private design carries this storage rule and the finding that produced it.

`Workflow` gains `name` / `system` / `external_ref` and, in
[file-taxonomy.md](file-taxonomy.md), a physical home at `process/workflows/`. Minor bump: no
type added or removed, **no edge legality changed** — `routed-to` and `triggers` already
pointed at `Workflow`; they just pointed at something that could not exist.

**Why:** `Workflow` was a node type with no storage rule. Ingestion run 1 produced two `Todo`
chunks and could place neither, at *high* confidence — the agent knew what it wanted and the
taxonomy had nowhere to put it. `Requirement → triggers → Workflow` had the same hole and had
simply not been hit. The fix is storage plus the rule that a `Workflow` is normally a
**pointer to the external system that really runs the process**, so the mesh never becomes a
shadow issue-tracker.

**Dependents updated:** [file-taxonomy.md](file-taxonomy.md) (the storage rule),
`skills/ingest-conversation/SKILL.md` (stage 3 routing), `test-mesh/` (a real backlog
workflow to route to).

### v1.1 (2026-07-16) — `Conversation` source references

`Conversation` gains required `source_ref` / `source_kind` / `content_hash` properties. No
node type added or removed, no edge legality changed — the legal-edge matrix is untouched, so
nothing that routes or traverses the graph is affected.

**Why:** the `Conversation` node is what every ingested fact hangs off via `derives-from`.
Before this, it summarized its source without pointing at it, so provenance bottomed out in
a node the agent itself wrote — no good answer to "that's not what we said" six months on.
Now it points at the transcript in **its own datastore**, which is a better audit trail than
storing transcripts *and* keeps PII custody out of context-mesh.

**Dependents updated:** [ingestion-pipeline.md](ingestion-pipeline.md) (stage 1),
`skills/ingest-conversation/SKILL.md` (stage 1 + the checkpoint).

## Deliberately excluded (and why)

- `is-a` — there is no classification hierarchy among instances; the type system *is* the
  taxonomy backbone. (Per knowledge-graph-model.md.)
- `Artifact` as a node type — too broad; replaced by concrete Group-B/C types.
- `links-to`, `applies-across` — folded into `references` and `applies-to`.
- Heavyweight relationship modifiers (weights, qualified edges) — defer until querying
  demands them, per the dumb-substrate principle.
