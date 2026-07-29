# context-mesh — visual-board sidecars

Status: design note. Extracted 2026-07-21 from `hub-leaf-meshing.md` Principle 5, when that
document was retired by the [single-Hub collapse](vocabulary.md#v20-2026-07-21--the-single-hub-collapse).
This principle was the one part of that document with **no dependency on repo topology**, so it
survives the collapse unchanged and lives here on its own.

## The rule

Board sync (Miro, Claude Design) is **optional** — a team need not use it — but the ontology
**specifies how a sidecar fits** so that teams who do use it have a defined home.

Model: a **sidecar is a typed attachment to its parent node**, never a standalone node.

- **File convention:** co-located with the artifact it syncs, suffixed `.board.json` (or the
  aiviz `miro-metadata.json` / `cd-metadata.json` form). Example:
  `product/iterations/{slug}/story-maps/story-map-v2.board.json` attaches to
  `story-map-v2.md`.
- **Edge type:** `rendered-on` (artifact → board). The board is an **external view**, not part
  of the canonical graph — agents that ignore boards still get a complete context graph.
- Sidecars are **never the source of truth**; they hold sync state (board id, geometry,
  last-synced sha, sync direction) for one tool. Dropping every sidecar loses no context, only
  board-sync convenience.

This keeps context-mesh harness-agnostic (the substrate stays dumb) while giving
visual-collaboration tooling a defined, optional slot in the ontology.

## What a sidecar actually is

A sidecar is **structurally just an ordinary file** — committed, versioned, human-readable —
whose *only* distinguishing feature is that its `rendered-on` edge points at a node that is
**not stored as a file**: a `Board` living in Miro/Claude Design, addressed by board ID rather
than a filesystem path. Every other edge in the mesh points at another file; this one points
off the filesystem.

So the mesh side is **already done by the vocabulary**: the `Board` node type and the
`rendered-on` edge are locked in [vocabulary.md](vocabulary.md). The only incremental mesh work
was a **validator exception**: whatever walks the graph must know that a `rendered-on` target is
a legitimate off-filesystem board ID and not a dangling path.

## The validator exception (built 2026-07-21)

`skills/setup-mesh/scripts/check_references.py`. There was no reference validator at all, so
this was "build the walker, with the exception in it."

The exception is a **positive rule enforced both ways**, not a suppression:

- a `rendered-on` target **must** be a board reference, and
- it **must not** be a path — a file target would claim that a *file* is the visual surface,
  inverting "a board is a view, never canonical";
- and **no other edge type may target a board.**

Whether the board *exists* is deliberately unchecked — that is the vendor's API, and asking
would couple the mesh to a vendor. Vendor-agnostic by regex (`miro:board:…`,
`claude-design:…` both pass).

Building it found two fail-open bugs in the walker itself.

## Out of scope

The actual **board sync** — reading a board, writing changes back, maintaining geometry and
`last-synced-sha` — is a **separate vendor-integration tool, deliberately outside
context-mesh**. The mesh defines the slot; a sync tool fills it.
