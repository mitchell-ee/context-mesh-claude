#!/usr/bin/env python3
"""Create the containers the Hub and its domains need. Idempotent. Never authors content.

This is the writing half of setup, and the line it holds is the whole reason it can run
unattended:

    IT CREATES CONTAINERS. IT NEVER CREATES A CLAIM.

A container is a directory, or an index whose entries are empty. Neither asserts anything
false: nothing routes *to* a directory, and an index with no entries honestly says "this
domain has no context yet" -- which is exactly the gap the survey reports.

A claim is a context file the index lists. `business-context.md` existing and saying nothing
is a LIE THE SKILL BELIEVES: routing reads the index, so ingestion would land a fact in a
stub at high confidence. That is build-scope decision 4, and it survives unchanged.

So: this script will create `staging/candidates/`, `process/workflows/`, and a stub
`context-index.md` with NO entries. It will never create `technical/repo-overview.md`, and
it will never add a row to the index's context table.

IDEMPOTENT. A second run does nothing and reports nothing changed. That is what makes "run
setup again to add a domain" the add path rather than a second mode -- and it is why a re-run
produces no PR: there is no diff.

All context lives in the Hub. A domain is a FOLDER inside it, not a separate repo, so the
only structural distinction is root-vs-domain: the root holds cross-cutting context and has
no team backlog (`Todo`s route to the domain that owns the work).

Usage:
    scaffold_domain.py <hub-root>                      # stand up the Hub root
    scaffold_domain.py <hub-root> <domain> [<domain>...]
    scaffold_domain.py <hub-root> <domain> --dry-run

Exit codes: 0 = done (changed or already correct), 2 = bad input.
"""

import os
import sys

INDEX = "context-index.md"

# Directories every domain has. Empty ones are honest: nothing routes to a dir.
DOMAIN_DIRS = [
    os.path.join("staging", "candidates"),
    os.path.join("process", "workflows"),
]

# The root has no team backlog by design: Todos route to the domain that owns the work.
ROOT_DIRS = [os.path.join("staging", "candidates")]

DOMAIN_INDEX = """# {name} — context index

Read this first; load only what the current task needs.

**This file is the manifest, the routing input, and the progressive-disclosure contract.**
It is what ingestion reads to decide where a fact belongs — and the *only* thing it reads
to decide that. A file not listed here is invisible to routing.

## Domain identity

- **Domain:** `{name}`
- **About:** <one line — what this domain covers>
- **Owned by:** <team>
- **ID prefix:** `{name}:` (e.g. `{name}:OPP-0001`)

<!-- A domain is a namespace, not necessarily a code repository. It may map to one repo,
     span several, or be finer than one. Say which here, in **About**. -->

## Canonical context

<!-- SCAFFOLD: no entries yet. This is an honest empty index, not a broken one.

     Setup does NOT invent rows here. Every entry needs two things only the team knows:
       - **About** — what the file covers, in one line
       - **Load when** — the progressive-disclosure condition routing matches against

     Add a row only when the file it names actually exists and says something. A row
     pointing at a stub is worse than no row: routing would send facts there. -->

| File | About | Load when |
|---|---|---|

## Workflows (routable processes)

<!-- SCAFFOLD: none declared. Until there is one, `Todo`s cannot route anywhere —
     a Todo may only be `routed-to` a Workflow. Knowledge and facts route fine.

     Run setup-mesh job 2 to declare where this team queues work. -->

| File | Process | Runs in | Route here when |
|---|---|---|---|

## Discovery artifacts

<!-- SCAFFOLD: unanswered. Say **"None."** if this team does not run continuous
     discovery — an explicit "none" tells routing there are no IDs to reference,
     whereas an absent answer is ambiguous. -->

## Staging

| Location | Purpose |
|---|---|
| `staging/candidates/` | Proposed nodes and edges awaiting the human gate. Nothing here is canonical. |

## Not in this mesh

<!-- SCAFFOLD: unanswered, and worth answering. Listing what is deliberately absent is
     what lets routing say "no home" honestly instead of picking the nearest survivor. -->
"""

