# The vocabulary: node and edge types

**What this is.** The list of things context-mesh can store, and the relationships it can record
between them. Ingestion classifies every fact into one of these types before it can be routed
anywhere.

**What you get from reading it.** You will know what kinds of context the system recognizes, how
they relate, and why a placement can be rejected as invalid.

**Who needs it.** Read the type tables if you are writing context by hand or wondering why
something was typed a certain way. The skills read this file to classify and validate; the
[legal-edge matrix](#legal-edge-matrix) is the part they enforce.

---

## Why there is a vocabulary at all

Without a fixed set of types, "route this fact to the right place" has no meaning — every
conversation would invent its own categories and nothing could check the result.

The vocabulary makes three things possible:

1. **Routing.** A fact's type determines where it may live. A `DomainFact` goes in a domain's
   technical context; an `OpenQuestion` cannot go into canonical context at all.
2. **Validation.** Relationships are checked against a fixed matrix. An edge that is not legal
   for a type is a validation error, caught before anything is written.
3. **Traversal.** Discovery artifacts form a chain — a story belongs to a solution, which
   belongs to an opportunity. Tooling can follow that chain and check it still resolves.

The types are deliberately few. Every addition costs routing surface and needs a storage rule to
match; a type the schema promises a home for, but storage never provides, is a hole every layer
assumes the one below has filled.

---

## Node types

Three groups by lifecycle role. **The group determines which edges are legal.**

### Group A — Ingested knowledge

What a conversation produces. Every one carries `derives-from` pointing at its `Conversation`.

| Type | Meaning |
|---|---|
| `Conversation` | The provenance root — a meeting, a session. Every ingested fact hangs off one. |
| `Knowledge` | A durable, cross-cutting fact. |
| `DomainFact` | A fact about one domain — how a service behaves, a constraint it has. |
| `Requirement` | A capability or constraint the product must satisfy. |
| `OpenQuestion` | Something undecided. **Cannot promote** — it must be resolved into another type first. |

### Group B — Discovery artifacts

Product-discovery work. **Many siblings, each with an ID**, forming a traceable chain. IDs are
4-digit and domain-prefixed (`payments:OPP-0042`) so they are unique across the mesh.

| Type | ID prefix | Meaning |
|---|---|---|
| `Outcome` | `OUTCOME-` | A business result being pursued. |
| `Opportunity` | `OPP-` | A user need or problem that could be addressed. |
| `Solution` | `SOL-` | A proposed way to address an opportunity. |
| `Assumption` | `ASSUMPTION-` | Something believed but not proven, usually attached to a solution. |
| `Story` | `STORY-` | A unit of delivery. |
| `Epic` | `EPIC-` | A grouping of stories. |
| `Interview` | — | A research conversation. |

**Parents are optional.** An artifact may exist before anyone decides where it belongs in the
chain — that is normal in discovery, not an error.

### Group C — Canonical context and structure

The slow foundation. One authored instance each, referenced by path.

| Type | Meaning |
|---|---|
| `ContextFile` | A canonical context file — business context, coding standards, and so on. |
| `Persona` | A customer or stakeholder persona. Keyed by `slug`. |
| `Architecture` | Cross-cutting technical architecture. |
| `Domain` | A namespace within the Hub — one folder under `domains/`. |
| `Board` | An external visual surface (Miro, Claude Design) — a view, never canonical. |

---

## Three types worth explaining

### `Domain` — a namespace, not a repository

A `Domain` is a folder under `domains/` holding all context about one thing. It answers "what is
this context *about*."

| Property | Required | Meaning |
|---|---|---|
| `name` | yes | The folder name, and the ID prefix (`payments` → `payments:OPP-0042`). |
| `about` | yes | What this domain covers, in one line. Declared in the index. |

**A domain lives at `domains/<name>/` and nowhere else.** The path is the declaration, so nothing
has to detect domain-ness. A folder called `product/` at the root is the cross-cutting product
tree; the same name under `domains/payments/` belongs to that domain.

**A domain need not map to a code repository.** It may cover one repo, several, or part of one.

**A domain holds context files and nothing else.** It has no index and no staging tree of its
own — both are centralized at the Hub root, and its files are declared in the root index under
their full path (`domains/payments/technical/system-behavior.md`).

**Zero domains is legal and complete.** A mesh whose context is entirely cross-cutting never
instantiates this type, and that is correct use of the schema. Nothing may report an absent
`domains/` as a gap.

**Ownership is declared, not structural** — `owned-by`, or CODEOWNERS. The filesystem does not
enforce it.

### `Persona` — keyed by `slug`

| Property | Required | Meaning |
|---|---|---|
| `slug` | yes | The key stories reference (`first-time-buyer`). Unique within the mesh. |
| `name` | yes | Display name. |
| `emoji` | no | A single emoji for board rendering. |

One file per persona at `product/personas/{slug}.md`. **The slug is load-bearing**: a `Story`
names its actor by slug, so a missing persona is a genuine dangling reference and renaming a
persona file breaks something.

**There is no legend file.** A slug→emoji table kept apart from the personas would be a second
source of truth that goes stale. With `emoji` on the persona itself, the only failure mode is
"persona file missing" — which a validator can actually check. Rendering surfaces derive the
mapping by reading the persona files.

### `Board` — the one node that is not a file

Every other node in the mesh is a file, and every other edge points at one. A `Board` lives in
Miro or Claude Design and is addressed by board ID.

Board sync is **optional** — a team need not use it — but the vocabulary defines the slot so
teams who do have a defined home.

- **A sidecar is an attachment to its parent node, never a standalone node.** Co-located with
  the artifact it syncs, suffixed `.board.json`.
- **Sidecars are never the source of truth.** They hold sync state — board ID, geometry,
  last-synced sha. Dropping every sidecar loses no context, only sync convenience.
- **The edge is `rendered-on`**, artifact → board.

**This creates one validator exception**, enforced by `check_references.py` as a positive rule in
both directions: a `rendered-on` target **must** be a board reference and **must not** be a path
(a file target would make the file the visual surface, inverting "a board is a view"), and **no
other edge type may target a board.**

Whether the board actually exists is deliberately unchecked — that is the vendor's API, and
asking would couple the mesh to a vendor.

The board *sync* itself — reading a board, writing changes back — is a separate vendor
integration, outside context-mesh. The mesh defines the slot; a sync tool fills it.

---

## Edge types

All edges are **directed and named**: `source —edge→ target`.

| Edge | Direction | Meaning |
|---|---|---|
| `derives-from` | Group-A node → `Conversation` | Provenance. Mandatory on every ingested node. |
| `references` | any → `Domain` / Group-B node | A soft mention or link. |
| `applies-to` | `Persona`/`Architecture`/`Knowledge`/`DomainFact` → `Domain` | This context governs that domain. |
| `parent-of` | Group-B → Group-B | The traceability chain (Outcome→Opportunity→Solution→Story; Epic→Story). Optional. |
| `contradicts` | any → any | This node conflicts with that one. **Flagged for a human, never auto-resolved.** |
| `rendered-on` | Group-B node → `Board` | An optional visual view. |
| `owned-by` | any → team | The authoring owner. Declared, not inferred from location. |
| `loaded-by` | `ContextFile` → index | When this file should load. |

---

## Legal-edge matrix

**This is the routing logic.** For each source type, the edges it may legally originate. An edge
not in this matrix is a validation error, caught by `validate_placements.py` before anything is
written.

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
| `Board` | none — terminal; only ever a `rendered-on` target |

Read it as routing: a `Knowledge` chunk `applies-to` a domain and may `contradict` existing
context, which flags a conflict for a human. An `OpenQuestion` can only point back at where it
came from — it has nowhere to go until someone decides something.

---

## Tags

Two tags ride on nodes. They are not relationships:

- **`decided` | `undecided`** — where in staging a chunk sits.
- **`state: staging | canonical`** — promotion lifecycle position. A promoted candidate stays in
  staging marked `canonical`, as the audit trail.

---

## What the mesh does not type

**Work items.** No `Todo`, `Task`, or `Workflow`. A queue is the work itself, not context about
it, and every team tracks work differently. Ingestion notices action items and reports them; it
does not file them.

The full design for work routing is preserved in the source repository, complete enough to
rebuild from if it is ever wanted.

---

## Changing the vocabulary

Adding a type is a minor change. Changing an edge's legality or removing a type is a breaking
change and requires updating every dependent doc and the skills that enforce the matrix.

**Every type needs a storage rule.** A type the schema recognizes but the taxonomy has no home
for is a gap every layer assumes another layer has filled. Add the type and its home together,
or not at all.

Meshes record which vocabulary they were built against, in the Hub root index's
`**Mesh vocabulary:**` line, so `setup-mesh` can migrate content written under an older
convention.
