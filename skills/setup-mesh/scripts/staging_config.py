#!/usr/bin/env python3
"""Where the staging tree lives. ONE definition, imported by every script that needs it.

Staging defaults to `staging/` at the Hub root and in each domain. A team that already keeps
proposed material somewhere else can move the whole tree by setting one environment variable,
with no script or prompt edited.

    export CONTEXT_MESH_STAGING=_incoming        # a different name
    export CONTEXT_MESH_STAGING=docs/staging     # nested, any depth
    export CONTEXT_MESH_STAGING=a/b/c/staging    # also fine

## What is configurable, and what is not

**The staging path is a PATH, not a name** -- it may be nested to any depth. `candidates/` and
`inbox/` keep their names beneath it, so the tree relocates as a unit:

    staging/candidates/   ->   docs/staging/candidates/
    staging/inbox/        ->   docs/staging/inbox/

The path is interpreted RELATIVE TO EACH CONTAINER -- the Hub root and every `domains/<name>/`
folder -- so one variable serves them all. With `docs/staging`, the root's tree is at
`<hub>/docs/staging/` and payments' at `<hub>/domains/payments/docs/staging/`.

**Every comparison here works on segment tuples, never on a basename or a substring.** The
first version compared `os.path.basename(parent) == STAGING_DIR`, which is true only for a
single-segment value: a nested `docs/staging` made every walk find nothing, and the
misconfiguration warning then advised setting the variable to `staging` -- confidently wrong.
A substring test fails differently, matching a directory whose name merely ends with the
configured value.

**The staging walk is anchored per container, not a search for a path tail.** An unanchored
match accepted `<anything>/staging/candidates` at any depth, so a stray directory buried in a
repo was adopted as a real staging dir. `find_candidates_dirs` enumerates containers and looks
in each; `containers()` is the only place the `domains/` layout is encoded.

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

# The configurable location. Read once at import: a process that re-read this per call could
# see the path change mid-run, and two walks that disagree about where candidates live make a
# claim invisible to one of them (see `find_staging_dirs`, which is duplicated deliberately
# so that both halves stay in step).
#
# MAY BE A NESTED PATH: `docs/staging`, `.mesh/staging`, `internal/context/staging`. Every
# comparison below therefore works on a SEGMENT TUPLE, never on a basename. The first version
# of this module compared `os.path.basename(parent) == STAGING_DIR`, which is true only when
# staging is a single segment -- `docs/staging` made every walk find nothing, and the
# misconfiguration warning then confidently advised setting the variable to the wrong value.
STAGING_DIR = os.environ.get("CONTEXT_MESH_STAGING", "staging").strip("/") or "staging"

# The configured location as a tuple of path segments, which is what every comparison uses.
# Normalizes separators so a Windows-style value still compares correctly, and drops `.` and
# empty segments so `./docs//staging` means what it looks like.
STAGING_SEGMENTS = tuple(
    s for s in STAGING_DIR.replace("\\", "/").split("/") if s and s != "."
) or ("staging",)

# Re-derived from the segments so the canonical form is what gets printed and joined -- a
# value like `./docs//staging/` must not reach an index or an error message verbatim.
STAGING_DIR = "/".join(STAGING_SEGMENTS)

# Fixed names beneath the staging directory. Not configurable -- see the module docstring.
CANDIDATES_DIR = "candidates"
INBOX_DIR = "inbox"

# The environment variable a human sets, named here so error text and generated index prose
# never hardcode it in a second place.
ENV_VAR = "CONTEXT_MESH_STAGING"


def _segments(p):
    """A path as a tuple of non-empty segments, separator-normalized."""
    return tuple(s for s in str(p).replace("\\", "/").replace(os.sep, "/").split("/")
                 if s and s != ".")


def staging_root(base=""):
    """The staging directory itself, under `base` (a Hub root or a domain folder)."""
    return os.path.join(base, *STAGING_SEGMENTS) if base else os.path.join(*STAGING_SEGMENTS)


def candidates_dir(base=""):
    """`<base>/<staging>/candidates` -- where ingestion writes and promotion reads."""
    return os.path.join(base, *STAGING_SEGMENTS, CANDIDATES_DIR) if base \
        else os.path.join(*STAGING_SEGMENTS, CANDIDATES_DIR)


def inbox_dir(base=""):
    """`<base>/<staging>/inbox` -- the optional drop location."""
    return os.path.join(base, *STAGING_SEGMENTS, INBOX_DIR) if base \
        else os.path.join(*STAGING_SEGMENTS, INBOX_DIR)


def candidates_rel():
    """The staging-relative candidates path as an index would write it, with a trailing slash."""
    return f"{STAGING_DIR}/{CANDIDATES_DIR}/"


def inbox_rel():
    """The staging-relative inbox path as an index would write it, with a trailing slash."""
    return f"{STAGING_DIR}/{INBOX_DIR}/"


def is_candidates_dir(dirpath, container=None):
    """Is this path the `<staging>/candidates` directory of a container?

    `container` is the Hub root or a domain folder. When given, the match is ANCHORED: the path
    must be exactly `<container>/<staging>/candidates`. That is the correct test, and the one
    callers walking a known Hub should use.

    Without a container this falls back to matching the trailing segments, which is what a
    caller with a bare path can check. **That fallback is deliberately loose and slightly
    wrong**: it accepts `a/b/c/staging/candidates` for a single-segment configuration, so any
    stray `staging/candidates` buried in a repo would be adopted as a real staging dir. Callers
    that can supply a container should, and `find_staging_dirs` does.
    """
    segs = _segments(dirpath)
    tail = STAGING_SEGMENTS + (CANDIDATES_DIR,)
    if container is not None:
        base = _segments(os.path.abspath(container))
        full = _segments(os.path.abspath(dirpath))
        return full == base + tail
    return len(segs) >= len(tail) and segs[-len(tail):] == tail


def containers(hub_root):
    """Every container in the Hub: the root, plus each `domains/<name>/` directory.

    A container is the unit that owns a staging tree and an index. Enumerating them is what
    lets the staging walk be anchored rather than matching a floating path tail -- and it is
    also the only place the `domains/` layout is encoded, so a change there lands once.
    """
    found = [hub_root]
    domains = os.path.join(hub_root, "domains")
    if os.path.isdir(domains):
        try:
            for name in sorted(os.listdir(domains)):
                path = os.path.join(domains, name)
                if os.path.isdir(path) and not name.startswith("."):
                    found.append(path)
        except OSError:
            # An unreadable domains/ is reported by the callers' own walk error handling; it
            # must not silently truncate the container list here.
            pass
    return found


def container_of(candidates_path, hub_root):
    """The container (Hub root or domain folder) that owns a `<staging>/candidates` directory.

    Strips the CONFIGURED staging path plus `candidates`, rather than a fixed number of
    levels. `os.path.dirname(os.path.dirname(p))` was correct only while staging was a single
    segment; with `docs/staging` it stopped one level short and labelled every domain `docs`.

    Falls back to `hub_root` if the path does not sit under the expected shape, so a caller
    labelling output cannot crash on an unexpected layout.
    """
    depth = len(STAGING_SEGMENTS) + 1          # staging segments + `candidates`
    owner = os.path.abspath(candidates_path)
    for _ in range(depth):
        owner = os.path.dirname(owner)
    return owner if owner else os.path.abspath(hub_root)


def find_candidates_dirs(hub_root):
    """Every container's `<staging>/candidates` that actually exists, anchored per container.

    This replaces walking the whole tree for a path tail. The two scripts that need the staged
    pool must agree exactly about where candidates live -- if they disagree, a claim is
    invisible to one of them -- so they call THIS rather than each implementing the walk.

    Returns (found, unreadable). A container whose staging dir exists but cannot be read is
    reported, never silently skipped: "no candidates" and "could not look" are the two states
    this codebase has repeatedly conflated, and the second one ships duplicates.
    """
    found, unreadable = [], []
    for container in containers(hub_root):
        cand = candidates_dir(container)
        if not os.path.isdir(cand):
            continue
        try:
            os.listdir(cand)
        except OSError as exc:
            unreadable.append((cand, str(exc)))
            continue
        found.append(cand)
    return sorted(found), unreadable


def is_staging_path(p):
    """Does this repo-relative path point anywhere inside a staging tree?

    Used to reject a promotion target that points back into staging -- staging is output, not a
    canonical home. Matches the staging segments at ANY offset, so `docs/staging/x.md` and
    `domains/payments/docs/staging/x.md` are both caught for a `docs/staging` configuration.

    A substring test cannot do this correctly once the path has more than one segment: it
    reports a false hit on a directory whose NAME merely ends with the configured value.
    """
    segs = _segments(p)
    n = len(STAGING_SEGMENTS)
    return any(segs[i:i + n] == STAGING_SEGMENTS for i in range(len(segs) - n + 1))


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

    Returns a list of (candidates_dir, inferred_staging_path). The second element is the value
    the variable would need in order to find that directory, and inferring it correctly is the
    whole point of the warning. It must handle NESTED staging: a `candidates/` at
    `<hub>/docs/staging/candidates` needs `docs/staging`, not `staging`. Reporting only the
    parent's basename produced advice that was confidently wrong -- it told the reader to set
    the variable to `staging` for a tree that was actually at `docs/staging`.

    The inferred value is relative to the container that owns it -- the Hub root for a root
    staging dir, the domain folder for a domain's -- because that is what the variable means.
    A domain's `domains/payments/docs/staging/candidates` therefore yields `docs/staging`, the
    same value the root one yields, which is exactly right: one variable serves every container.
    """
    misplaced = []
    hub_abs = os.path.abspath(hub_root)
    # The set of correctly-placed dirs, computed with the ANCHORED test. Using the unanchored
    # `is_candidates_dir(dirpath)` here reported nothing on a nested mesh: `docs/staging/
    # candidates` still matched the default `staging` tail, so every directory looked correct
    # and the warning never fired for the exact case it was needed.
    correct = {os.path.abspath(p) for p in find_candidates_dirs(hub_root)[0]}

    for dirpath, dirnames, _ in os.walk(hub_root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        if os.path.basename(dirpath) != CANDIDATES_DIR:
            continue
        if os.path.abspath(dirpath) in correct:
            continue

        # Strip the container prefix to get the staging path as the variable would express it.
        rel = os.path.relpath(os.path.abspath(os.path.dirname(dirpath)), hub_abs)
        segs = _segments(rel)
        # A domain's dirs sit under `domains/<name>/`; drop that so the inferred value is
        # container-relative and matches what the root would need.
        if len(segs) >= 2 and segs[0] == "domains":
            segs = segs[2:]
        if segs:
            misplaced.append((dirpath, "/".join(segs)))
    return sorted(misplaced)


def misconfig_message(misplaced):
    """The warning text for `find_misplaced_candidates` output. One wording, both scripts."""
    names = sorted({inferred for _, inferred in misplaced})
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
    """Does this path START at the staging directory?

    Narrower than `is_staging_path` on purpose: an index's rows are relative to the container
    that owns them, so a staging row there is always at the top of the path. A path that merely
    contains the staging segments further down is a different case and must not be swept up.

    Compares the leading segments as a tuple, so a nested `docs/staging` matches a row reading
    `docs/staging/candidates/`. Taking only `split("/")[0]` compared `docs` against
    `docs/staging` and never matched, which let staging rows through as broken collections.
    """
    segs = _segments(p)
    n = len(STAGING_SEGMENTS)
    return len(segs) >= n and segs[:n] == STAGING_SEGMENTS
