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
stub at high confidence. Setup creates containers; promotion creates files, once it has
content for a home the index already declares.

So: this script will create `staging/candidates/` and a stub `context-index.md` with NO
entries. It will never create `technical/repo-overview.md`, and it will never add a row to
the index's context table.

IDEMPOTENT. A second run does nothing and reports nothing changed. That is what makes "run
setup again to add a domain" the add path rather than a second mode -- and it is why a re-run
produces no PR: there is no diff.

All context lives in the Hub. A domain is a FOLDER under `domains/`, not a separate repo
(v2.2), so the only structural distinction is root-vs-domain: which index template is
written, and where the folder goes.

Usage:
    scaffold_domain.py <hub-root>                      # stand up the Hub root
    scaffold_domain.py <hub-root> <domain> [<domain>...]
    scaffold_domain.py <hub-root> <domain> --dry-run

Exit codes: 0 = done (changed or already correct), 2 = bad input.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import staging_config  # noqa: E402  (one definition of where staging lives, never a second)

INDEX = "context-index.md"
DOMAINS_DIR = "domains"

# The vocabulary version this scaffold writes into a new root index's `Mesh vocabulary:` line.
# Bump it when a vocabulary change lands, and ship a migration alongside -- see
# `migrations/README.md`. The marker prompts; it never selects (guards key on data shape).
VOCABULARY = "v2.5"

# Directories every container gets. Empty ones are honest: nothing routes to a dir.
#
# The root and a domain took different lists until v2.2, because a domain also got
# `process/workflows/` and the root deliberately did not. With the workflow layer deferred
# the two are identical, and survey_mesh.py imports this rather than restating it -- the
# survey once hardcoded its own copy and promised a directory this script would not create
# (Minotaur finding 5).
#
# THE ROOT ALSO GETS `inbox/`, because the ROOT index template lists `<staging>/inbox/`. A row
# naming a directory that setup does not create is precisely the Minotaur-5 failure above, in
# the same file -- `a missing directory is an error` (file-taxonomy.md), so an advertised inbox
# must exist. Whenever a row is added to a template, add its directory here.
ROOT_DIRS = [staging_config.candidates_dir(), staging_config.inbox_dir()]

# A DOMAIN GETS NO STAGING AND NO INDEX (v0.17.0). Staging and the index are centralized at
# the Hub root; a domain is a folder of context files and an ID namespace, not a container.
#
# It gets `technical/` and nothing more. That is not a claim about what the domain contains --
# it is the one folder the taxonomy shows for every domain, and it exists so the domain is a
# real, git-trackable directory rather than an empty name. Everything else (`product/`,
# `process/`) is added by the team when they have something to put in it. Scaffolding the full
# set would author structure nobody asked for, which is the failure this script exists to
# avoid: setup creates containers, never claims.
DOMAIN_DIRS = ["technical"]

