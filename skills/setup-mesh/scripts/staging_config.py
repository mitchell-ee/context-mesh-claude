#!/usr/bin/env python3
"""Where the staging tree lives. ONE definition, imported by every script that needs it.

Staging defaults to `staging/` at the Hub root and in each domain. A team that already keeps
proposed material somewhere else -- `inbox/`, `_incoming/`, `.mesh-staging/` -- can move the
whole tree by setting one environment variable, with no script or prompt edited.

    export CONTEXT_MESH_STAGING=_incoming

## What is configurable, and what is not

Only the TOP segment moves. `candidates/` and `inbox/` keep their names beneath it, so the
tree relocates as a unit:

    staging/candidates/   ->   _incoming/candidates/
    staging/inbox/        ->   _incoming/inbox/

Two scripts locate per-domain staging by walking for a directory named `candidates` whose
PARENT is the staging directory. Letting the leaf name vary too would leave that walk with no
fixed thing to match on, and the walk is what makes domains work without a registry.

## `state: staging` is a different thing with the same word

A candidate's frontmatter carries `state: staging`, and that is a value in the vocabulary, not
a path. It does not live here and must not move when the directory does -- relocating a folder
would otherwise reclassify every existing candidate as promoted.

## Why a variable AND an index entry

The root `context-index.md` declares the staging path for humans; this module is what scripts
read. They are not redundant, because **the scripts that most need this path do not read the
index at all** -- `classify_candidates.py` and `collect_dedup_targets.py` walk the filesystem,
and `collect_dedup_targets.py` walks the whole Hub looking for per-domain staging dirs, so
resolving the path from an index would mean parsing one index per domain just to find a folder.

The index entry therefore carries a note telling anyone who edits it to set the variable to
match. A mismatch is the failure mode worth designing against: the index would document one
location while every script used another.
"""

import os

# The configurable segment. Read once at import: a process that re-read this per call could
# see the path change mid-run, and two walks that disagree about where candidates live make a
# claim invisible to one of them (see `find_staging_dirs`, which is duplicated deliberately
# so that both halves stay in step).
STAGING_DIR = os.environ.get("CONTEXT_MESH_STAGING", "staging").strip("/") or "staging"

# Fixed names beneath the staging directory. Not configurable -- see the module docstring.
CANDIDATES_DIR = "candidates"
INBOX_DIR = "inbox"

# The environment variable a human sets, named here so error text and generated index prose
# never hardcode it in a second place.
ENV_VAR = "CONTEXT_MESH_STAGING"


def staging_root(base=""):
    """The staging directory itself, under `base` (a Hub root or a domain folder)."""
    return os.path.join(base, STAGING_DIR) if base else STAGING_DIR


def candidates_dir(base=""):
    """`<base>/<staging>/candidates` -- where ingestion writes and promotion reads."""
    return os.path.join(base, STAGING_DIR, CANDIDATES_DIR) if base else \
        os.path.join(STAGING_DIR, CANDIDATES_DIR)


def candidates_rel():
    """The staging-relative candidates path as an index would write it, with a trailing slash."""
    return f"{STAGING_DIR}/{CANDIDATES_DIR}/"


def inbox_rel():
    """The staging-relative inbox path as an index would write it, with a trailing slash."""
    return f"{STAGING_DIR}/{INBOX_DIR}/"


def is_candidates_dir(dirpath):
    """Is this path a `<staging>/candidates` directory?

    Matches on the last two segments rather than on a prefix, because the same shape appears at
    the Hub root and inside every domain, and neither position is privileged.
    """
    return (os.path.basename(dirpath) == CANDIDATES_DIR and
            os.path.basename(os.path.dirname(dirpath)) == STAGING_DIR)


def is_staging_path(p):
    """Does this repo-relative path point anywhere inside a staging tree?

    Used to reject a promotion target that points back into staging -- staging is output, not a
    canonical home. Checks a leading segment and an interior one, so both `staging/x.md` and
    `domains/payments/staging/x.md` are caught.
    """
    norm = str(p).replace(os.sep, "/")
    return norm.startswith(f"{STAGING_DIR}/") or f"/{STAGING_DIR}/" in norm


def find_misplaced_candidates(hub_root):
    """Directories named `candidates` whose parent is NOT the configured staging dir.

    This exists because of a fail-open bug found by testing, not by reading. Relocate a mesh's
    staging tree and forget to set the variable (or set it, then unset it in a later shell) and
    the walk finds nothing -- which is INDISTINGUISHABLE from a legitimately empty mesh that has
    never ingested anything. The dedup pool silently collapses to zero, every prior candidate
    goes uncompared, and the script exits 0. Verified: five candidates vanished with no warning.

    "Zero staging dirs" cannot itself be an error -- a fresh mesh really does have none, and
    making it one would be a fail-CLOSED bug of the kind this codebase has twice. But "zero
    where the variable says, and some under ANOTHER name" is not ambiguous at all. That is a
    misconfiguration, and it is reportable without guessing.

    Returns a list of (candidates_dir, its_parent_name). Callers decide how loudly to say it.
    """
    misplaced = []
    for dirpath, dirnames, _ in os.walk(hub_root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        if os.path.basename(dirpath) != CANDIDATES_DIR:
            continue
        parent = os.path.basename(os.path.dirname(dirpath))
        if parent != STAGING_DIR:
            misplaced.append((dirpath, parent))
    return sorted(misplaced)


def misconfig_message(misplaced):
    """The warning text for `find_misplaced_candidates` output. One wording, both scripts."""
    names = sorted({parent for _, parent in misplaced})
    return (
        f"WARNING: no candidates found under `{STAGING_DIR}/`, but {len(misplaced)} "
        f"`{CANDIDATES_DIR}/` director(ies) exist under: {', '.join(names)}.\n"
        f"  Staging is configured as `{STAGING_DIR}/` via {ENV_VAR}. If this mesh keeps its "
        f"staging tree somewhere else, set it:\n"
        f"      export {ENV_VAR}={names[0]}\n"
        f"  Until then these candidates are INVISIBLE to dedup and promotion -- which looks "
        f"exactly like a mesh that has never ingested anything."
    )


def is_staging_first_segment(p):
    """Is the FIRST segment of this path the staging directory?

    Narrower than `is_staging_path` on purpose: an index's rows are relative to the container
    that owns them, so a staging row there is always top-level. A domain path that merely
    contains `staging` further down is a different case and must not be swept up.
    """
    return str(p).replace(os.sep, "/").split("/")[0] == STAGING_DIR