ROOT_INDEX = """# AI Hub — context index

The single repo holding all context. Cross-cutting context (shared by every team) lives at
this root; everything specific to one thing lives in its **domain folder** alongside.

**This file is the manifest, the routing input, and the progressive-disclosure contract.**
Read it first; load only what the current task needs. Do not load the whole mesh.

## Identity

- **Role:** AI Hub — the one repo where all context lives
- **Owns:** cross-cutting canonical context — the context that belongs to everybody
- **PII policy:** strip

<!-- PII policy is read by the transcript structurer (prompts/structure-transcript.md) and by
     ingest-conversation. `strip` (the default) redacts speaker identity; `enrich` preserves
     who-said-what and takes on client + DPO custody obligations (consent, retention,
     right-to-erasure). Secrets and non-participant PII are redacted under either policy. Do
     not switch to `enrich` without a deliberate data-custody decision. -->

## Domains

<!-- SCAFFOLD: no domains yet. This list is the one piece of mesh-wide manifest that is
     not a file list: which domains exist is a per-engagement decision (one per code repo,
     one per business domain, or a mix). Add a row per domain folder. -->

| Domain | About | Owned by |
|---|---|---|

## Cross-cutting canonical context

<!-- SCAFFOLD: no entries yet. Setup does not author the manifest — the file list is
     per-implementation config the engagement decides.

     This root holds context that governs everybody (personas, target architecture, coding
     standards). Context about one domain belongs in that domain's folder, not here. Add a
     row only when the file exists and says something. -->

| File | About | Load when |
|---|---|---|

## Staging

| Location | Purpose |
|---|---|
| `staging/candidates/` | Cross-cutting proposals from ingestion, awaiting the human gate. Nothing here is canonical. |

## Not in this mesh

<!-- SCAFFOLD: unanswered. Naming the deliberate gaps is what lets routing report
     "no home in this mesh" instead of routing to the closest surviving file. -->
"""


def scaffold(path, name, is_root, dry_run=False):
    """Create missing containers. Returns (created, skipped) lists of relative paths."""
    created, skipped = [], []

    for d in (ROOT_DIRS if is_root else DOMAIN_DIRS):
        full = os.path.join(path, d)
        if os.path.isdir(full):
            skipped.append(d + "/")
            continue
        created.append(d + "/")
        if not dry_run:
            os.makedirs(full, exist_ok=True)
            # Git does not track empty dirs, and an untracked staging dir means the first
            # ingestion run creates it in whatever branch happens to be checked out. A
            # .gitkeep makes the container real in the repo, not just on disk.
            with open(os.path.join(full, ".gitkeep"), "w"):
                pass

    index_path = os.path.join(path, INDEX)
    if os.path.isfile(index_path):
        # NEVER rewrite an existing index. It is authored -- the team's entries, load
        # conditions, and identity live there. Idempotence here is not "make it match the
        # template"; it is "leave it completely alone".
        skipped.append(INDEX)
    else:
        created.append(INDEX)
        if not dry_run:
            body = ROOT_INDEX if is_root else DOMAIN_INDEX.format(name=name)
            with open(index_path, "w") as fh:
                fh.write(body)

    return created, skipped


def main():
    argv = sys.argv[1:]
    dry_run = "--dry-run" in argv
    args = [a for a in argv if not a.startswith("--")]

    if not args:
        print(__doc__)
        return 2

    hub_root, domains = args[0], args[1:]

    if not os.path.isdir(hub_root):
        print(f"error: not a directory: {hub_root}", file=sys.stderr)
        return 2

    # The Hub root is checked and stood up on EVERY run, single-domain or many. It is just
    # another idempotent step that happens to run first.
    targets = [(hub_root, "hub", True)]
    for d in domains:
        if os.sep in d or d in (".", ".."):
            print(f"error: domain must be a plain folder name, got: {d}", file=sys.stderr)
            return 2
        targets.append((os.path.join(hub_root, d), d, False))

    any_change = False
    for path, name, is_root in targets:
        if not dry_run:
            os.makedirs(path, exist_ok=True)
        elif not os.path.isdir(path):
            print(f"{name}: would create the domain folder itself")
        created, skipped = scaffold(path, name, is_root, dry_run=dry_run)
        label = "(hub root)" if is_root else name
        verb = "would create" if dry_run else "created"

        if created:
            any_change = True
            print(f"{label}: {verb} {len(created)}")
            for c in created:
                print(f"    + {c}")
        else:
            print(f"{label}: no change -- already scaffolded")
        if skipped:
            for s in skipped:
                print(f"    = {s} (exists, untouched)")
        print()

    if not any_change:
        print("Nothing changed. A re-run over a scaffolded mesh is a no-op -- which is")
        print("why it produces no PR: there is no diff to review.")
    else:
        print("Containers only. No context file was authored, and no index row was added --")
        print("those are claims, and only the team that knows the answer can make them.")
        print("Run survey_mesh.py to see what still needs a human.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
