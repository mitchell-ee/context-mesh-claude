# Where context lives

**What this is.** The layout: which folder a given piece of context belongs in, and how to
declare it so ingestion can route to it.

**What you get from reading it.** You will be able to look at any fact and say where its file
goes, and write the index row that makes it reachable.

**Who needs it.** Anyone setting up a mesh or wondering why a fact landed where it did. For
*what* the types are, see [vocabulary.md](vocabulary.md). For the process end to end, see
[how-it-works.md](how-it-works.md).

---

## Everything lives in the AI Hub

One repo holds all context, authored once and never mirrored. The Hub may be its own repo or it
may be the code repo — in a monorepo the Hub root *is* the repo root.

```
context-index.md          the root index — routing reads this
product/                  cross-cutting product context
technical/                cross-cutting technical context
process/  governance/     how the team works; policy
staging/candidates/       ingested, not yet decided
domains/                  OPTIONAL — one folder per domain
  payments/
    context-index.md      that domain's index
    technical/  product/
    staging/candidates/
```

**Two questions decide where any file goes:**

| | Meaning | Answers |
|---|---|---|
| **Scope** | Who does this govern? | *Cross-cutting* (Hub root) or *one domain* (`domains/<name>/`) |
| **State** | Is it decided? | *Canonical* (decided, believed) or *staging* (proposed, not yet believed) |

A domain folder uses **the same layout as the Hub root**, so a path means the same thing at
either level. Whether `product/business-context.md` is cross-cutting or domain-scoped is
answered by whether it sits at the root or inside a domain folder.

**A domain is exactly a directory under `domains/`.** Nothing else is one, whatever it contains.

**Domains are optional.** A mesh with no `domains/` directory — all context cross-cutting — is
complete, not half-built.

---

## The three kinds of context home

Everything ingestion can route to is one of three kinds. Declaring a home correctly in the index
is all that is needed to make content flow to it.

| Kind | Looks like | New content… | Declare it as |
|---|---|---|---|
| **Singleton** | `technical/architecture.md` | merges into the file | a row in the **Context files** table |
| **Collection** | `product/personas/`, `decisions/` | modifies an existing member **or** creates a new one | a row in the **Collections** table, path ending `/` |
| **Discovery artifacts** | `opportunity-solution-tree/`, `iterations/` | follows that structure's own rules | nothing — the tooling already knows it |

**How to choose — ask how many of this thing there will be.**

- **One** → a singleton. Architecture, coding standards, a glossary.
- **Many of the same kind** → a collection. Personas, architecture decision records, journey
  maps. One index row covers the whole folder, so adding the tenth persona is not an index edit.
- **Product-discovery work** → discovery artifacts. Opportunities, solutions, stories. These
  carry IDs and form a chain the tooling follows, so their layout is fixed and you do not
  declare it. You only meet these if you do discovery work in the mesh.

**Some collection members are referenced by name.** A `Story` names a persona by its slug, so
renaming `first-time-buyer.md` breaks that reference. It is still an ordinary collection,
declared the same way — just know that renaming a member there is a real change. If nothing
points at a member (architecture decision records are the usual case), rename freely.

---

## Declaring a home in the index

**Routing reads the index and only the index.** A file the index does not list is invisible to
ingestion, however real it is.

### Context files (singletons)

A row per file, and **the path must be a markdown link**:

```markdown
| [technical/system-behavior.md](technical/system-behavior.md) | What this service does — flows, transactions | debugging behavior; changing a flow |
```

Backticked or plain-text paths are **invisible to the tooling** — the checker extracts paths with
a link regex, so a backticked row is neither checked nor routable. An index written entirely in
backticks parses to zero files while looking complete.

### Collections

Their own table, with the path **ending in a slash**:

```markdown
## Collections

| Collection | Members | About | Load when |
|---|---|---|---|
| [decisions/](decisions/) | `NNN-{slug}.md` | Architecture decision records | deciding something with precedent |
```

- **The trailing slash is what distinguishes a collection from a file**, for a human and for the
  tooling both.
- **`Members` is the naming pattern** — one of `{slug}.md`, `{date}-{slug}.md`, or
  `NNN-{slug}.md`. It is used only to *name* a new member. Nothing reads meaning back out of an
  existing filename.
- **A missing directory is an error; an empty one is a note.** Nothing creates the folder for
  you, but an empty declared collection is normal — the row says where this kind of context
  goes, not that any exists yet.

### Deliberate gaps

Files that should *not* exist here go under **Not in this mesh**, **backticked, never linked** —
a link would make them read as a context file that is missing:

```markdown
- `governance/data-handling.md` — the platform team owns this; not duplicated here
```

### Four states that look alike

| State | Where it goes | Means |
|---|---|---|
| **Deliberate gap** | *Not in this mesh*, backticked | Should never exist here |
| **Pending home** | a context row, linked | Declared home, not written yet. **Normal** — promotion fills it |
| **Broken link** | a context row, linked | Was real, now missing — an error |
| **Collection** | a *Collections* row, linked, trailing `/` | A folder; one row covers every member |

