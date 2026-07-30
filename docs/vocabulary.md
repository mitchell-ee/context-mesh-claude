# context-mesh — node & edge vocabulary (the schema)

Status: **LOCKED v2.1** (v1 2026-06-25; v1.1–v1.3 2026-07-16; v2.0 2026-07-21 — the
single-Hub collapse; **v2.1 2026-07-30 — `Task`, keyed `Persona`, `Workflow` creation
targets**, see Versioning). This is the controlled vocabulary — the type system of
the knowledge graph. It is the schema the rest of the system references:
[ingestion-pipeline.md](ingestion-pipeline.md) stages 2–3 classify into these types and
[file-taxonomy.md](file-taxonomy.md) stores them. Changes here ripple everywhere —
version-bump and update dependents.

Locked per the project backlog and the starter vocabulary in
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
| `Todo` | An action item. | backlog/queue |
| `DomainFact` | A fact specific to one domain — its code, quirks, conventions. | that domain's canonical context (Group C) |
| `OpenQuestion` | An undecided point needing a human decision. | resolves into one of the above |

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
(`payments:OPP-0042`). Most form the outcome→story traceability chain via `parent-of`;
`Task` (v2.1) is the deliberate exception — same ID treatment, no chain.

| Type | ID | Parent (via `parent-of`) |
|---|---|---|
| `Outcome` | `OUTCOME-NNNN` | — (top of tree) |
| `Opportunity` | `OPP-NNNN` | `Outcome` |
| `Solution` | `SOL-NNNN` | `Opportunity` |
| `Assumption` | `ASSUMPTION-NNNN` | `Solution` |
| `Story` | `STORY-NNNN` | `Solution` (and `Epic` within an iteration) |
| `Epic` | `EPIC-NNNN` | (groups `Story`s) |
| `Task` | `TASK-NNNN` | — (**none**; see below) |
| `Interview` | per-iteration | — (feeds synthesis) |

#### `Assumption` requires a `Solution`, not a tree (clarified v2.1, 2026-07-30)

An assumption is tested **against a solution**, so `parent-of` from `Solution` stays
**required**. What is *not* required is an `Outcome`/`Opportunity` above that solution. A team
doing assumption mapping without a full opportunity-solution tree is a legal, expected
configuration — the chain is satisfied as far up as it goes. The storage folder moved out of
`opportunity-solution-tree/` to match ([file-taxonomy.md](file-taxonomy.md)); the edge did not
change.

#### `Task` — work with no discovery lineage (added v2.1, 2026-07-30)

`Story` is dev work that traces to a `Solution`. `Task` is everything else the team must
actually do — run a workshop, chase a DPA, prepare a client readout. **It is defined by the
absence of a parent**: no `parent-of`, because there is no discovery chain above it. That
absence is the whole distinction; a `Task` that turns out to trace to a `Solution` was a
`Story` all along.

| Property | Required | Meaning |
|---|---|---|
| `id` | **yes** | `TASK-NNNN`, domain-prefixed like every Group-B ID. |
| `title` | **yes** | What is to be done. |

**Why a node type rather than leaving it outside the mesh.** `Story` is already a tracked
Group-B artifact with an ID and a storage rule, so the mesh already tracks work of one kind;
excluding the other kind would be arbitrary. The `Todo` analogy does not apply — `Todo` is a
**Group-A staging type** (an action item extracted from a conversation, awaiting routing),
while `Story` and `Task` are canonical artifacts. Different lifecycle layers.

**How it is tracked stays flexible.** A `Task` may live as a file in the mesh, or wholly in an
external system when the `Workflow` it is `routed-to` points outward. The node type does not
dictate the tracker — see `Workflow.creates` below.

### Group C — Canonical context & structural (singletons, **path-referenced**)
The slow foundation. One authored instance each; referenced by path.

| Type | Meaning |
|---|---|
| `ContextFile` | A canonical context file (business-context, coding-standards, etc.). |
| `Persona` | A customer/stakeholder persona. **Keyed by `slug`** — see below. |
| `Architecture` | Cross-cutting technical architecture. |
| `Domain` | A namespace within the Hub — one folder, holding all context about one thing. See below. |
| `Workflow` | A triggerable process (refinement, backlog routing). **Usually a pointer to an external system** — see below. |
| `Board` | An external visual surface (Miro / Claude Design) — view only, never canonical. |

