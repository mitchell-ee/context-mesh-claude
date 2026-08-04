# Migrations

One file per migration. `setup-mesh` runs them; nothing else does.

**These files ship with the plugin.** They live at
`${CLAUDE_PLUGIN_ROOT}/skills/setup-mesh/migrations/` — inside the plugin's versioned install
directory, never in the user's Hub. A migration is invoked by absolute path from there, and
operates *on* the Hub's content. If this directory looks empty or absent, re-resolve
`${CLAUDE_PLUGIN_ROOT}`; searching the Hub for `migrations/` will always come up empty, and
that is not evidence of a packaging problem.

A migration exists because **the plugin changed a convention and existing mesh content is now
stale**. The plugin cannot run code when it is updated — there is no install hook — so
migration is *lazy*: the `Mesh vocabulary:` marker in the Hub root's `context-index.md` makes
the gap visible the next time setup runs, and setup applies the fix.

## The rule that governs every migration here

> **A migration only ever edits an index, or reports. It never moves, deletes, or rewrites
> content in the mesh.**

This is stricter than it needs to be for any one migration, and it is deliberate. **The
plugin only ever adds to the mesh.** The content is the team's — authored by people, often
the only copy, and worth more than the tooling. A migration that relocates a directory it
misidentified, or deletes a file it misread, destroys something the plugin did not create and
cannot restore.

So the two things a migration may do are:

1. **Edit the index** — remove a row pointing at a convention that no longer exists, or add
   one. The index is the plugin's own artifact and the routing input; correcting it is what
   migration *means*.
2. **Report** — tell the human what to do, and let them do it.

A migration that wants to move a file **reports instead**. That is a real loss of automation
and it is the right trade: the human doing it knows whether the directory is what the
migration thinks it is.

## Naming

```
{version-that-introduced-the-change}-{slug}.md
```

The version is **when the convention changed**, not when the migration was written — a
migration added late for an already-released version still names that version, and still
applies, because selection is by data shape rather than version arithmetic (see below).

Every migration here is `.md`. With file-moving off the table, none of them is a purely
mechanical transform: each either edits an index (which needs judgment about what a row
meant) or reports (which is prose by definition).

## Header

Every migration opens with:

```
**Applies when:** <the data shape that makes this migration relevant>
**Guard:** <what to check; what a no-op looks like>
**Requires:** <migrations that must run before this one, or —>
**Precedes:** <migrations that must run after, or omit>
```

`Requires:` is honored **before** version order. Version numbers do not reliably encode
dependency; declare it rather than relying on the numbers.

## The contract

Every migration MUST be:

1. **Guarded** — inspect the content first; act only if the old shape is present. A migration
   that finds nothing to do is a success, not a failure.
2. **Idempotent** — running it twice changes nothing the second time. This is what makes
   "run every migration" safe, and what makes a retroactively-added migration safe on a mesh
   that already passed that version.
3. **Dry-run first** — show what would change before changing it. Setup always previews and
   asks before applying.
4. **Explicit about no-ops** — say `nothing to do` when the guard finds nothing. A silent
   no-op is indistinguishable from a silent failure.
5. **Additive or corrective only** — see the rule above. Index edits and reports; never a
   move, a delete, or a rewrite of mesh content.

## Guards fail open, never closed

A migration that cannot tell whether it applies must **do nothing and say so**, not guess.
The cost of a skipped migration is a validation failure and a clear prompt; the cost of a
wrong guess is corrupted mesh content with a version marker vouching for it.

This project has found ten fail-open validator bugs, every one of which reported success
while checking nothing. A migration guard is a validator. Test it by deliberately breaking
something, **in both directions** — the old shape must be detected, *and* an already-migrated
mesh must be left alone.

## Idempotence is the whole design

There is **no record of which migrations have run**. No state file, no applied-list, no
bookkeeping to drift out of sync. Setup runs **every** migration in version order — not just
the ones newer than the marker — and each decides for itself whether it applies.

Running the full set is what makes a **retroactively-added migration** work: one written
after meshes already reached that version would never be selected by a newer-than filter.
**The marker is a prompt trigger ("you may be behind, run setup"), never the selector.**

That works only because guards key on **content shape**, not version numbers:

- The workflow migration matches a `## Workflows` index section and rows pointing into
  `process/workflows/`. Once those rows are gone, it matches nothing.
- The domains migration matches a root-level directory holding a `context-index.md`. Once
  the human has moved it under `domains/`, there is nothing at the root to find.

**Anchor guards on structure, never on bare words.** `Todo` as a `type:` field is a node
declaration; "todo" in a sentence is prose. A migration doing blanket text substitution is
not idempotent, it is destructive — it will keep finding new things to "fix" on every run.

## Changes that need no migration

Not every breaking change leaves stale content behind. Two from v2.2 did not, and they are
listed here so nobody writes a no-op file for them later:

- **Parents became optional everywhere.** A pure loosening — content that specified a parent
  is still valid, and content that omitted one was already being written. Nothing to fix.
- **IDs widened to `0000`–`9999`.** Also a widening. Every existing four-digit ID remains
  valid, and `0000` merely became legal where it had not been.

A convention change needs a migration only when **existing content becomes wrong**, not when
it merely becomes non-mandatory.

## The validation gate

Migrations do not decide whether a mesh is current — **the data does.** After migrations run,
setup validates the result and stamps `Mesh vocabulary:` **only if the content actually
checks out**.

**Do not stamp because the migrations ran. Stamp because the content is correct.** A stamped
mesh that is still stale is worse than an unstamped one: nothing prompts, and the staleness
is invisible. A migration set that is incomplete — or one the human declined — must not be
able to certify a mesh as current.

So when you change a convention: add the migration **and** the check that proves it worked.
If you ship no migration for a convention change, the matching check fails, the mesh stays
unstamped, and setup keeps prompting. That is the intended behavior — the gap stays visible
instead of being certified away.

## Writing a new one

- Start from the closest existing migration; the guard is the part to get right.
- Test the guard against content that is **already migrated** — the no-op path runs most
  often and is the one most likely to be wrong.
- Test against a **throwaway fixture**, not a real Hub. A fixture written by the same session
  that wrote the migration cannot find the class of bug a real, unfamiliar mesh finds, so keep
  the fixture adversarial: include something that *looks* migratable but is not.
- Add a row to the table in `SKILL.md`, and a validation check if the convention needs one.