**A pending home and a typo'd path are indistinguishable**, and neither blocks. That is a
deliberate trade — treating a pending home as broken made setup withhold READY over work that
simply had not happened yet. The consequence is that **nothing catches a typo in a row's path**,
so setup names the pending paths and expects you to read them.

---

## Which files exist is your choice

There is no required file list. A team with four context files and a team with twenty are both
correctly configured, and nothing validates that any particular file exists — a repo missing
`design-principles.md` is not broken, it is a repo without design principles.

**A starting set ships as commented examples** in the index template
(`skills/setup-mesh/templates/context-index.md`). Add, drop, rename, split, or merge to match
how your team already works. `setup-mesh` surveys what a repo already has and suggests only what
seems genuinely absent, matching your existing naming rather than the template's.

What does **not** vary: the layer semantics above, the three kinds of home, the discovery-artifact
structure, and the [vocabulary](vocabulary.md). Those are what the tooling reasons over.

---

## Collections in detail

A **collection** is many files of one kind in one folder. Architecture decision records are the
motivating case: `decisions/001-gcp-dev-region.md`, `002-…`, all the same kind of thing, more
arriving over time.

**One row for the folder, not one row per file.** Listing members individually grows the index
without bound, makes every new member an index edit, and repeats a near-identical description as
many times as there are files.

### Modify an existing member, or create a new one

A collection is the one kind where routing does not finish the job. The index row describes the
*folder*, so routing can tell that a fact is an architecture decision without telling *which*
one. A separate step — member resolution — runs after the folder is chosen and reads that
folder's members to decide.

**Ambiguity resolves to CREATE.** If a fact clearly belongs to an existing member, it modifies
that member. If it clearly does not, it creates a new one. If it *might* belong to an existing
member, it creates, and the near-match is flagged at the checkpoint for a human to overturn. A
spurious new member is visible on disk and named at the gate; a wrong merge is buried in a file
nobody re-reads.

**Promotion may only add a member to a collection whose row already exists** — never the member
and its justifying row in one motion.

**Ordinal patterns number at promotion time**, by reading the directory, so two promotions
running at once could both claim `004`. Promotion is expected to run single-threaded. Prefer
`{date}-{slug}.md` for new collections, which cannot collide.

---

## Discovery artifacts

Product-discovery work, if you do it in the mesh. These live in the owning domain under
`product/`:

```
product/opportunity-solution-tree/     outcomes, opportunities, solutions, assumptions
product/iterations/                    interviews, stories, epics, story maps
```

**IDs, not paths.** Each artifact carries a 4-digit ID, domain-prefixed so it is unique across
the mesh: `payments:OPP-0042`. A story names its solution *by that ID*, forming a chain
(`Story → Solution → Opportunity → Outcome`) that `check_references.py` walks.

**The layout is fixed**, because the chain breaks if the folders move. This is the one structure
you do not declare in the index — the index lists the tree as IDs and titles so an agent can
reference `payments:OPP-0001` without loading the file.

**No parent is required.** An artifact may exist before anyone decides where it fits. That is
normal in discovery.

---

## Staging

Undecided material, at the root and in each domain:

```
staging/candidates/       one file per ingested candidate
staging/inbox/            optional: raw material dropped for later processing
```

**Staging is not canonical context.** Nothing here is believed yet. Ingestion writes here
directly; promotion moves claims into canonical files.

**A promoted candidate stays** in staging, marked `state: canonical`. It is the audit trail: the
context file states the fact, the candidate records how we know it — which conversation, who
raised it, when.

**`staging/inbox/` is a drop location, not a collection.** No naming pattern, nothing routes to
it. Processed items move to `staging/inbox/processed/`.

**The staging tree can live anywhere.** Set `CONTEXT_MESH_STAGING` and the whole tree moves
together, keeping `candidates/` and `inbox/` beneath it. The value is a **path**, so it may be
nested to any depth:

```bash
export CONTEXT_MESH_STAGING=_incoming        # -> _incoming/candidates/
export CONTEXT_MESH_STAGING=docs/staging     # -> docs/staging/candidates/
```

The path is relative to **each container**, so one setting covers the Hub root and every
domain. With `docs/staging`, the root's tree is at `docs/staging/` and the payments domain's
at `domains/payments/docs/staging/`.

It is set in **one** place and every script reads it — nothing else needs editing. The root
index's Staging table documents the path for humans, so if you change one, change the other:
the table is prose, the variable is what the tooling obeys. Get them out of step and the index
describes a folder nothing reads or writes. The scripts detect that specific mismatch and name
it, rather than reporting an empty staging tree as normal.

**Open questions live in the file they are about**, not in a separate list. A question about
payments behavior belongs beside that behavior, where whoever reads it will see it.

---

## The index is the routing input

Every container — the Hub root and each domain — has a `context-index.md`. It is the only thing
routing reads.

Each row needs two things a script cannot guess:

- **What the file is about** — one line.
- **When to load it** — the condition that makes it relevant. This is the part that makes
  progressive disclosure work.

The root index additionally declares which domains exist and records the mesh's vocabulary
version.
