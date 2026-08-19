#!/usr/bin/env python3
"""List what a dedup pass must read -- and nothing else. TWO read sets, not one.

A claim can already exist in two places, and missing either one ships a duplicate:

  CANONICAL  the target file routing chose. "Does decided context already say this?"
  STAGED     unpromoted candidates from EARLIER INGESTIONS. "Did a previous conversation
             already produce this claim, still sitting in staging unpromoted?"

The second set exists because the first cannot cover it. Dedup compares against canonical
context, but a candidate that has not been promoted yet is BY DEFINITION not in canonical
context -- so two conversations three weeks apart could each produce the same claim and
both would land in staging, unlinked, with a human left to spot it at promotion time weeks
later. (Added 2026-08-14.)

## The two sets are bounded differently, on purpose

CANONICAL is N-chunks-bounded: routing picked exactly one file per chunk, and this script
derives the list from the placements, so the read set is a consequence of the routing
decision rather than a judgement call made in the moment. Opening one more file to be sure,
then another, is how index-only routing erodes into the whole-mesh load the project exists
to kill.

STAGED is pool-bounded, and that is a deliberate, narrower claim than "unbounded". Staging
is a fixed-size pool a human actively drains, not the mesh: candidates run ~2 KB, so even a
neglected pool of 100 is ~200 KB. Scoping this read to same-target candidates only was
considered and REJECTED -- it would silently miss the case that most needs catching, where
two conversations describe the same fact and get routed to DIFFERENT files. A scoped read
fails silently; a pool-size warning fails loudly. So: read the pool, and warn when it grows.

## What is NOT in either set

Routing still reads indexes ONLY. Both of these reads happen strictly AFTER every target is
fixed, which is what makes them safe -- a read that cannot influence the routing decision
cannot erode it.

Canonical: only files that ALREADY EXIST. A target that doesn't exist yet cannot contain a
duplicate. Staged: only candidates still `state: staging`. One marked `canonical` has been
promoted, so its claim now lives in the canonical file and is caught by the first set --
counting it too would double-report the same claim against itself.

Usage:
    collect_dedup_targets.py <placements.json> <hub-root>
    collect_dedup_targets.py <placements.json> <hub-root> --explain

Exit codes: 0 = read set resolved, 1 = a target could not be resolved, or a staging
directory could not be read (see below), 2 = bad input.
"""

import json
import os
import re
import sys

# One definition of where staging lives, shared across all three skills. Resolved via
# CLAUDE_PLUGIN_ROOT when the plugin is installed, and via a relative path when these scripts
# are run straight out of a checkout -- both must work, because the second is how they are
# tested. A copy of the path logic here instead of an import is exactly the drift that put two
# definitions of INDEX in this codebase.
_SETUP_SCRIPTS = os.path.join(
    os.environ.get("CLAUDE_PLUGIN_ROOT",
                   os.path.dirname(os.path.dirname(os.path.dirname(
                       os.path.dirname(os.path.abspath(__file__)))))),
    "skills", "setup-mesh", "scripts")
sys.path.insert(0, _SETUP_SCRIPTS)
import staging_config  # noqa: E402

# Above this many unpromoted candidates, say so. A large pool is not an error and never
# blocks -- it is a nudge to promote, on the same footing as a pending home. The number is
# a default, not a tuned value: it is roughly "more than a couple of un-drained ingestions".
POOL_WARN_AT = 50

# Above this many members in one collection, say so. Same footing as POOL_WARN_AT: a nudge,
# never a block. This bound is the honest cost of member resolution -- the CANONICAL set is
# chunk-bounded, but a chunk routed to a collection expands to that folder's members, so the
# read is FOLDER-bounded and grows with the folder rather than the transcript.
#
# Scoping this read by guessing at filenames was considered and REJECTED, for the reason the
# staged pool gives above: a scoped read fails silently, a size warning fails loudly. It would
# also break the taxonomy's rule that a member pattern is opaque -- used to GENERATE a name,
# never parsed to read meaning out of an existing one (docs/file-taxonomy.md). Frontmatter is
# read first and bodies only on demand, which is what keeps the constant small.
COLLECTION_WARN_AT = 40

FM = re.compile(r"^---\s*\n(.*?)\n---", re.S)
FM_KEY = re.compile(r"^([a-z_-]+):\s*(.*)$")

# A placement's target_path is Hub-relative and unambiguous: "payments/technical/x.md" for a
# domain file, "technical/x.md" for a cross-cutting one. There is exactly one place it can be.
#
# This used to try several mesh layouts, because a target was *repo*-relative and where that
# repo physically sat was a property of the layout rather than of the placement. That guessing
# is gone with the single-Hub collapse -- and with it the failure mode it created, where an
# unresolvable repo made dedup fail open.


