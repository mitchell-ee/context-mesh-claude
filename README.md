# context-mesh (Claude)

**The structure for where LLM context lives across an organization, and the process for
populating it from conversations.** A plain-language overview of what it does today and what's
next; for the authoritative detail, see the docs linked at the end (or start with
[`docs/vocabulary.md`](docs/vocabulary.md), the locked schema everything references).

The `-claude` in the repo name marks the **packaging**, not the design. The structure itself is
LLM-agnostic — plain markdown, no vendor coupling — and this repo is its Claude Code
distribution. A port to another harness would reuse [`docs/`](docs/) and
[`prompts/`](prompts/) wholesale and replace only [`skills/`](skills/).

---

## Install

Packaged as the `ee-context-mesh` [Claude Code plugin](https://code.claude.com/docs/en/plugins):

```
/plugin marketplace add mitchell-ee/claude-plugins
/plugin install ee-context-mesh@mitchell-ee-claude-plugins
```

That installs the three skills below. Start with `setup-mesh` against the repo you want to use
as your Hub.

**The plugin is a wrapper, not the substance.** Everything it stores is plain markdown, and the
structure it defines ([`docs/`](docs/)) is deliberately vendor-neutral — the schema, the
taxonomy, and the transcript-structuring prompt work with any LLM or tooling. Only the three
skills are Claude-specific packaging.

---

## The problem it solves

Durable engineering knowledge — a decision from a meeting, how a service really behaves, a
newly-spotted product gap — rarely gets written down where it belongs. Meanwhile every AI
coding tool in the org is starving for exactly that context, and each repo knows only about
itself. In a big estate — the seeding case was ~100 service repos and no monorepo — there is no
shared brain.

context-mesh is that shared brain: a well-defined home for scattered knowledge, plus a
repeatable way to get knowledge out of conversations and into that home without filing it by
hand.

- **AI-tool-agnostic.** Everything it stores is plain markdown any tool or human can read —
  Claude, Cursor, Copilot, or whatever comes next. A hard constraint, not a preference.
- **Progressive disclosure.** Each file is small and single-purpose; an index says what exists
  and when it's relevant. An assistant reads only the files a task needs, never the whole
  corpus.

---

## Where context lives: the Hub, and only the Hub

**All context lives in the AI Hub — one repo.** Context sits on two axes: **what it's about**
(product / technical / process) and **its scope** — *cross-cutting* (at the Hub root, governing
everybody) or *domain* (inside one domain folder, about one thing).

A **domain** is a namespace, not necessarily a code repository: it may map 1:1 to one repo, span
several, or be finer than one. **Code repos hold no context and are unaware of the mesh.** All
Hub content, domain-specific included, is readable by everyone.

### Cross-cutting — at the Hub root (shared, changes rarely)

All singletons, referenced by path.

| Area | Files |
|---|---|
| **Product** | `product/business-context.md`, `personas.md`, `design-principles.md`, `glossary.md` |
| **Technical** | `technical/target-architecture.md`, `integration-map.md`, `api-and-interface-standards.md`, `coding-standards.md`, `testing-standards.md`, `nfr.md` |
| **Process & governance** | `process/ways-of-working.md`, `definition-of-done.md`, `review-and-release.md`; `governance/data-handling.md`, `access-control.md`, `compliance.md`, `ai-policy.md`; `capabilities/skill-governance.md` |
| **Shared workflows** | `process/workflows/` — e.g. `refinement.md`, `incident-response.md` |

### Domain — in `<domain>/` inside the Hub (specific to that thing/team)

| Kind | Files |
|---|---|
| **Technical singletons** (path-referenced) | `technical/repo-overview.md`, `system-behavior.md`, `runtime-architecture.md`, `legacy-notes.md`, `local-conventions.md` |
| **PM discovery artifacts** (many instances, ID'd) | `product/opportunity-solution-tree/` (outcomes, opportunities, solutions, assumptions) and `product/iterations/` (interviews, stories, epics, story maps, decisions) |
| **This team's workflow** | `process/workflows/backlog.md` — a pointer to the team's Jira/Linear |
| **Staging** | `staging/candidates/` — where ingestion drops undecided material |

A domain folder uses the **same layout as the Hub root**, so a path means the same thing at
either level. Whether a `product/…` file is cross-cutting or domain-scoped is answered by
*whether it sits at the root or inside a domain folder*. Domain-prefixed IDs
(`payments:OPP-0001`) keep artifacts globally unique.

### What's customizable, and what isn't

The two lists above are a **default manifest**, not a specification — generalized from one real
project. Expect to tweak them per implementation.

- **Customizable (the manifest):** which files exist, their names, what each is about, and
  whether a given file is cross-cutting or domain-scoped, **and which domains exist**. Add `technical/legacy-runtime-topology.md` for a
  migration; drop `design-principles.md` for a team with no design practice; rename `nfr.md` →
  `slos.md`. This costs nothing structurally — the index lists the file, an agent loads it,
  nothing validates its name.
- **Fixed (the framework):** the [vocabulary](docs/vocabulary.md) (node/edge types), the discovery-
  artifact shape (the OST folders, 4-digit IDs, the `Story → Solution → Opportunity → Outcome`
  chain), the cross-cutting/domain/staging layer semantics, and the promotion rules. These are
  what the graph's edges traverse; changing them changes the routing logic.

The line: the manifest covers **path-referenced singletons** (inert to the type system); the
framework covers **everything the graph reasons over**.

---

## What's built today

A conversation-to-context loop, packaged as three skills, plus one optional prompt that
pre-cleans a raw transcript before the loop begins.

### `setup-mesh` — get the Hub ready

Finds or declares each **index** (Hub root and per domain) and writes a **pointer to where
to-dos go** (Jira, Linear). It does *not* generate context files — it reports which are missing. A stub the index
lists but that says nothing is worse than an honest gap.

It also records the mesh's **PII policy** on the Hub root index — `strip` (the default: redact
speaker identity) or `enrich` (preserve who-said-what, and take on the client + DPO custody that
implies). Both the structuring prompt and `ingest-conversation` read it.

### `prompts/structure-transcript.md` — clean up a raw transcript (optional pre-pass)

A **vendor-neutral markdown prompt** — no scripts, no Claude-specific packaging. Any LLM can run
it, or you can paste it into a meeting tool (Granola, etc.) as a template. It turns a raw
transcript from *any* source into a clean, topically-labeled one: merged speaker turns, filler
and abandoned tangents dropped, secrets redacted.

Meeting tools like Granola get their value from a *user-authored template inside that one tool*.
This prompt does the same structuring as a **mesh artifact** instead, so it works on a raw
Zoom/Meet/Teams export too — nothing depends on someone having written a good template. It
**cleans and labels only; it never assigns types or routes anything** — that stays the sole job
of `ingest-conversation`, so the two can't drift. Its output is still just a transcript, which
enters the pipeline the same way any raw one does. Optional: skip it and `ingest-conversation`
handles a raw transcript directly.

### `ingest-conversation` — turn a transcript into staged knowledge

```
transcript → distilled typed chunks → proposed placements → checkpoint → validated → staging
```

- **Distill & sanitize** the transcript into durable facts; the raw copy isn't kept.
- **Type each fact** (domain fact, requirement, open question, to-do…) — the type decides where
  it may go.
- **Propose a home** per fact, reading *only the indexes*. If the index can't place it, that's
  reported, not fudged.
- **Dedup & conflict-check** against the one chosen target file: already there → skip; says the
  opposite → flag.
- **Checkpoint** — every placement, least-confident first; you `approve` / `retry` / `drop`.
  This is the gate.
- **Write to staging** on approval. No PR (see below).

### `promote-candidate` — make staged knowledge official

The separate, human-initiated step that moves a fact from staging into the canonical context
everyone reads. Promotion has six outcomes: **merge** into the target doc, **contradicts** (a
human decides), **handover** to the tracker, **resolve** an open question first, **no home**,
or **never** (provenance records stay in staging). Edits to the same file are batched into one
reviewed change.

### Using it, start to finish

1. **Once, then again to add a domain:** `setup-mesh`. Sets the PII policy while you're there.
2. **After a meeting, if the transcript is raw and messy** (a Zoom/Meet/Teams export, not
   pre-structured): run it through `prompts/structure-transcript.md` first for a clean, labeled
   version. Optional — skip it for an already-tidy transcript.
3. **Then:** `ingest-conversation`. Review placements at the checkpoint; on approval
   they're written straight to staging.
4. **When ready:** `promote-candidate`. It opens a **PR** into the canonical layer; approving
   it makes the knowledge official.

**One review to stage, one PR to promote.** The PR sits at promotion, not staging, because
that's where it earns both its jobs: staging writes are collision-free (new files, unique IDs)
and already reviewed at the checkpoint, whereas promotion edits shared canonical docs that
multiple promotions can touch at once.

---

## Status

The structure, the vocabulary, and the three-skill loop are built. What is **not yet proven** is
the loop against real material: ingestion has only run on a synthetic transcript and AI
coding-session logs (a poor source — retrieval isn't new knowledge). The real target is a
**multi-person meeting transcript**, where the decision happens in the room and nobody writes it
down. That end-to-end run is the next milestone, pending a real recording.

---

## Where the detail lives

- [vocabulary.md](docs/vocabulary.md) — the locked type system. The authoritative schema.
- [file-taxonomy.md](docs/file-taxonomy.md) — where each piece of context lives; the full manifest.
- [board-sidecars.md](docs/board-sidecars.md) — optional visual-board attachments.
- [ingestion-pipeline.md](docs/ingestion-pipeline.md) — the ingestion pipeline in detail.
- [prompts/structure-transcript.md](prompts/structure-transcript.md) — the optional
  vendor-neutral pre-pass that cleans and labels a raw transcript.
- [build-scope.md](docs/build-scope.md) — what the first cut built and deliberately left out.
- [setup-scope.md](docs/setup-scope.md) — how the Hub gets stood up and carved into domains; why
  there is no separate scaffolding command.
- [promotion-boundary.md](docs/promotion-boundary.md) — promotion (staging → canonical) and where
  the skills' job ends.
- [knowledge-graph-model.md](docs/knowledge-graph-model.md) — why a knowledge graph rather than a
  flat taxonomy (rationale; superseded on specifics by `vocabulary.md`).