#### `Domain` — the namespace node (replaces `Repo`, v2.0, 2026-07-21)

All context lives in the **AI Hub**, the one repo. A `Domain` is a **folder within it** holding
all context about one thing, and it is what `applies-to` targets — the answer to "what is this
context *about*."

| Property | Required | Meaning |
|---|---|---|
| `name` | **yes** | The folder name and the ID prefix (`payments` → `payments:OPP-0042`). |
| `about` | **yes** | What this domain covers, in a line. Declared in the index. |

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

#### `Workflow` — properties and storage (added v1.2, 2026-07-16; extended v2.1)

`Workflow` is the target of `routed-to` (from `Todo`) and `triggers` (from `Requirement`). It
had **no storage rule anywhere in the design** until v1.2 — the type system promised a
destination [file-taxonomy.md](file-taxonomy.md) never provided. `Todo` hit it first because
`routed-to → Workflow` is its only useful edge.

| Property | Required | Meaning |
|---|---|---|
| `name` | **yes** | The process: `backlog`, `refinement`, `triage`. |
| `system` | **yes** | What owns the queue: `jira`, `linear`, `github`, or **`repo`**. |
| `external_ref` | **yes** | Where it actually is — a URL/ID, or a **repo-relative path** when `system: repo`. |
| `creates` | no | The node type produced there: `Story`, `Task`, or absent. (v2.1) |
| `via` | no | **Non-normative** hint at the process that creates it. (v2.1) |

