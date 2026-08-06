# <domain> — context index

The index for one **domain folder** inside the AI Hub. (The Hub root has its own index,
which additionally lists the domains and holds cross-cutting context — see
[setup-scope.md](../../../docs/setup-scope.md).)

Read this first; load only what the current task needs.

**This file is the manifest, the routing input, and the progressive-disclosure contract.**
It is what ingestion reads to decide where a fact belongs — and the *only* thing it reads to
decide that. A file not listed here is invisible to routing.

## Domain identity

- **Domain:** `<domain>`
- **About:** <one line — what this domain covers>
- **Owned by:** <team>
- **ID prefix:** `<domain>:` (e.g. `<domain>:OPP-0001`)

<!-- A domain is a namespace, not necessarily a code repository: it may map to one repo, span
     several, or be finer than one. Say which in **About**.

     A domain is EXACTLY a directory under `domains/`. A domain index anywhere else is
     invisible to routing — the survey reports it, and a human moves it. Nothing detects
     domain-ness from a directory's contents (that heuristic existed through v2.1 and
     misidentified a docs folder as a domain while missing the real one).

     NO `Mesh vocabulary:` LINE HERE. The marker is mesh-wide and lives in the Hub ROOT
     index only; one per mesh means there is nothing to drift out of sync. -->


## Canonical context

Every entry needs **what it's about** and **when to load it**. The load condition is what
routing actually matches against — vague conditions produce vague routing.

> **The path must be a markdown link** — `[technical/repo-overview.md](technical/repo-overview.md)`,
> not `` `technical/repo-overview.md` ``. Paths are extracted with a link regex, so a
> backticked or plain-text row is **invisible**: it is never checked, and routing cannot see
> the file. An index written entirely in backticks parses to zero files while looking
> complete, and the setup check has no way to tell that from an empty mesh.

| File | About | Load when |
|---|---|---|
| [technical/repo-overview.md](technical/repo-overview.md) | <what this domain is, its place in the system, its boundaries> | <orienting here; deciding whether a change belongs> |
| [technical/system-behavior.md](technical/system-behavior.md) | <what it does at runtime: flows, orchestration> | <reasoning about runtime behavior or changing a flow> |
| … | … | … |

## Discovery artifacts

<If this team runs continuous discovery, list the OST folders and the current tree — titles
and IDs only, so an agent can reference `<domain>:OPP-NNNN` without loading the files.

If it doesn't: say **"None."** explicitly. An absent section is ambiguous; an explicit "this
team does not run discovery" tells routing there are no IDs to reference here.>

## Staging

| Location | Purpose |
|---|---|
| `staging/candidates/` | Proposed nodes and edges awaiting the human gate. Nothing here is canonical. |

## Not in this mesh

Optional but valuable: what is **deliberately** absent. A chunk whose only home would be one
of these has **no home**, and routing should say so rather than pick the nearest survivor.
Naming the gaps makes that honest instead of accidental.

> **Format: one bullet per gap, filename backticked, never markdown-linked.** A link here
> would be read as a context file that is listed but missing — the opposite of what this
> section means. The two rules pull in opposite directions on purpose: a *real* row must be
> a link, a *deliberate gap* must not be.

- `<path/to/file.md>` — <why it is absent, and where that context lives instead>
- `<path/to/folder/>` — <same>

<!-- Three states share filename-shaped syntax and are NOT the same thing:
       deliberate gap  — this section, backticked: the file should never exist here
       pending home    — a row in Canonical context: a declared home, not written yet.
                         NORMAL. Promotion creates the file when it has content for it,
                         patterns it on its siblings, and updates the row in the same PR.
       broken link     — a row in Canonical context whose file is gone: a real error
     Only the first belongs in this section.

     The last two are indistinguishable and neither blocks setup: a row whose path is a
     TYPO reads exactly like a pending home, and promotion would create a file at the
     misspelling. Nothing automated catches that -- read the paths when setup lists them. -->

<Say **"None."** if nothing is deliberately excluded — an absent section is ambiguous.>
