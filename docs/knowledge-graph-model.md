# context-mesh: the knowledge-graph model

> **Historical note (2026-07-21).** This document records the original rationale for choosing
> a knowledge graph, written when context lived across many repos and was mirrored into the Hub.
> The rationale stands; the multi-repo specifics do not. All context now lives in the AI Hub in
> domain folders — `RepoFact` is `DomainFact`, and `mirrored-to`/`mirrored-from` no longer exist.
> See the [single-Hub collapse](vocabulary.md#v20-2026-07-21--the-single-hub-collapse).
> **Superseded on specifics by [vocabulary.md](vocabulary.md).**


Status: thinking / design note. Written 2026-06-25.

## The decision: graph from the get-go, not a taxonomy with links bolted on

The conversation-ingestion layer of the AI Hub is a **knowledge graph**, not a
taxonomy. The relationships between things *are* the value — they are not an
afterthought on top of a classification scheme.

The tell is in what the design has to do. Every requirement from the seeding
conversation is a **named, typed edge between two entities**:

- a distilled chunk **references** repos and **links-to** influenced artifacts
- a requirement **triggers** a refinement workflow and **creates** a story/epic
- context is **owned-by** someone, **mirrored-to** the AI Hub, **loaded-by** an index file under conditions
- cross-cutting context (personas, architecture) **applies-across** many repos
- knowledge **derives-from** a conversation that **influenced** these artifacts

None of these is an "is-a" relationship. The whole reason the AI Hub exists is that
~100 microservice repos (no mono repo) can't share knowledge — and the thing that
connects them is precisely this web of references. A pure classification scheme
captures none of it.

## Taxonomy vs. ontology vs. knowledge graph (for reference)

- **Taxonomy** — classifies items into a hierarchy; one dominant relationship (`is-a`). Answers "what kind of thing is this?" Good for lookup and grouping.
- **Ontology** — a formal model of a domain: entities, attributes, and many named/typed relationships, plus rules to reason over them. Answers "how does everything relate, and what can I infer?"
- **Knowledge graph** — an instantiated ontology: actual nodes and edges populated with real data.

An ontology *contains* a taxonomy (its `is-a` backbone) and adds everything else.
For context-mesh, the **taxonomy becomes the type system** of the graph — the
controlled vocabulary of node types and edge types — not the top-level structure.

## Node types (the "taxonomy", reframed)

> **Locked (2026-06-25):** this starter vocabulary has been finalized — grouped by
> lifecycle role, near-duplicate edges collapsed, `Artifact` dropped. The authoritative
> schema is now [vocabulary.md](vocabulary.md); the list below is the historical starting
> point.

The chunk-classification work from the call becomes "define the node and edge types."
Starting vocabulary (to refine with Andy):

**Node types**
- `Conversation` (a distilled interaction; raw transcript may not be retained)
- `Knowledge` (durable fact → product-level context)
- `Requirement` (→ triggers refinement, becomes Story/Epic)
- `Todo` (→ backlog/queue)
- `RepoFact` (repo-specific context) — *now `DomainFact`; see the note at the top*
- `Repo`
- `Artifact` (story, epic, context file, doc, board object…)
- `Persona`, `Architecture` (cross-cutting context)

**Edge types (named, typed)**
- `derives-from` (Knowledge/Requirement → Conversation)
- `references` / `links-to` (Conversation → Repo / Artifact)
- `triggers` (Requirement → workflow)
- `creates` (Requirement → Story/Epic)
- `applies-to` / `applies-across` (Persona/Architecture → Repo)
- `owned-by`, `mirrored-to`, `loaded-by`

The node type determines which edges are **legal** — a `Todo` routes to a backlog;
a `Requirement` triggers refinement. That is the taxonomy doing real work as a schema.

## Connection to the Visual Collaboration / board-object model

This is the key cross-thread insight: the board-object architecture from the
**Visual Collaboration with AI** model is *already a typed graph*:

`opportunity → opportunity-solution-tree → assumption → story → epic →
activity-backbone card`

— objects joined by ID, one markdown file per object, stored in the repo, read and
written by agents. The conversation-ingestion model and the board-object model are
arguably **the same knowledge graph viewed two ways**: one populated from
conversations, one populated/edited through visual workshops. Unifying them is a
goal worth pursuing — same node/edge vocabulary, same storage substrate.

## Storage: graph is the model, the substrate stays dumb

> **Correction (2026-06-25, post-note):** the "everything joined by ID" framing below is
> too broad. The current decision: **most files reference each other by filesystem
> location** (repo + relative path), kept human-navigable, with an index/loader for
> navigation. **IDs are reserved for artifact types with many siblings** that must be
> tracked and differentiated — the board-object family (outcomes, opportunities,
> solutions, activities, epics, stories), as in the aiviz project. One-off singletons
> (canonical product/technical context) are referenced by path, not ID. See `CLAUDE.md`.

"Knowledge graph" must **not** pull us toward heavyweight tooling (triple stores,
RDF/OWL, Neo4j) before it's needed. The harness-agnostic stance and the observed
anti-pattern of agents rebuilding context at runtime on every query both argue for a
**dumb substrate**:

- Nodes = markdown files (one per object), joined by **ID** — exactly the board-object pattern.
- Edges = ID references in frontmatter / index files.
- The AI Hub remains a mirror; CI syncs source-repo context into it.
- The graph is the **logical** model; files-in-repos is the **physical** storage.

Upgrade to a real graph DB only if/when querying and inference demand it. Default to
the simplest thing that represents nodes + typed edges.

## Where the taxonomy is still genuinely needed

Defining and governing the **controlled vocabulary** of node and edge types is a real,
bounded task — and it's the first thing to do, because it constrains everything
downstream (routing, validation, what edges are legal). That is the reframed A3 task.

## Open questions (carried from the call)

- Where does each machine/process write graph state for others to read? (CI-mirror is the obvious channel.)
- How much PII clearing happens at distillation vs. never storing raw transcripts at all?
- Does the human validation step approve **nodes and edges** explicitly before commit? (Leaning yes.)
- How far do we unify with the board-object model before it adds risk?