ROOT_INDEX = """# AI Hub — context index

The one place all context lives. Cross-cutting context (shared by every team) lives at this
root; anything specific to one thing lives in its **domain folder under `domains/`** — an
optional layer, absent in a mesh whose context is all cross-cutting.

This may be a repo of its own, or the code repo itself: **in a monorepo the Hub root is the
repo root**, and this file sits beside the build manifest.

**This file is the manifest, the routing input, and the progressive-disclosure contract.**
Read it first; load only what the current task needs. Do not load the whole mesh.

## Identity

- **Role:** AI Hub — the one repo where all context lives
- **Owns:** cross-cutting canonical context — the context that belongs to everybody
- **Mesh vocabulary:** {vocabulary}

<!-- Mesh vocabulary is the schema version this mesh's content is written in. Setup reads it
     to tell whether the mesh predates a convention change, and prompts if it does. It is a
     PROMPT TRIGGER, NOT A SELECTOR: every migration decides for itself whether it applies by
     inspecting the data, so a mesh with no marker, or one already fixed by hand, still
     behaves correctly. Setup rewrites this line only after the data actually checks out. -->

<!-- There was a `PII policy: strip | enrich` line here through v2.3. It is gone (v2.4):
     ingestion does nothing to a transcript before extracting from it. Retention is the
     team's decision about their own repo -- a mesh that does not want transcripts in its
     history can .gitignore them. -->

## Domains

<!-- SCAFFOLD: no domains yet. This list is the one piece of mesh-wide manifest that is
     not a file list: which domains exist is a per-engagement decision (one per code repo,
     one per business domain, a mix, or NONE). Add a row per folder under `domains/`.

     DOMAINS ARE OPTIONAL, and leaving this table empty is a complete answer. If all your
     context is cross-cutting — the usual case for a monorepo, where there is one thing to
     describe — there is no `domains/` directory and nothing is missing. Nothing will ask
     you to add one.

     A domain is exactly a directory under `domains/` — nothing else is one, whatever it
     contains or is named. -->

| Domain | About | Owned by |
|---|---|---|

## Cross-cutting canonical context

<!-- SCAFFOLD: no entries yet. Setup does not author context files — the file list is
     yours to decide. Add a row only when the file exists and says something.

     This root holds context that governs everybody (personas, target architecture, coding
     standards). Context about one domain belongs in that domain's folder, not here.

     EVERY PATH MUST BE A MARKDOWN LINK — see the note in a domain index. A backticked or
     plain-text path is invisible to the checker and to routing. -->

| File | About | Load when |
|---|---|---|

<!-- A STARTING SET, not a specification. Every line below is optional; a team with four
     context files and a team with twenty are both correctly configured. Uncomment a row
     when the file exists, delete the ones you do not want, and rename freely to match what
     your team already calls things.

     Start with the HIGHEST-LEVEL file that covers an area. `technical/architecture.md` is a
     better start than six separate architecture files -- split later, if one grows too big
     to load for a single task. Starting with the split version is how a mesh ends up with
     eighteen files nobody filled in.

| [product/business-context.md](product/business-context.md) | Why this exists, what problem it solves, who depends on it | orienting on the product; weighing whether something is in scope |
| [product/glossary.md](product/glossary.md) | Domain terms and shared vocabulary | reading anything that uses house jargon |
| [product/design-principles.md](product/design-principles.md) | Product values, and how tradeoffs get resolved | making a judgment call between competing options |
| [technical/architecture.md](technical/architecture.md) | How the system is put together: components, how they talk | changing structure; adding a component |
| [technical/coding-standards.md](technical/coding-standards.md) | Language and style conventions, patterns, anti-patterns | writing or reviewing code |
| [technical/testing-standards.md](technical/testing-standards.md) | Test types, coverage expectations, CI integration | writing tests; changing the test setup |
| [technical/integration-map.md](technical/integration-map.md) | Cross-system dependencies: APIs, data stores, queues, jobs | tracing a dependency; changing an interface |
| [process/ways-of-working.md](process/ways-of-working.md) | How work flows from idea to deployed; rituals, handoffs | onboarding; questioning who decides what |
| [governance/data-handling.md](governance/data-handling.md) | Data classification, residency, encryption | touching customer or regulated data |

     COLLECTIONS go in their own section, not this table -- a folder of same-typed files
     gets one row for the folder, with a trailing slash. Personas are the common case:

| [product/personas/](product/personas/) | `{{slug}}.md` | Customer and stakeholder personas, one per file | reasoning about who a user is, or whose problem a change solves |
-->


## Staging

| Location | Purpose |
|---|---|
| `{candidates}` | Cross-cutting proposals from ingestion, awaiting the human gate. Nothing here is canonical. |
| `{inbox}` | Optional drop location for raw material awaiting processing. |

<!-- The staging tree may live somewhere other than `staging/`. It is set in ONE place --
     the `{env_var}` environment variable -- and the whole tree moves together,
     keeping `candidates/` and `inbox/` beneath it. If you change the paths above, set that
     variable to match: this table documents the location, but the scripts read the variable,
     and a mismatch means the index describes a folder nothing reads or writes. -->

## Not in this mesh

<!-- SCAFFOLD: unanswered. Naming the deliberate gaps is what lets routing report
     "no home in this mesh" instead of routing to the closest surviving file.

     FORMAT — one bullet per gap, and DO NOT markdown-link the filename. A link here
     would be read as a context file that is listed but missing. Backticks, deliberately:

       - `governance/data-handling.md` — handled by the platform team's own repo, not here
       - `product/pricing.md` — no pricing context in this mesh; ask the commercial team

     Three states share the filename-shaped syntax and mean different things: a deliberate
     gap (this section — the file should never exist here), a pending home (a row in the
     context table whose file has not been written yet), and a broken link (a row whose
     file was deleted). Only the first belongs here. -->
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

    # ONLY THE ROOT GETS AN INDEX (v0.17.0). There is one index for the whole mesh; a domain's
    # context files are declared in it with `domains/<name>/...` paths. A domain folder with no
    # index is the normal, correct state -- not a half-finished container.
    if not is_root:
        return created, skipped

    # CAPTURE a non-default staging path into the repo, so it stops being per-shell state.
    # The variable has to be re-exported in every terminal, CI job, and agent run; forgetting
    # it made the staged pool come back empty, which is indistinguishable from a mesh that has
    # never ingested. Writing it here means the next person to clone the Hub gets the right
    # layout with nothing to install and nothing to remember.
    #
    # Only when it is NOT the default: a Hub at plain `staging/` needs no file, and creating
    # one everywhere would be clutter that most meshes never edit. Never overwritten -- if the
    # file exists it is the team's, and it is what produced this value in the first place.
    cfg_path = os.path.join(path, staging_config.CONFIG_FILE)
    if staging_config.STAGING_DIR != staging_config.DEFAULT_STAGING:
        if os.path.isfile(cfg_path):
            skipped.append(staging_config.CONFIG_FILE)
        else:
            created.append(staging_config.CONFIG_FILE)
            if not dry_run:
                with open(cfg_path, "w") as fh:
                    fh.write(
                        "# Where this mesh keeps its staging tree, relative to the Hub root.\n"
                        "# Committed so the setting travels with the repo instead of living\n"
                        f"# in one person's shell. {staging_config.ENV_VAR} overrides it.\n"
                        f"staging: {staging_config.STAGING_DIR}\n"
                    )

    index_path = os.path.join(path, INDEX)
    if os.path.isfile(index_path):
        # NEVER rewrite an existing index. It is authored -- the team's entries, load
        # conditions, and identity live there. Idempotence here is not "make it match the
        # template"; it is "leave it completely alone".
        skipped.append(INDEX)
    else:
        created.append(INDEX)
        if not dry_run:
            body = ROOT_INDEX.format(vocabulary=VOCABULARY,
                                     candidates=staging_config.candidates_rel(),
                                     inbox=staging_config.inbox_rel(),
                                     env_var=staging_config.ENV_VAR)
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

    # Resolve staging for THIS Hub, then rebuild ROOT_DIRS from the resolved value. The
    # constant is computed at import, before any Hub root is known, so it holds the DEFAULT
    # path until this runs -- scaffolding a Hub whose `.context-mesh` says `docs/staging`
    # would otherwise create `staging/` and leave the index pointing at a folder that does
    # not exist.
    staging_config.configure(hub_root)
    global ROOT_DIRS
    ROOT_DIRS = [staging_config.candidates_dir(), staging_config.inbox_dir()]

    # The Hub root is checked and stood up on EVERY run, single-domain or many. It is just
    # another idempotent step that happens to run first.
    targets = [(hub_root, "hub", True)]
    for d in domains:
        if os.sep in d or d in (".", ".."):
            print(f"error: domain must be a plain folder name, got: {d}", file=sys.stderr)
            return 2
        # Domains live under `domains/`, never at the root beside the cross-cutting
        # folders (v2.2). The explicit container is what removes the need to detect
        # domain-ness at all -- see survey_mesh.discover().
        targets.append((os.path.join(hub_root, DOMAINS_DIR, d), d, False))

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