def resolve(hub_root, target_path):
    """Return (full_path, exists). One candidate, no guessing."""
    full = os.path.join(hub_root, target_path)
    return full, os.path.isfile(full)


def parent_dir_exists(hub_root, target_path):
    """Does the directory this target names exist? Distinguishes 'a new file in a known
    location' (fine) from 'a path into nowhere' (a bug that would make dedup fail open)."""
    return os.path.isdir(os.path.dirname(os.path.join(hub_root, target_path)))


def is_collection_target(target_path):
    """A trailing slash means routing chose a FOLDER, not a file.

    The same one-character signal `classify_candidates.py` and `check_setup.py` use. It is the
    whole discriminator on purpose: nothing here knows what a persona is, or an ADR. A
    collection is a folder of same-typed files, and which folders those are is the mesh's
    business, not this script's.
    """
    return target_path.endswith("/")


def collect_members(hub_root, target_path):
    """Return (members, unreadable) for one collection target.

    Each member is {path, frontmatter}. FRONTMATTER ONLY -- bodies are not read here. Member
    resolution asks "which of these is this fact about?", and for a keyed member (a persona's
    `slug`, a typed artifact) the frontmatter answers it. Reading every body to decide would
    make the cost of routing to a collection scale with the SIZE of its members, not just
    their count, and persona files are explicitly hundreds of lines.

    FAILS CLOSED, and for a reason this project has now paid for repeatedly: a collection
    directory that exists but cannot be read must not come back as "no members". That is
    indistinguishable from an empty collection, and it would resolve every chunk to CREATE --
    silently manufacturing a duplicate member of a folder that already had the right one.
    Same shape as fail-open #12, where `os.walk` swallowing OSError made a guard unreachable.
    Listed here, checked by the caller, never guessed at.
    """
    members, unreadable = [], []
    full_dir = os.path.join(hub_root, target_path)

    try:
        names = sorted(os.listdir(full_dir))
    except OSError as exc:
        unreadable.append((full_dir, str(exc)))
        return members, unreadable

    for f in names:
        if not f.endswith(".md"):
            continue
        path = os.path.join(full_dir, f)
        try:
            with open(path) as fh:
                text = fh.read()
        except OSError as exc:
            unreadable.append((path, str(exc)))
            continue
        members.append({"path": path, "frontmatter": read_frontmatter(text)})

    return members, unreadable


def find_staging_dirs(hub_root):
    """The Hub's `<staging>/candidates/`. One tree, at the root (v0.17.0).

    Delegates to `staging_config.find_candidates_dirs`, which promotion also calls. The pool
    this dedups against must be exactly the pool promotion will later offer: if the two ever
    disagree about where candidates live, a claim is invisible to one of them. They used to be
    two identical hand-written walks kept in step by a comment; now there is one function.

    The path is ANCHORED to the Hub root rather than scanned for as a path tail. Scanning
    matched `<anything>/staging/candidates` at any depth, so a stray directory buried in a repo
    was adopted as a real staging dir.

    Returns (found, errors). A staging dir that exists but cannot be read is an ERROR, never a
    silent omission -- "no candidates" and "could not look" are indistinguishable downstream,
    and the second one ships every duplicate the pool contained.
    """
    return staging_config.find_candidates_dirs(hub_root)


def read_frontmatter(text):
    """Flat scalars from a candidate's frontmatter. Enough to read id/type/state/target."""
    m = FM.search(text)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("-"):
            continue
        if line[:1] in (" ", "\t"):      # nested under `edges:` -- not a top-level key
            continue
        km = FM_KEY.match(line)
        if km:
            out[km.group(1)] = km.group(2).strip()
    return out


