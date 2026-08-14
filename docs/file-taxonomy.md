# context-mesh — file taxonomy

Status: design note. Written 2026-06-25; reframed 2026-07-16; **restructured 2026-07-21 by the
[single-Hub collapse](vocabulary.md#v20-2026-07-21--the-single-hub-collapse)**; **updated
2026-08-03 for vocabulary v2.2** — domains moved under `domains/`, and the workflow layer
(`Todo`/`Task`/`Workflow`, `process/workflows/`) deferred. This is the
"where does any piece of context live" layout this project is built around.

**Read the manifest split first** ([below](#the-manifest-split-what-varies-per-implementation)):
the file *lists* here are a good default, not a specification. They are expected to be
tweaked per implementation. The *structure* around them — the layers, the discovery-artifact
shape, staging — is framework and does not vary.

## Everything lives in the AI Hub

**One repo holds all context.** Context about a specific thing lives in a **domain folder**
inside the Hub. All Hub content, domain-specific included, is readable by everyone.

The invariant is **one home per fact, authored in exactly one place, never mirrored**. Two
things around it vary per implementation, and neither changes the structure:

**Where the Hub sits.** It may be its own repo, or it may *be* the code repo:

| | The Hub is | Code repos |
|---|---|---|
| **Multi-repo product** | usually a repo of its own | hold no context; unaware of the mesh |
| **Monorepo** | the code repo — Hub root *is* repo root | there is only the one, and it holds the mesh |

In a monorepo, `context-index.md` sits beside `package.json`, and **Hub-relative and
repo-relative are the same thing** — one path convention, no offset to reason about. Nothing in
the structure or the tooling changes; the mesh does not detect which shape it is in, and code
sitting in the Hub is not a misconfiguration.

**Whether domains exist at all.** They are optional:

```
hub/
  context-index.md    # the root loader
  product/            # cross-cutting, applies to everybody
  technical/
  process/
  governance/
  staging/            # cross-cutting undecided material
  domains/            # OPTIONAL — every domain lives here, and nowhere else
    <domain>/         # everything about one domain
      context-index.md
      product/
      technical/
      staging/
```

**A Hub with no `domains/` directory is a complete mesh**, not an unfinished one — its context
is entirely cross-cutting, and the root holds all of it. Tooling must never report zero domains
as a gap.

**The two are independent.** A multi-repo product will probably carve domains; a monorepo
probably won't, having one thing to describe; either may do the opposite. Do not infer the
domain layer from the repo topology, or either from what a directory contains.

A **domain** is a namespace, not necessarily a code repository. It may map 1:1 to one repo, span
several, or be finer than one. **Which domains exist — including none — is manifest**
(per-engagement config); **that domains, where they exist, own their context exclusively is
framework**. See [vocabulary.md](vocabulary.md) `Domain`.

**A domain is exactly a directory under `domains/`** (v2.2, 2026-08-03). This is a *declaration
by location*, not a heuristic: tooling never infers domain-ness from what a folder contains.
Before v2.2 domains sat beside the cross-cutting folders at the root and had to be detected —
which misfired in the first third-party run, reporting a `docs/product/` research folder as a
domain while missing the real one. A folder named `product/` at the root is the cross-cutting
product tree; a folder named `product/` under `domains/checkout/` is that domain's. Nothing
else needs deciding.

## How to read this

Every file sits on two axes, plus two attributes that decide its storage mechanics:

- **Scope** — *Cross-cutting* (at the Hub root; governs everybody) vs. *Domain* (inside one
  domain folder; about that thing). **This replaces the old central-vs-repo-local axis**, which
  described *which repo a file sat in* back when there were many. The question is now "what is
  this about," not "where does it live" — everything lives in the Hub.
- **About** — Product / Feature / Technical / Process & Governance.
- **State** — *Canonical* (decided fact) vs. *Staging* (undecided; awaits promotion).
- **Cardinality** — *Singleton* (one-off; referenced by **path**) vs. *Multi-sibling*
  (many instances of a type; referenced by **ID** — see [[id-vs-path-references]] /
  the path-vs-ID rule). This is what determines whether a thing is a file or a folder-of-files.

Two source models fed this draft, one per side of the cross-cutting/domain split:
- A real engagement's canonical context list (a legacy-platform migration) — **generalized
  here**, engagement specifics stripped. → the *cross-cutting, durable* side.
- The aiviz/Crumbs product-discovery structure (OST, iterations, stories) — a working
  instance of PM-owned, multi-sibling, ID'd artifacts. → the *domain, discovery* side.

The design goal is **mutual exclusivity**: for any fact, exactly one obvious home.

---

## The manifest split: what varies per implementation

The context-file list is **not a design decision to get right once**. It changes from
project to project — a migration engagement, a greenfield product, and a platform team all
want different central files. Deciding on a defensible starting set and tweaking it per
implementation is the correct move; trying to find the one true list is not.

So the taxonomy splits in two:

| | What it is | Varies? |
|---|---|---|
| **Manifest** | The **file lists**: which Layer A cross-cutting files exist, and which Layer B per-domain singletons exist — their names, and what each is about. **Plus which domains exist.** | **Yes** — per implementation |
| **Framework** | The **structure**: the layers and their semantics, the two axes, the discovery-artifact shape, staging, and the [vocabulary](vocabulary.md) | **No** — fixed |

### What the manifest can vary

- **Add** a file the framework never anticipated (`technical/legacy-runtime-topology.md` for a
  migration engagement).
- **Carve the domains** — one per code repo, one per business domain, a mix, or **none at all**
  (a monorepo usually has one thing to describe, so all its context is cross-cutting). The
  framework says that domains, where they exist, own their context exclusively; *which* ones
  exist, including zero, is this client's call.
- **Drop** a file this org has no use for (a team with no formal design practice drops
  `product/design-principles.md`).
- **Rename** to match house vocabulary (`technical/nfr.md` → `technical/slos.md`).
- **Split or merge** where progressive disclosure demands it — e.g. splitting
  `governance/data-handling.md` once a given org's content actually grows too broad.
  Formerly an open question here; the manifest answers it per implementation.

### What the manifest cannot vary

- **The vocabulary** ([vocabulary.md](vocabulary.md), locked v2.0) — node types, edge types,
  and the legal-edge matrix. This is the routing logic; ingestion validates against it.
  A per-client type system means a per-client ingestion agent.
- **The discovery-artifact shape** (Layer B, below) — `opportunity-solution-tree/` and
  `iterations/`, the 4-digit IDs, the `Story → Solution → Opportunity → Outcome` parent
  chain. This is not a file list; it is the **physical instantiation of the vocabulary's
  discovery node types**. Making it configurable would decouple storage from the type
  system and break the traceability chain the graph depends on.
- **The layer semantics** — what "cross-cutting canonical" / "domain" / "staging" *mean*, and
  the ownership and promotion rules that follow. See
  [promotion-boundary.md](promotion-boundary.md).
- **Staging mechanics** (Layer C) — the inbox → candidates → promotion flow.

### Why the line falls there

The manifest covers **singletons referenced by path**; the framework covers **everything
the graph reasons over**. A path-referenced singleton is inert as far as the type system is
concerned — the index/loader lists it, an agent loads it, nothing validates its name. Adding
or renaming one costs nothing structurally. Multi-sibling ID'd artifacts are the opposite:
their folders, IDs, and parent chains are what the edges traverse. Change those and the
routing logic changes with them.

The lists below are therefore the **default manifest** — a "pretty good" starting set,
generalized from one real engagement's context list plus the aiviz discovery structure.
Ship it, then tweak in place per client.

---

## Layer A — Cross-cutting canonical context (Hub root) — *manifest-driven*

Shared by everybody, changes rarely. Lives at the **Hub root**, outside any domain folder.
Mostly **singletons referenced by path**. These are the "5–7 foundational files to define
before the conversations" from the seeding design work, generalized from a real engagement's
context-file list. Each is one small file (split a section out into its own file only when it
grows enough to hurt progressive disclosure).

> **This list is the default manifest, not a specification.** Add, drop, rename, split, and
> merge per implementation. The tables' "Generalized from" column records the kind of source
> each default came from, so a new engagement can see what was generalized away and put its
> own specifics back.
>
> **Every row below is optional** (clarified 2026-07-30). Not "optional in principle, expected
> in practice" — genuinely optional. Nothing validates that any of these exist:
> `check_setup.py` deliberately does not check for manifest files, because *a repo missing
> `design-principles.md` isn't broken; it's a repo without design principles.* A team that
> keeps four files and a team that keeps twenty are both correctly configured.
>
> **Read this list as a vocabulary of homes, not a checklist.** Its job is to answer "if we
> *do* have this kind of context, where does it go?" so that two teams who both have personas
> put them in the same place. It is not a claim about which kinds a team ought to have. Any
> real practice's list will look substantially different from this one — these defaults were
> generalized from **one** engagement plus the [ee-pm](https://github.com/mitchell-ee/ee-pm)
> discovery practice, and both are particular.

### Product (cross-cutting)
| File | About | Generalized from |
|---|---|---|
| `product/business-context.md` | Why this product/system exists; business problems solved; who depends on it; value delivered | "Business Context & Purpose" |
| `product/personas/{slug}.md` | Customer/stakeholder personas — **one file each**, keyed by `slug`. See [Personas](#personas--one-file-each-keyed-by-slug) below: this is the one Layer-A entry that is *framework*, not manifest. | — |
| `product/design-principles.md` | Product values and how tradeoffs get resolved | aiviz `principles.md`, ee-pm `principles.md` |
| `product/glossary.md` | Domain terms, shared vocabulary | aiviz `glossary.md` |
| `product/product-strategy.md` | Where the product is going: direction, bets, what it will and won't become | ee-pm |
| `product/product-as-built.md` | What the product actually does **today** — existing behavior and constraints, from the user's view. *Product*, not technical: `technical/system-behavior.md` covers runtime behavior per domain. | ee-pm |

**Practice-dependent product context.** These exist only if a team runs a discovery practice
that produces them. Listed so that a team who *has* them has a declared home — not as a gap
for a team who doesn't.

| File | About | Generalized from |
|---|---|---|
| `product/screens/{slug}.md` | Baseline specs for screens the product already has — what exists today, used to ground a new design against it rather than redesigning around it | ee-pm `claude-design` |
| `product/journey-maps/{slug}.md` | Key user workflows: critical moments, friction points. One file per journey — same progressive-disclosure reasoning as personas | ee-pm `framework-setup` |
| `product/competitive-analysis.md` | Competitors and alternatives; what they do well; market gaps | ee-pm `framework-setup` |
| `product/use-cases.md` | Primary scenarios, edge cases that must be handled, what's explicitly out of scope | ee-pm `framework-setup` |
| `product/constraints.md` | Technical, business, and regulatory constraints the product operates under | ee-pm `framework-setup` |

### Technical (cross-cutting)
| File | About | Generalized from |
|---|---|---|
| `technical/target-architecture.md` | Target-state architecture, structure, deployment, observability | "Target Architecture" |
| `technical/integration-map.md` | Cross-system dependencies: APIs, data stores, queues, feeds, jobs | "Dependency & Integration Map" |
| `technical/api-and-interface-standards.md` | How APIs and interfaces should look — conventions, contracts, patterns | (generalized) |
| `technical/coding-standards.md` | Language/framework/style conventions, patterns, anti-patterns | "Coding Standards" |
| `technical/testing-standards.md` | Test types, coverage thresholds, test-data, CI integration | "Testing Standards" |
| `technical/nfr.md` | Non-functional requirements: performance, SLAs, throughput, scalability | "Non-Functional Requirements" |

### Process & Governance (cross-cutting)
| File | About | Generalized from |
|---|---|---|
| `process/ways-of-working.md` | End-to-end workflow, rituals, handoffs (ticket → … → deploy) | "Ways of Working Overview" |
| `process/definition-of-done.md` | Shared "complete" criteria; acceptance-criteria pattern | "Definition of Done" + "AC Pattern" |
| `process/review-and-release.md` | Review/approval model, environments, promotion path, rollback | "Review & Approval" + "Release & Environment Flow" |
| `governance/data-handling.md` | Data classification, residency/sovereignty, encryption, network security | split from "Security, Data & Compliance" |
| `governance/access-control.md` | AuthN/AuthZ, identity, RBAC, service accounts, SSO/MFA | split from "Security, Data & Compliance" |
| `governance/compliance.md` | Regulatory framework, audit, logging, retention, incident response | split from "Security, Data & Compliance" |
| `governance/ai-policy.md` | AI usage guidelines, AI-specific data rules, human-review triggers | "AI Usage Guidelines" + "AI-Specific Data Policies" |
| `capabilities/skill-governance.md` | How skills/agents are proposed, tested, approved, versioned, retired; context-update policy | "Skill Lifecycle" + "Context Update Policy" |

> **Why these and not the source list's several dozen sections:** the source list mixes the
> durable taxonomy with one engagement's specifics (legacy runtime topology, target-platform
> details, migration playbook, coexistence routing). Those are *domain-local technical context
> for that migration*, not the central canonical list. The generalization keeps the durable
> categories and pushes engagement specifics down to Layer B.

---

## Personas — one file each, keyed by `slug` (revised 2026-07-30) — *framework, fixed*

Every other Layer-A entry is manifest: a path-referenced singleton the loader lists and
nothing validates. **`Persona` is the exception**, and it always was — `Story` files name
personas **by slug**, so the slug is traversed, and a story naming a persona that doesn't
exist is a dangling reference. That puts personas on the framework side of the line this
document draws at [Why the line falls there](#why-the-line-falls-there): they are *not* inert
to the type system.

```
product/personas/
  first-time-buyer.md
  repeat-buyer.md
```

```yaml
---
type: Persona
slug: first-time-buyer
name: First-time buyer
emoji: 🧭        # optional; board rendering only
---
```

**One file per persona, and no legend file.** The prior default (`product/personas.md` — a
slug legend plus one section each) was carried over from aiviz and loses twice:

- **Progressive disclosure.** Real persona documents run to hundreds of lines. Merged into one
  file, loading any persona means loading all of them — against one of this project's two
  stated principles. Separate files also give routing a precise target: an ingested fact about
  one persona lands in that persona's file, not in a section of a shared one.
- **A legend is a second source of truth.** A slug→emoji table living apart from the personas
  goes stale, and detecting the staleness needs machinery that exists *only because the table
  exists*. With `emoji` on the persona, the failure mode becomes "persona file missing" — real,
  actionable, and checkable — instead of "legend is out of date."

Surfaces that need the whole set (a Miro story-map legend, say) **derive** it by reading the
files. Derived views are fine; a stored second copy is not.

> **This overrides the manifest's split/merge freedom for this one entry.** The manifest may
> normally split or merge files per implementation. Personas may not be merged back into a
> single file, because the slug is a traversed key rather than a heading.

---

## Workflows — deferred, no longer part of the taxonomy (v2.2, 2026-08-03)

`process/workflows/` held one file per routable process, and `Todo` routed action items into
it. **The whole layer is deferred** — the mesh holds context, and a queue is the work rather
than context about it. Nothing in the mesh stores, types, or routes work items now.

The complete design — the `Workflow` property table, the pointer-not-container rule, the
`system: repo` case, `creates`/`via`, the template, and the findings that produced all of it —
is retained privately and may return as a future feature.

**What this means for authoring:** a conversation that produces an action item still produces
one. Ingestion reports it as out of scope rather than placing it, and the human takes it
wherever their team actually tracks work. The mesh does not need to know where that is.

---

## Layer B — Domain context (in each domain folder)

Specific to one domain — its codebase, its team. Lives at `domains/<domain>/` **inside the
Hub**, using the **same layout as the Hub root**, so a path means the same thing at either
level.

> **Changed 2026-07-21.** Layer B used to live in the code repo and be **mirrored to the Hub by
> CI on merge to main**, with the leaf authoritative and the Hub copy read-only. There is no
> mirror and no second copy: the file a developer edits **is** the canonical file. Code repos
> hold no context. See the [single-Hub collapse](vocabulary.md#v20-2026-07-21--the-single-hub-collapse).

**Layer B straddles the manifest split** — its two halves fall on opposite sides:
the per-domain singleton list is manifest, the discovery-artifact structure is framework.

### Per-domain canonical (singletons, path-referenced) — *manifest-driven*

Same rules as Layer A: this list is a default. Add, drop, or rename per implementation.

| File | About |
|---|---|
| `technical/repo-overview.md` | What this domain is and does; its place in the system |
| `technical/system-behavior.md` | What this service does technically: flows, transactions, orchestration |
| `technical/runtime-architecture.md` | This domain's runtime topology (engagement-specific architecture lands here, not at the root) |
| `technical/legacy-notes.md` | Undocumented behaviors, quirks, tribal knowledge |
| `technical/local-conventions.md` | Domain-specific deviations from the cross-cutting standards |

### PM-owned discovery artifacts (multi-sibling → **ID'd**, the aiviz model) — *framework, fixed*

These are the product-management working artifacts. They are multi-instance, tracked,
and cross-referenced — so they get **IDs**, not path-only references. They live in the owning
**domain folder** (PMs own their own OSTs, discovery, stories), not at the Hub root.

> **Not manifest-configurable.** Unlike the file lists above, this structure is fixed. The
> folders, ID formats, and parent chain are the physical instantiation of the vocabulary's
> discovery node types (`Outcome`, `Opportunity`, `Solution`, `Assumption`, `Story`, `Epic`,
> `Interview`) and the `parent-of` edge — they are what the graph traverses, not inert files
> the loader happens to list. An implementation that doesn't do continuous discovery simply
> leaves these folders empty; it does not redefine them.

> **No `context/` layer.** These hang directly off `product/`
> (`product/opportunity-solution-tree/`, `product/iterations/`), not under an intermediate
> `product/context/` (the aiviz path is dropped). This keeps the domain layout identical to the
> Hub root's: every path is `product/<thing>` and means the same thing at either level. The
> cross-iteration-vs-iteration distinction `context/` used to mark is already carried by the
> folder names (`opportunity-solution-tree/` is the cross-iteration state; `iterations/` is the
> per-cycle work).
>
> **Shared `product/` namespace.** Cross-cutting context (`product/personas/`) and
> per-domain discovery artifacts share the `product/` namespace. Whether a given `product/…`
> file is cross-cutting or domain-scoped is answered by **whether it sits at the root or inside
> a domain folder** — not by the path shape. Domain-prefixing keeps IDs globally unique
> (`payments:OPP-0001`).

Product-level (spans iterations), under `product/opportunity-solution-tree/`:

All non-singleton artifact IDs are **4-digit, zero-padded** (`0000`–`9999`) to support
very large, long-lived projects without exhausting the number space. (aiviz uses 2–3
digits; context-mesh standardizes on 4 across every multi-sibling type for headroom and
consistency.) Combined with the domain prefix, a full ID is e.g. `payments:OPP-0042`.

**`0000` is legal** (settled 2026-08-03). The range used to start at `0001`, which made a
deliberately zero-indexed artifact — `EPIC-0000`, numbered to signal *"this precedes
everything"* — out of spec for a reason nobody had decided on. Zero is a useful signal and
costs nothing, so it is in range. Numbering otherwise starts at `0001` by convention; reserve
`0000` for the foundational-artifact meaning rather than using it as an ordinary first item.

| Artifact | Folder | ID format |
|---|---|---|
| Outcome | `outcomes/outcome-NNNN-slug.md` | `OUTCOME-NNNN` |
| Opportunity | `opportunities/opportunity-NNNN-slug.md` | `OPP-NNNN` (frontmatter: `Parent Outcome`) |
| Solution | `solutions/solution-NNNN-slug.md` | `SOL-NNNN` (frontmatter: `Parent Opportunity`) |

Assumptions sit **beside** the tree, not inside it (moved 2026-07-30):

| Artifact | Folder | ID format |
|---|---|---|
| Assumption test | `product/assumptions/assumption-NNNN-slug.md` | `ASSUMPTION-NNNN` (frontmatter: `Parent Solution`, **optional** — see below) |
| Assumption map | `product/assumption-maps/SOL-NNNN-slug/miro-metadata.json` | sidecar; see [board-sidecars.md](board-sidecars.md) |

**Why they moved out of `opportunity-solution-tree/`.** An assumption is usually tested
**against a solution**, but a team can map assumptions for candidate solutions without having
built a full tree, and that is a legal, expected configuration; nesting the folder inside
`opportunity-solution-tree/` made such a project carry a tree-shaped directory containing only
assumptions. The chain is satisfied as far up as it goes.

### No parent is required, anywhere (revised 2026-08-03, vocabulary v2.2)

This table marked `Parent Solution` **required** on assumptions, and ee-pm enforced it.
**That was a mistake.** A parentless `Assumption` is legal, and so is a parentless `Story`.

The case that settled it: four bets whose operative content was *which solutions not to design
yet* — "defer the student home surface until students have been interviewed." An assumption
that constrains **whether to build anything** cannot have a parent solution, because the tree
deliberately has none. Requiring one left it with no legal home, contradicting this document's
own "satisfied as far up as it goes" rationale one paragraph earlier.

**Prefer an explicit absence over a blank field:**

```yaml
parent: none
parent-rationale: constrains whether to build at all; no solution exists to hang it from
```

A blank or missing key reads as *"not filled in yet."* `parent: none` plus a reason says
*"this genuinely has no discovery lineage"* — a **finding**, not an omission, and the
difference matters when someone later asks whether the tree is incomplete.

**This is a documentation and ee-pm change, not a walker change.** `check_references.py:137`
only verifies that a *named* parent resolves; a file with no `parent-*` key emits no edge and
already could not fail. The requirement lived only in this table and in ee-pm's
`assumption-map` enforcement.

> **`Task` had a storage row here through v2.1** — `product/tasks/task-NNNN-slug.md`, no
> parent frontmatter — and is deferred with the rest of the workflow layer. The design is retained privately
> and may return as a future feature. With parents now optional,
> a restoration must first re-establish what distinguishes a `Task` from a parentless `Story`.

Iteration-scoped, under `product/iterations/{YYYY-MM-DD-slug}/`:

| Artifact | Location | Notes |
|---|---|---|
| Interview | `interviews/{persona}-NNNN-name.md` | feeds synthesis |
| Synthesis | `synthesis.md` | singleton per iteration |
| Story | `stories/story-NNNN-slug.md` | `STORY-NNNN`; links `Opportunity`/`Solution`/`Epic` |
| Epic | `epics/epic-NNNN-slug.md` | `EPIC-NNNN`; only when story count trips the threshold |
| Story map | `story-maps/story-map-vN.md` | activity × release-slice grid |
| Decisions log | `decisions.md` | append-only |

Traceability chain (all via ID frontmatter): `Story → Solution → Opportunity → Outcome`,
and within an iteration `Story → Epic`. `Assumption → Solution` hangs off the same chain. This
is the typed-edge graph from [knowledge-graph-model.md](knowledge-graph-model.md),
instantiated.

The chain is satisfied **as far up as it goes**, and every link in it is optional — a solution
with no opportunity above it is legal, and so is a story or assumption with no parent at all
(see above). What the chain describes is lineage where lineage exists, not a completeness
requirement.

---

## Layer C — Staging (undecided material, at the root and per-domain) — *framework, fixed*

Where conversation ingestion drops things that are **not yet decided** — speculation,
feature requests, ideation, unrouted facts — separate from canonical context, awaiting a
human **promote** decision. aiviz already runs a working instance of this: the OST
`inbox/` holds candidate opportunities from discovery until a PM promotes them into the
tree (`promote-from-inbox`).

| File / folder | Purpose |
|---|---|
| `staging/inbox/{YYYY-MM-DD}-{source}.md` | Distilled chunks from a conversation, pre-routing |
| `staging/candidates/` | Proposed nodes/edges awaiting human validation (the OST-`inbox` generalization) |
| `staging/open-questions.md` | Unresolved decisions surfaced but not yet answered |

Staging mirrors the canonical structure: a candidate destined for `product/` waits in
staging tagged for `product/`.

**Promotion is a merge, not a move** (corrected 2026-07-16, on building
`skills/promote-candidate/` against ten real candidates). The candidate's claim lands *in a
section of an existing document*; the candidate itself **stays in staging**, marked
`state: canonical`, as the audit trail carrying `derives-from` back to the conversation. The
context file states the fact; the candidate records how we know it. Nothing is deleted, and
nothing literally moves.

Nor is promotion one verb — an `OpenQuestion` resolves into another type before it can promote
at all, and a candidate contradicting its target stops for a human. See
[ingestion-pipeline.md](ingestion-pipeline.md#separate-step--promotion-built-2026-07-16-skillspromote-candidate).

---

## Cross-cutting: the index / loader

The Hub carries one **index/loader** file at its root, and one per domain folder, listing every
context file and **when to load it** — the progressive-disclosure contract. This is what
makes path references navigable without IDs. Suggested: `context-index.md` (or whatever
the harness reads). It is the only file an agent must read first.

**The index is where the manifest lands.** The manifest says which singletons this
implementation has; the index lists them with their load conditions. Any tool that
scaffolds a mesh reads the manifest and writes the index — which is why varying the file
lists costs nothing structurally: the index absorbs the variance, and every consumer reads
the index rather than assuming a file list.

**The index *is* the manifest** (settled 2026-07-16, see [build-scope.md](build-scope.md)).
There is no separate config file: one authored index declares the file list, feeds
the ingestion agent's routing, and states the load conditions. A second authored copy would
only drift.

The **root index additionally declares which domains exist** — the one piece of mesh-wide
manifest that is not a file list.

---

## Resolved (2026-07-16)

- **The context-file list is per-implementation config, not a design decision.** File lists
  (Layer A; Layer B singletons) are a **manifest**; structure (vocabulary, discovery shape,
  layers, staging) is **framework**. See [the manifest split](#the-manifest-split-what-varies-per-implementation)
  above. This retires "lock the foundational file list" as a blocker — ship a good default,
  tweak in place per client.
- **Is `governance/data-handling.md` too broad to split further?** Dissolved by the
  manifest: splitting is a per-implementation call, made when a given org's data-handling
  content actually grows enough to hurt progressive disclosure. No global answer needed.
- **Manifest form — the index/loader IS the manifest.** One authored file per repo, serving
  three roles at once: the manifest (what files this implementation has), the ingestion
  agent's routing input, and the progressive-disclosure contract. No separate
  `mesh-manifest.yml` — it would be a second copy of the same list, and two *authored* copies
  drift. Settled while scoping the build — see [build-scope.md](build-scope.md).

## Resolved (2026-07-21) — the single-Hub collapse

- **Where domain-specific context lives: the Hub, in a domain folder.** Not in a *separate* code
  repo that the mesh does not hold. This replaced the central-vs-repo-local axis with a
  cross-cutting-vs-domain one — a question about *what context is about*, not *which repo it
  sits in*.
- **Which domains exist is manifest**, alongside the file lists; *that* domains, where they
  exist, own their context exclusively is framework.
- **Dissolved with the collapse:** the CI mirror (Layer B is authored where it lives, not
  copied), leaf→Hub promotion of discovery artifacts, the partitioned/uniform access model, the
  promotion allow-list, and the mono-vs-multi-repo question (there is one repo).

> **Clarified 2026-08-13 — two things this section was read as saying, and doesn't.**
>
> "Code repos hold no context and are unaware of the mesh" described the *seeding client*, which
> has ~100 microservice repos and a Hub of its own. It was written as though it were framework,
> and it isn't: it is what the invariant (**one home per fact, never mirrored**) looks like
> *when the Hub is a separate repo*. **In a monorepo the Hub root is the repo root**, code and
> context sit in one repo, and the invariant holds unchanged. The pre-collapse design had
> already worked this out — mono-repo and multi-repo were held to be *the same model, differing
> by exactly one path segment* — and the collapse resolving that "into the only case" meant the
> monorepo branch is the **only** branch, not that monorepos were ruled out.
>
> Separately: **domains are optional**, and their absence is independent of repo topology. A
> monorepo usually has one thing to describe, so all of its context is cross-cutting and it has
> no `domains/` at all. That is a complete mesh. Tooling that treats zero domains as an
> unfinished state is wrong — `survey_mesh.py` did, and was fixed.

## Resolved (2026-06-25)

- **Security/compliance file split** into `governance/data-handling.md`,
  `governance/access-control.md`, `governance/compliance.md` for progressive disclosure
  (reflected in Layer A above).
- **Per-feature requirements** are covered by the Opportunity → Solution → Story chain —
  a "feature" is a Solution (or an Epic grouping Stories); its requirements are the Story
  acceptance criteria. No separate per-feature file (would duplicate and break mutual
  exclusivity).
- **Visual-board sidecars** — optional `rendered-on` attachments to their parent node;
  never canonical. See [board-sidecars.md](board-sidecars.md).

## Still open

- **How domain ownership is declared.** Repo boundaries used to make "authored in exactly one
  place" structurally true; in one Hub it is true by construction, but *which team owns which
  domain* is now a declaration (`owned-by`, CODEOWNERS) rather than a filesystem fact. See
  [promotion-boundary.md](promotion-boundary.md).

(**Resolved by the collapse, formerly open here:** the seeding client's access model, and where
the promotion allow-list lives — there is no allow-list. The staleness gate and its "material
change" question were already dissolved.)
