#!/usr/bin/env python3
"""Where the staging tree lives. ONE definition, imported by every script that needs it.

Staging defaults to `staging/` at the Hub root and in each domain. A team that already keeps
proposed material somewhere else can move the whole tree by setting one environment variable,
with no script or prompt edited.

    export CONTEXT_MESH_STAGING=_incoming        # a different name
    export CONTEXT_MESH_STAGING=docs/staging     # nested, any depth
    export CONTEXT_MESH_STAGING=a/b/c/staging    # also fine

## What is configurable, and what is not

**The staging path is a PATH, not a name** -- it may be nested to any depth. The fixed names
beneath it keep their names, so the tree relocates as a unit:

    staging/candidates/    ->   docs/staging/candidates/
    staging/inbox/         ->   docs/staging/inbox/
    staging/runs/          ->   docs/staging/runs/
    staging/transcripts/   ->   docs/staging/transcripts/

The path is interpreted RELATIVE TO THE HUB ROOT. **There is exactly one staging tree**
(v0.17.0) -- domains do not have their own. With `docs/staging`, the mesh's staging is at
`<hub>/docs/staging/` and nowhere else.

**Every comparison here works on segment tuples, never on a basename or a substring.** The
first version compared `os.path.basename(parent) == STAGING_DIR`, which is true only for a
single-segment value: a nested `docs/staging` made every walk find nothing, and the
misconfiguration warning then advised setting the variable to `staging` -- confidently wrong.
A substring test fails differently, matching a directory whose name merely ends with the
configured value.

**The staging walk is anchored to the container, not a search for a path tail.** An unanchored
match accepted `<anything>/staging/candidates` at any depth, so a stray directory buried in a
repo was adopted as a real staging dir. `find_candidates_dirs` resolves the path directly;
`containers()` is the only place the container model is encoded, and is deliberately kept as a
function so reintroducing per-domain staging would be a change in one place.

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
DEFAULT_STAGING = "staging"

# The file a Hub can carry to declare its own staging location, so the setting travels with
# the repo instead of living in one person's shell. See `configure()`.
CONFIG_FILE = ".context-mesh"

# Fixed names beneath the staging directory. Not configurable -- see the module docstring.
CANDIDATES_DIR = "candidates"
INBOX_DIR = "inbox"
RUNS_DIR = "runs"

# The environment variable a human sets, named here so error text and generated index prose
# never hardcode it in a second place.
ENV_VAR = "CONTEXT_MESH_STAGING"

STAGING_DIR = DEFAULT_STAGING
STAGING_SEGMENTS = (DEFAULT_STAGING,)

# Where the current value came from, for error messages that would otherwise send a reader to
# fix the wrong thing -- "set the variable" is bad advice when a config file is overriding it.
STAGING_SOURCE = "default"


def _set_staging(value, source):
    """Set the module's staging location from a raw string. Returns the canonical form.

    Everything downstream compares SEGMENT TUPLES, so this is where a raw value becomes one.
    Normalizes separators (a Windows-style value still compares correctly) and drops `.` and
    empty segments, so `./docs//staging` means what it looks like. `STAGING_DIR` is re-derived
    from the parsed tuple rather than kept as typed -- a sloppy value must not reach an index
    row or an error message verbatim.
    """
    global STAGING_DIR, STAGING_SEGMENTS, STAGING_SOURCE
    segs = tuple(s for s in str(value).replace("\\", "/").split("/") if s and s != ".")
    if not segs:
        segs = (DEFAULT_STAGING,)
    STAGING_SEGMENTS = segs
    STAGING_DIR = "/".join(segs)
    STAGING_SOURCE = source
    return STAGING_DIR


def read_config_keys(hub_root):
    """Every `key: value` pair in `<hub>/.context-mesh`, as a dict. `{}` when there is no file.

    Deliberately not YAML. This file has a handful of keys and adding a parser dependency to
    read them would be the wrong trade -- the format is `key: value`, one per line, `#`
    comments. An unreadable or malformed file returns `{}` rather than raising: the caller
    falls back to defaults, and a mesh whose staging is genuinely at `staging/` keeps working.

    Unknown keys are returned rather than dropped, so this file can grow without old plugin
    versions choking on a key they do not know.
    """
    path = os.path.join(hub_root, CONFIG_FILE)
    try:
        with open(path) as fh:
            text = fh.read()
    except OSError:
        return {}

    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        value = value.strip().strip('"').strip("'")
        if value:
            out[key.strip()] = value
    return out


def read_config_file(hub_root):
    """The staging path declared in `<hub>/.context-mesh`, or None."""
    return read_config_keys(hub_root).get("staging") or None


def find_hub_root(start):
    """The nearest ancestor of `start` (including itself) carrying a `.context-mesh` file.

    Some entry points are pointed at a domain folder rather than the Hub root, and the config
    file lives at the root. Walking up finds it; if nothing is found, `start` is returned
    unchanged and resolution falls through to the env var or the default -- which is exactly
    the behaviour of a Hub that has no config file at all.

    Stops at the filesystem root. Does NOT look for `.git` or `context-index.md`: a Hub may be
    a subdirectory of a repo, and an index may not exist yet during setup.
    """
    cur = os.path.abspath(start)
    while True:
        if os.path.isfile(os.path.join(cur, CONFIG_FILE)):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return start
        cur = parent


def configure(hub_root):
    """Resolve where staging lives for THIS Hub. Call once, after the root is known.

    Resolution order, highest first:

        1. CONTEXT_MESH_STAGING    -- the environment, for a one-off or a CI override
        2. <hub>/.context-mesh     -- the Hub's own declaration, committed to the repo
        3. `staging`               -- the default

    **Why a file and not just the variable.** An environment variable is per-shell, so the
    setting had to be re-exported in every terminal, every CI job, and every agent run that
    touched the mesh. Forgetting it did not fail loudly: the staged pool came back empty,
    which is indistinguishable from a mesh that has never ingested anything, and dedup then
    ran against nothing and shipped duplicates. A file in the Hub travels with the repo, so
    cloning it is enough -- no tooling to install, and it works in CI and headless runs where
    a `.envrc` would not.

    Called once per process, after the Hub root is parsed from argv -- not at import, because
    the file lives AT the Hub root and nothing knows where that is until then. Re-reading per
    call would let the path change mid-run, and two walks that disagree about where candidates
    live make a claim invisible to one of them.
    """
    env = os.environ.get(ENV_VAR)
    if env and env.strip():
        return _set_staging(env.strip(), "environment")

    from_file = read_config_file(hub_root)
    if from_file:
        return _set_staging(from_file, CONFIG_FILE)

    return _set_staging(DEFAULT_STAGING, "default")


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


def runs_rel():
    """The staging-relative runs path as an index would write it, with a trailing slash."""
    return f"{STAGING_DIR}/{RUNS_DIR}/"


def transcripts_rel():
    """The staging-relative transcripts path as an index would write it, trailing slash.

    Exists even though setup never CREATES this directory. Listing and creating are separate
    questions: the index's Staging table is backticked prose describing what the staging tree
    holds, not a routing input, so naming an on-demand directory advertises nothing. Omitting
    it implied `transcripts/` was routable in a way the other three are not, which is backwards
    -- promotion refuses every staging path alike.
    """
    return f"{STAGING_DIR}/{TRANSCRIPTS_DIR}/"


# ---------------------------------------------------------------------------
# Archival policy: does a source system hold the original, or must the Hub?
# ---------------------------------------------------------------------------
#
# `source_kind` already decides this PER TRANSCRIPT and stays the authority. What the team
# configures is only the DEFAULT for material that arrives with no datastore behind it --
# which in practice means the inbox, where a dropped file is the only copy anyone knows about.
#
# `trusted` means "our source system keeps originals, so point at it and store nothing."
# `hub` means "keep our own copy, because nothing else reliably will."
#
# The default is `hub`, and it is the safe direction: an unnecessary archive is a redundant
# file a team can delete, while a missing one is a transcript that no longer exists anywhere.
# Those errors are not equal, so the default is not a coin flip.
ARCHIVE_KEY = "archive_inbox"
ARCHIVE_TRUSTED = "trusted"
ARCHIVE_HUB = "hub"
DEFAULT_ARCHIVE = ARCHIVE_HUB

# Fixed name beneath staging, alongside `candidates/` and `inbox/`. Where an archived
# transcript lands so it outlives the run that ingested it.
TRANSCRIPTS_DIR = "transcripts"


def archive_policy(hub_root):
    """`hub` or `trusted` -- whether the Hub keeps its own copy of sourceless material.

    Unrecognized values fall back to `hub` rather than raising. A typo'd policy must not
    silently become "store nothing": that is the one direction where the mistake is
    unrecoverable, because the transcript it declined to keep is gone.
    """
    value = read_config_keys(hub_root).get(ARCHIVE_KEY, DEFAULT_ARCHIVE).strip().lower()
    return value if value in (ARCHIVE_TRUSTED, ARCHIVE_HUB) else DEFAULT_ARCHIVE


def transcripts_dir(base=""):
    """`<base>/<staging>/transcripts` -- where archived transcripts outlive their run."""
    return os.path.join(base, *STAGING_SEGMENTS, TRANSCRIPTS_DIR) if base \
        else os.path.join(*STAGING_SEGMENTS, TRANSCRIPTS_DIR)


def runs_dir(base=""):
    """`<base>/<staging>/runs` -- one directory per ingestion run, holding its placements.

    A run survives the session that created it: the placements JSON records a decision per
    chunk, so a walk can be resumed, or an async review can be picked up days later.
    """
    return os.path.join(base, *STAGING_SEGMENTS, RUNS_DIR) if base \
        else os.path.join(*STAGING_SEGMENTS, RUNS_DIR)


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
    """The containers that own a staging tree and an index. **The Hub root, and only it.**

    Centralized as of v0.17.0. Until then a domain was a container too: each got its own
    `context-index.md` and its own `staging/candidates/`. That split was removed because
    neither benefit claimed for it was real --

      * **Progressive disclosure did not apply.** Routing reads the root index AND every
        domain index on every run, so splitting saved nothing and only made N places to edit.
      * **Per-team ownership did not exist.** No CODEOWNERS was ever generated, and
        `vocabulary.md` is explicit that ownership is declared via `owned-by` metadata,
        "not structural -- the filesystem does not enforce it."

    while the costs were real: N indexes to keep valid, and two staging walks that had to
    agree exactly or a claim went invisible to one of them (fail-open #16).

    This function is kept rather than inlined. It is the ONE place the container model is
    encoded, so a future decision to reintroduce per-team review -- a second gate after
    ingestion, or a domain-targeted ingestion run -- changes this and the callers follow.

    `domains/<name>/` still exists and still holds context files; it is simply no longer a
    container. A domain remains exactly a directory under `domains/`.
    """
    return [hub_root]


def find_candidates_dirs(hub_root):
    """The Hub's `<staging>/candidates` -- a list, because callers iterate it.

    Returns (found, unreadable), a list of at most one. Kept plural because both callers walk
    the result, and because the container model is deliberately left as the seam to change if
    per-domain staging ever returns.

    An existing-but-unreadable staging dir is REPORTED, never silently skipped: "no
    candidates" and "could not look" are the two states this codebase has repeatedly
    conflated, and the second one ships duplicates.
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

    The inferred value is relative to the Hub root, because that is what the variable means.

    Since v0.17.0 this also catches the OTHER misplacement: a `candidates/` under
    `domains/<name>/`, left over from when a domain was a container. Staging is centralized
    now, so those candidates are invisible to promotion and dedup -- exactly the condition
    this function exists to make loud. They are reported with `domain: <name>` as the inferred
    value, which no `export` line can fix, so `misconfig_message` names the real remedy.
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

        # Strip the Hub prefix to get the staging path as the variable would express it.
        rel = os.path.relpath(os.path.abspath(os.path.dirname(dirpath)), hub_abs)
        segs = _segments(rel)

        # A leftover per-domain staging tree. Relocating the variable cannot reach it -- the
        # candidates have to MOVE to the root -- so it is flagged as its own kind of finding.
        if len(segs) >= 2 and segs[0] == "domains":
            misplaced.append((dirpath, f"domain: {segs[1]}"))
            continue

        if segs:
            misplaced.append((dirpath, "/".join(segs)))
    return sorted(misplaced)


def misconfig_message(misplaced):
    """The warning text for `find_misplaced_candidates` output. One wording, both scripts.

    Two remedies, because there are two causes and only one of them is a configuration fix. A
    leftover per-domain staging tree cannot be reached by pointing the config at it -- the
    candidates must move to the Hub root -- so suggesting a setting there would be advice that
    silently does nothing.

    The suggested fix names the source that is actually in effect. Telling someone to export a
    variable when a committed `.context-mesh` is overriding their shell sends them to edit the
    wrong thing and watch nothing change.
    """
    domain_hits = sorted({inf for _, inf in misplaced if inf.startswith("domain: ")})
    path_hits = sorted({inf for _, inf in misplaced if not inf.startswith("domain: ")})

    lines = [
        f"WARNING: no candidates found under `{STAGING_DIR}/`, but {len(misplaced)} "
        f"`{CANDIDATES_DIR}/` director(ies) exist elsewhere.",
    ]

    if path_hits:
        lines += [
            f"  Found under: {', '.join(path_hits)}.",
            f"  Staging resolves to `{STAGING_DIR}/` (from: {STAGING_SOURCE}). If this mesh "
            f"keeps its staging tree somewhere else, declare it:",
        ]
        if STAGING_SOURCE == "environment":
            lines += [
                f"      export {ENV_VAR}={path_hits[0]}",
                f"  -- or drop the variable and commit it to `{CONFIG_FILE}` instead, which "
                f"travels with the repo:",
                f"      staging: {path_hits[0]}",
            ]
        else:
            lines += [
                f"  In `{CONFIG_FILE}` at the Hub root:",
                f"      staging: {path_hits[0]}",
                f"  -- or, for a one-off:  export {ENV_VAR}={path_hits[0]}",
            ]

    if domain_hits:
        names = ", ".join(h.split("domain: ", 1)[1] for h in domain_hits)
        lines += [
            f"  Per-domain staging found in: {names}.",
            "  Staging is CENTRALIZED (v0.17.0) -- only the Hub root has a staging tree, and "
            "no environment variable reaches these.",
            f"  Move their candidates into `{candidates_rel()}` at the Hub root and delete "
            "the empty domain staging folders.",
        ]

    lines.append(
        "  Until then these candidates are INVISIBLE to dedup and promotion -- which looks "
        "exactly like a mesh that has never ingested anything."
    )
    return "\n".join(lines)


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