def collect_staged(hub_root):
    """Return (rows, unreadable, misconfig). Unpromoted candidates across the whole mesh.

    FAILS CLOSED. A staging directory that exists but cannot be read is returned in
    `unreadable` and makes the caller exit non-zero, because "0 staged candidates" and
    "could not read staging" are indistinguishable to whoever consumes this list -- and the
    second one silently ships every duplicate the pool contained. That is the fail-open
    shape this project has now found twelve times; it is not going to be the thirteenth.
    Note the mesh may legitimately have NO staging dirs at all (nothing ingested yet), which
    is an empty pool, not an error -- absent is fine, unreadable is not.

    `misconfig` is the third case, between those two: no staging dirs where the config says,
    but `candidates/` directories present under some other parent name. That is a relocated
    tree with the variable unset, and it produces an empty pool that looks exactly like a
    fresh mesh. It warns rather than exits, because the pool is genuinely empty either way --
    what the caller must not do is report that emptiness as normal.
    """
    rows, unreadable, misconfig = [], [], []

    # `unreadable_dirs` are staging dirs that EXIST but could not be listed. They join the
    # same fail-closed list as an unreadable candidate file: an empty pool and an unlooked-at
    # pool are indistinguishable downstream, and the second one ships every duplicate.
    staging_dirs, unreadable_dirs = find_staging_dirs(hub_root)
    unreadable.extend(unreadable_dirs)

    # Found nothing where staging is configured to be? Check whether candidates exist under
    # some OTHER name before accepting an empty pool. Absent is legal; misconfigured is not,
    # and the two look identical from here without this check.
    if not staging_dirs:
        misconfig = staging_config.find_misplaced_candidates(hub_root)

    for cand_dir in staging_dirs:
        try:
            names = sorted(os.listdir(cand_dir))
        except OSError as exc:
            unreadable.append((cand_dir, str(exc)))
            continue

        for f in names:
            if not f.endswith(".md") or f.endswith("-transcript.md"):
                continue
            path = os.path.join(cand_dir, f)
            try:
                with open(path) as fh:
                    text = fh.read()
            except OSError as exc:
                unreadable.append((path, str(exc)))
                continue

            fm = read_frontmatter(text)
            if not fm:
                continue

            # A Conversation node is provenance, not a claim -- same skip as the chunk side.
            if fm.get("type") == "Conversation":
                continue

            # Skip on "not staging" rather than listing the done states, so a state added
            # later defaults to safe. A promoted candidate's claim lives in the canonical
            # file now, where the CANONICAL read set already covers it.
            if fm.get("state", "staging") != "staging":
                continue

            rows.append({
                "id": fm.get("id", f[:-3]),
                "path": path,
                "type": fm.get("type", "?"),
                "target": fm.get("target", ""),
            })

    return rows, unreadable, misconfig


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    explain = "--explain" in sys.argv

    if len(args) != 2:
        print(__doc__)
        return 2

    placements_path, hub_root = args

    # Resolve where staging lives for THIS Hub before anything looks for it: env var, then
    # `<hub>/.context-mesh`, then the default. Must happen after the root is known and before
    # the first staging lookup.
    staging_config.configure(hub_root)

    try:
        with open(placements_path) as fh:
            data = json.load(fh)
    except FileNotFoundError:
        print(f"error: no such file: {placements_path}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"error: {placements_path} is not valid JSON: {exc}", file=sys.stderr)
        return 2

    chunks = data.get("chunks", []) if isinstance(data, dict) else data

    # A file that parses as JSON but yields no chunks is the same failure as an
    # unresolvable target, one level up: "0 files to read" is indistinguishable from
    # "checked everything, nothing to dedup against". Silence here means every
    # duplicate and every contradiction ships.
    #
    # Caught by a wrong-schema fixture ({"placements": [...]} with `chunk_id`/`node_type`
    # instead of {"chunks": [...]} with `id`/`type`): it reported 0 files and exited 0.
    if not isinstance(chunks, list):
        print("error: expected a JSON list of chunks, or {\"chunks\": [...]} -- got "
              f"{type(chunks).__name__}", file=sys.stderr)
        return 2
    if not chunks:
        print("error: no chunks found. Expected a JSON list, or {\"chunks\": [...]} whose "
              "entries have `id`, `type`, and `target_path`.", file=sys.stderr)
        print("       An empty read set is NOT the same as 'no duplicates' -- refusing to "
              "report one.", file=sys.stderr)
        return 2

    # Entries that carry no target_path key at all are almost certainly a schema
    # mismatch rather than genuine homelessness (which is `target_path: null`).
    if not any("target_path" in c for c in chunks if isinstance(c, dict)):
        print(f"error: none of the {len(chunks)} chunk(s) have a `target_path` key. This "
              "looks like a schema mismatch, not a mesh with no homes.", file=sys.stderr)
        return 2

    # target -> [chunk ids routed there]
    targets = {}
    skipped_homeless = []
    skipped_conversation = []
    skipped_staging = []

    for c in chunks:
        cid = c.get("id", "?")

        # The Conversation node is provenance, not a claim. Nothing to dedup.
        if c.get("type") == "Conversation":
            skipped_conversation.append(cid)
            continue

        tp = c.get("target_path", "")

        # No home -> no file -> nothing to read. The gap is the finding, not a dupe.
        if tp is None:
            skipped_homeless.append(cid)
            continue

        if not tp:
            continue

        # A chunk whose TARGET points into staging has no canonical destination, so there is
        # no canonical file to compare it against. It is still compared against the staged
        # pool below, like every other chunk -- this skip is about the CANONICAL set only.
        #
        # Do not "fix" this by resolving the path: reading the file a chunk names as its own
        # destination compares it to its own candidate from a prior run, which flags a re-run
        # of the same transcript as duplicating itself.
        if staging_config.is_staging_path(tp):
            skipped_staging.append(cid)
            continue

        targets.setdefault(tp, []).append(cid)

    existing, new_file, unresolvable = [], [], []
    collections, coll_unreadable = [], []
    for tp in sorted(targets):
        # A COLLECTION target resolves to its members, not to one file. Without this branch
        # `resolve()` returns exists=False for the directory while `parent_dir_exists()`
        # returns True, so the target classified as "a new file in a known location" and
        # dedup compared the chunk against NOTHING -- every member of the folder invisible.
        # A fact about an existing persona could not be caught as a duplicate, because the
        # only file that could have shown it was never in the read set. Confirmed by running
        # it against `product/personas/` before this branch existed.
        if is_collection_target(tp):
            full_dir = os.path.join(hub_root, tp)
            if not os.path.isdir(full_dir):
                unresolvable.append((tp, targets[tp], full_dir))
                continue
            members, unread = collect_members(hub_root, tp)
            coll_unreadable.extend(unread)
            collections.append((tp, members, targets[tp]))
            continue

        full, exists = resolve(hub_root, tp)
        if exists:
            existing.append((tp, full, targets[tp]))
        elif parent_dir_exists(hub_root, tp):
            # The location is real, the file just isn't there yet. Nothing to dedup against.
            new_file.append((tp, full, targets[tp]))
        else:
            # The path points into nowhere. This is a bug, not a new file -- and it is
            # the one that MATTERS: an unresolved target reads as "no duplicates found",
            # so dedup would silently do nothing and every duplicate would ship.
            unresolvable.append((tp, targets[tp], full))

    # The second read set: unpromoted candidates from earlier ingestions.
    staged, unreadable, misconfig = collect_staged(hub_root)

    # To stderr, and in BOTH modes. The plain mode is a path list consumed by a caller, so a
    # warning must not join it on stdout -- but staying silent is how the empty pool passed as
    # normal in the first place.
    if misconfig:
        print(staging_config.misconfig_message(misconfig), file=sys.stderr)

    if not explain:
        for _, full, _ in existing:
            print(full)
        for _, members, _ in collections:
            for m in members:
                print(m["path"])
        for row in staged:
            print(row["path"])
        if unresolvable:
            for tp, ids, full in unresolvable:
                print(f"error: cannot resolve target '{tp}' (chunks: {', '.join(ids)})",
                      file=sys.stderr)
                print(f"    no such directory for: {full}", file=sys.stderr)
        # "cannot read" without naming staging: this list also carries walk errors from
        # `find_staging_dirs`, which walks the WHOLE Hub looking for staging dirs and so
        # reports any unreadable directory it meets on the way -- a collection included.
        # Calling all of them "staging" mislabels a real error, which is its own small
        # fail-open: the operator fixes the wrong directory.
        for path, err in unreadable:
            print(f"error: cannot read: {path} ({err})", file=sys.stderr)
        # An unreadable COLLECTION is an error on the same terms as unreadable staging: it
        # would otherwise read as an empty folder and resolve every chunk to CREATE.
        for path, err in coll_unreadable:
            print(f"error: cannot read collection member: {path} ({err})", file=sys.stderr)
        # A detected misconfiguration exits NON-ZERO, on the same footing as an unreadable
        # staging dir. The warning alone was not enough: it goes to stderr and the script
        # exited 0, so a piped or agent-driven run that only reads stdout proceeded to dedup
        # against an empty pool and shipped duplicates. Note this fires only when misplaced
        # candidates were actually FOUND -- a genuinely fresh mesh still exits 0, because
        # making "no candidates" an error would be the fail-CLOSED mirror of the same bug.
        if unresolvable or unreadable or coll_unreadable or misconfig:
            return 1
        return 0

    n_members = sum(len(m) for _, m, _ in collections)
    print(f"Dedup read set: {len(existing)} canonical file(s) + {n_members} collection "
          f"member(s) + {len(staged)} staged candidate(s).")
    print(f"  CANONICAL: bounded by {len(chunks)} chunk(s) -- routing chose these targets "
          f"from the index.")
    if collections:
        print(f"  MEMBERS:   bounded by the {len(collections)} collection(s) routing chose "
              f"-- folder-bounded, not chunk-bounded.")
    print("  STAGED:    bounded by the unpromoted pool -- earlier ingestions, not yet "
          "promoted.")
    print("Read these sets and nothing else.")
    print()

    if existing:
        print("READ THESE -- CANONICAL (they exist, so they may already contain the claim):")
        for tp, full, ids in existing:
            print(f"  {tp}")
            print(f"      -> {full}")
            print(f"      chunks routed here: {', '.join(ids)}")
        print()

    if collections:
        print("READ THESE -- COLLECTION MEMBERS (routing chose the FOLDER; decide which "
              "member):")
        for tp, members, ids in collections:
            print(f"  {tp}  ({len(members)} member(s))")
            print(f"      chunks routed here: {', '.join(ids)}")
            for m in members:
                fm = m["frontmatter"]
                key = fm.get("slug") or fm.get("id") or ""
                label = f"{fm.get('type', '?')}" + (f" {key}" if key else "")
                print(f"      {os.path.basename(m['path']):40} {label}")
            if not members:
                print("      (empty collection -- every chunk here CREATES a new member)")
        print()
        print("  MODIFY an existing member, or CREATE a new one. When the match is")
        print("  ambiguous, CREATE and flag the near-match at the checkpoint: a spurious")
        print("  new member is visible on disk and at the gate, while a wrong merge is")
        print("  buried in a diff. Do not merge on a maybe.")
        print()

    for tp, members, _ in collections:
        if len(members) >= COLLECTION_WARN_AT:
            print(f"NOTE: collection `{tp}` has {len(members)} members (warn at "
                  f"{COLLECTION_WARN_AT}).")
            print("  Not an error. This read is folder-bounded, so it grows with the folder")
            print("  rather than the transcript -- the one read here that does.")
            print()

    if staged:
        print("READ THESE -- STAGED (unpromoted claims an earlier ingestion already made):")
        for row in staged:
            tgt = row["target"] or "(no target)"
            print(f"  {row['id']:12} {row['type']:14} -> {tgt}")
            print(f"      {row['path']}")
        print()
        print("  A match here is NOT written into staging as a fresh claim. Link the new")
        print("  chunk to the staged one (`duplicate_of:` / a `contradicts` edge) and leave")
        print("  the staged candidate untouched -- ingestion only ever adds.")
        print()

    if len(staged) >= POOL_WARN_AT:
        print(f"NOTE: {len(staged)} unpromoted candidates in staging (warn at "
              f"{POOL_WARN_AT}).")
        print("  Not an error, and nothing is blocked. But the pool is what every future")
        print("  ingestion reads and what a human eventually reviews -- consider promoting.")
        print()

    if new_file:
        print("SKIP (location exists, file does not yet -- nothing to duplicate):")
        for tp, _, ids in new_file:
            print(f"  {tp}  ({', '.join(ids)})")
        print()

    if skipped_homeless:
        print(f"SKIP (no home in this mesh): {', '.join(skipped_homeless)}")
    if skipped_staging:
        print(f"SKIP canonical read (target is inside staging -- still compared against the "
              f"staged pool above): {', '.join(skipped_staging)}")
    if skipped_conversation:
        print(f"SKIP (provenance root, not a claim): {', '.join(skipped_conversation)}")

    if unreadable:
        print()
        print("UNREADABLE -- dedup cannot run, and that is an error:")
        for path, err in unreadable:
            print(f"  {path}")
            print(f"      {err}")
        print()
        print("An unreadable staging dir yields an empty pool, which looks exactly like")
        print("'no staged duplicates'. Fix access before writing anything.")

    if unresolvable:
        print()
        print("UNRESOLVABLE -- dedup cannot run for these, and that is an error:")
        for tp, ids, full in unresolvable:
            print(f"  {tp}  (chunks: {', '.join(ids)})")
            print(f"      no such directory for: {full}")
        print()
        print("An unresolved target looks exactly like 'no duplicates found'. Fix the")
        print("target path or the Hub root before writing anything.")

    if coll_unreadable:
        print()
        print("UNREADABLE COLLECTION -- member resolution cannot run, and that is an error:")
        for path, err in coll_unreadable:
            print(f"  {path}")
            print(f"      {err}")
        print()
        print("An unreadable collection yields zero members, which looks exactly like an")
        print("empty folder -- so every chunk would CREATE, silently duplicating a member")
        print("that is already there. Fix access before writing anything.")

    # Same non-zero exit as the plain path: a detected misconfiguration means the staged pool
    # is empty because nothing looked in the right place, not because there is nothing there.
    if unresolvable or unreadable or coll_unreadable or misconfig:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
