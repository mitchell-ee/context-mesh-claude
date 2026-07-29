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
     several, or be finer than one. Say which in **About**. -->

## Canonical context

Every entry needs **what it's about** and **when to load it**. The load condition is what
routing actually matches against — vague conditions produce vague routing.

| File | About | Load when |
|---|---|---|
| [technical/repo-overview.md](technical/repo-overview.md) | <what this domain is, its place in the system, its boundaries> | <orienting here; deciding whether a change belongs> |
| [technical/system-behavior.md](technical/system-behavior.md) | <what it does at runtime: flows, orchestration> | <reasoning about runtime behavior or changing a flow> |
| … | … | … |

## Workflows (routable processes)

Where an action item or a requirement goes. Most are **pointers to the system that really
runs the process** — the file names it and says where it lives.

| File | Process | Runs in | Route here when |
|---|---|---|---|
| [process/workflows/backlog.md](process/workflows/backlog.md) | `backlog` | <Jira (`KEY`)> | An action item needs queueing for this team. Routing = identified and attributed, **not filed**. |

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

<Optional but valuable: list what's deliberately absent. A chunk whose only home would be one
of these has **no home** — and routing should say so rather than pick the nearest survivor.
Naming the gaps makes that honest instead of accidental.>