**Stored** one file per process under `process/workflows/` — at the Hub root (cross-team) or
within a domain (that team's own). Both legal; the index that lists it declares the owner.
Singletons, path-referenced — no chain runs between workflows.

**A `Workflow` is a pointer, not a container.** The backlog lives in Jira, or in a file this
repo owns; either way the `Workflow` file names it and says where. Routing a `Todo` there
means *identified and attributed*, **not filed** — filing stays a human act in the real
system.

##### The rule is single-source, not "no checkboxes" (corrected v2.1, 2026-07-30)

Through v2.0 this was stated as a prohibition on mesh-native lists, and the validators
implemented it by looking for **checkbox characters**. That was the wrong test. The hazard was
never the syntax; it is a **second source of truth** — a copy of a queue some other system
already owns, rotting from the day it is written.

A repo-native backlog that *is* the record of work is not a shadow of anything. So:

- `system: repo` is a **first-class value**, and `external_ref` may be a repo-relative path.
  The path **must resolve** — a dangling one is a real failure, and the one thing to check.
- A checkbox list under a declared, resolving owner is **fine**.
- A workflow declaring **no owning system at all** is the smell the rule was written for.

**`creates` — what the work becomes when it lands.** A `Workflow` says where work goes;
`creates` says what it turns into there. A `Todo` routed to a workflow with `creates: Story`
is destined for a real story — with an ID, a template, a parent `Solution`, and a place in the
backlog index — not a bare line of text. One with `creates: Task` becomes non-dev work with no
discovery lineage. Several workflows coexist in one mesh precisely so this distinction has
somewhere to live; `process/workflows/` already holds one file per process.

**`via` is deliberately non-normative.** It may name a skill, a runbook, a person — anything
that tells a human or agent *how* creation happens (`via: ee-pm:story-management`). It is a
hint, not a contract. Harness-agnosticism is a hard constraint of this project, so a validator
**must not fail on an unrecognized `via`**, and any tooling that does not understand one must
ignore it and proceed.

---

## Edge types

All edges are **directed and named**. `source —edge→ target`.

| Edge | Direction | Meaning |
|---|---|---|
| `derives-from` | Group-A node → `Conversation` | Provenance. Mandatory on every ingested node. |
| `references` | any → `Domain` / Group-B node | A soft mention/link (collapses old `references`+`links-to`). |
| `applies-to` | `Persona`/`Architecture`/`Knowledge`/`DomainFact` → `Domain` | This context governs that domain. Cardinality (one vs. many domains) is a property of the edge set, not a separate edge (old `applies-across` removed). |
| `parent-of` | Group-B → Group-B | The traceability chain (Outcome→Opp→Sol→Story; Epic→Story). Inverse of the aiviz `Parent X` frontmatter. |
| `triggers` | `Requirement` → `Workflow` | Routes a requirement into a process. |
| `creates` | `Requirement`/`Workflow` → `Story`/`Epic`/`Task` | Produces a new artifact. |
| `routed-to` | `Todo`/`Task` → `Workflow` (backlog/queue) | Where an action item goes. |
| `contradicts` | any → any | This node conflicts with that one. Flagged for human, never auto-resolved. |
| `rendered-on` | Group-B node → `Board` | An optional visual view. Dropping it loses no context. |
| `owned-by` | any → team | The single authoring owner. Declared, not inferred from location. |
| `loaded-by` | `ContextFile` → index/loader | Progressive-disclosure: when this file loads. |

---

## Legal-edge matrix (the routing logic)

For each **source** node type, the edges it may legally originate. This *is* the routing
logic the ingestion agent enforces at propose-time (stage 3) — an edge not in this matrix
is a validation error.

| Source type | Legal outgoing edges |
|---|---|
| `Conversation` | `references` |
| `Knowledge` | `derives-from`, `applies-to`, `references`, `contradicts` |
| `Requirement` | `derives-from`, `triggers`, `creates`, `references`, `contradicts` |
| `Todo` | `derives-from`, `routed-to`, `references` |
| `DomainFact` | `derives-from`, `applies-to`, `references`, `contradicts` |
| `OpenQuestion` | `derives-from`, `references` |
| `Outcome` | `parent-of`, `rendered-on` |
| `Opportunity` | `parent-of`, `references`, `rendered-on` |
| `Solution` | `parent-of`, `references`, `rendered-on` |
| `Assumption` | `references`, `rendered-on` |
| `Story` | `parent-of`, `references`, `rendered-on` |
| `Epic` | `parent-of`, `rendered-on` |
| `Task` | `references`, `routed-to`, `rendered-on` (**no `parent-of`** — that is the point) |
| `Interview` | `references` |
| `ContextFile` | `applies-to`, `references`, `loaded-by`, `owned-by` |
| `Persona` | `applies-to`, `references` |
| `Architecture` | `applies-to`, `references` |
| `Workflow` | `creates` |
| `Domain` | `owned-by` |
| `Board` | (none — terminal; only a `rendered-on` target) |

Reading the matrix as routing: a `Requirement` chunk can `trigger` a `Workflow` and
`create` a `Story` — so the ingestion agent proposes exactly those placements. A `Todo` can
only be `routed-to` a queue — and the queue's `creates` property then decides whether it
becomes a `Story` or a `Task`, which is how one edge serves both kinds of work. A `Knowledge`
chunk `applies-to` a domain and may `contradict` existing context (flagging a conflict). This
is the type system "doing real work as a schema," as knowledge-graph-model.md put it.

---

## Tags (not edges)

Two boolean/enum tags ride on nodes; they are not relationships:
- `decided` | `undecided` — drives where in staging a chunk sits (ingestion stage 2).
- `state: staging | canonical | resolved` — promotion lifecycle position.

### `state: resolved` (added v1.3, 2026-07-16)

A candidate that has been **promoted, but not into the mesh**. Specifically: a `Todo` handed
over to the external system its `Workflow` names (Jira, Linear).

It exists because such a candidate is in neither of the other states. It never becomes
`canonical` — there is no file for it, since the backlog lives in Jira
([workflow-is-a-pointer](file-taxonomy.md#workflows--where-a-routable-process-lives-added-2026-07-16)) —
but it is no longer `staging`, because the decision has been made.

**The candidate is kept, not deleted.** It carries the `derives-from` chain back to the
`Conversation` — what was said, who raised it, which meeting it came from. **A Jira ticket
cannot hold that**, and that provenance is precisely what this project exists to preserve.
The ticket is the work; the candidate is the record of where the work came from.

A `resolved` candidate records `resolved_to` (the external reference, once the human has
filed it and says so) and stays put.

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

This vocabulary is **v2.1**. Adding a type is a minor bump; changing an edge's legality or
removing a type is a major bump and requires updating every dependent doc. **Adding a
required property to an existing type is a minor bump** — it constrains what a valid
instance looks like without changing what the graph traverses. (This case was unspecified
until v1.1 needed it.) The lock exists so ingestion and storage agree on one schema.

### v2.1 (2026-07-30) — `Task`, keyed `Persona`, `Workflow` creation targets

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
