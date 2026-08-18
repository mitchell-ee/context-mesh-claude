# context-mesh

**A defined home for your organization's durable knowledge, and a repeatable way to get
knowledge out of conversations and into that home.**

Durable knowledge — a decision from a meeting, how a service really behaves, a product gap
someone spotted — rarely gets written down where it belongs. Meanwhile every AI coding tool in
the org needs exactly that context, and each repo knows only about itself.

context-mesh gives that knowledge one place to live, and a process for putting it there without
anyone writing it up by hand.

**New here? Read [docs/how-it-works.md](docs/how-it-works.md)** — it walks through the whole
thing with diagrams. This page is just the map.

---

## The idea in three points

- **One repo holds all context.** Authored once, never mirrored. Cross-cutting context lives at
  the root; anything specific to one thing lives in that thing's folder under `domains/`.
- **Everything is plain markdown.** Any tool or human can read it — Claude, Cursor, Copilot, or
  whatever comes next. This plugin packages it for Claude Code, but nothing about the structure
  is Claude-specific.
- **An index says what exists and when it matters.** An assistant reads only the files a task
  needs, never the whole corpus.

## The loop

```
setup once  →  ingest a conversation  →  you approve  →  staging  →  you promote  →  canonical
```

Four skills:

| Skill | What it does |
|---|---|
| **`/setup-mesh`** | Surveys what context a repo already has, helps declare the index, and suggests what looks missing. Creates folders and an index — never a context file. |
| **`/structure-transcript`** | *Optional.* Cleans up a raw transcript before ingestion. Also ships as a plain prompt that runs in any tool. |
| **`/ingest-conversation`** | Distills a transcript into typed facts, proposes a home for each, checks for duplicates and conflicts, then stops and asks you. Approved facts go to staging. |
| **`/promote-candidate`** | Moves staged knowledge into the canonical files everyone reads, batched by target file, opening one PR. |

**Two places a human decides**, and nothing passes either without you:

1. **The checkpoint**, during ingestion — every proposed placement, grouped by destination.
   Approve, retry, or drop. It stops here while the transcript is still in context, so fixing a
   bad placement is cheap.
2. **The PR**, at promotion — where existing shared docs actually change.

## Where things go

Three kinds of home, and picking one is usually obvious:

- **A single file** — `technical/architecture.md`. Most context is this.
- **A folder of same-typed files** — personas, architecture decision records. One index row
  covers the folder.
- **Discovery artifacts** — opportunities, solutions, stories, carrying IDs that form a chain.
  Only if you do product discovery in the mesh.

Which files you keep is your decision. A starting set ships as commented examples in the index
template; add, drop, and rename to match how your team already works.

---

## Installing

Available in the `mitchell-ee/claude-plugins` marketplace as `ee-context-mesh`. The marketplace
pins versions — refresh it before updating, or you will reinstall the version you already have.

## Where the detail lives

| Doc | What it covers |
|---|---|
| [how-it-works.md](docs/how-it-works.md) | **Start here.** The whole lifecycle, with diagrams. |
| [vocabulary.md](docs/vocabulary.md) | The types of context and how they relate. |
| [file-taxonomy.md](docs/file-taxonomy.md) | Where each kind of context lives, and how to declare it. |

## Status

The structure and the three-skill loop are built and in use. What is **not yet proven** is the
loop against a real multi-person meeting transcript — the case it exists for, where the decision
happens in the room and nobody writes it down. That end-to-end run is the next milestone.
