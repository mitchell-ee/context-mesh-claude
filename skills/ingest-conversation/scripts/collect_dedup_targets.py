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

# Above this many unpromoted candidates, say so. A large pool is not an error and never
# blocks -- it is a nudge to promote, on the same footing as a pending home. The number is
# a default, not a tuned value: it is roughly "more than a couple of un-drained ingestions".
POOL_WARN_AT = 50

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


def find_staging_dirs(hub_root):
    """Every `staging/candidates/` in the Hub -- the root one plus one per domain.

    Same walk as classify_candidates.find_staging_dirs, and deliberately so: the pool this
    dedups against must be exactly the pool promotion will later offer. If the two ever
    disagree about where candidates live, a claim is invisible to one of them.

    Returns (found, walk_errors). `os.walk` swallows OSError by default, so a staging dir
    the walker cannot descend into simply never appears -- it is not found, not empty, and
    NOT an error, which is indistinguishable from "that domain has no candidates". A real
    candidate then goes uncompared and its duplicate ships. Verified by chmod 000 on a
    populated staging dir: the pool silently lost a candidate and the script exited 0.
    `onerror` is what makes that visible; the listdir guard below never even ran, because
    the failure happened one level up during the walk.
    """
    found, walk_errors = [], []

    def on_walk_error(exc):
        walk_errors.append((getattr(exc, "filename", "?"), str(exc)))

    for dirpath, dirnames, _ in os.walk(hub_root, onerror=on_walk_error):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        if os.path.basename(dirpath) == "candidates" and \
                os.path.basename(os.path.dirname(dirpath)) == "staging":
            found.append(dirpath)
    return sorted(found), walk_errors


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
    """Return (rows, unreadable). Unpromoted candidates across the whole mesh.

    FAILS CLOSED. A staging directory that exists but cannot be read is returned in
    `unreadable` and makes the caller exit non-zero, because "0 staged candidates" and
    "could not read staging" are indistinguishable to whoever consumes this list -- and the
    second one silently ships every duplicate the pool contained. That is the fail-open
    shape this project has now found twelve times; it is not going to be the thirteenth.
    Note the mesh may legitimately have NO staging dirs at all (nothing ingested yet), which
    is an empty pool, not an error -- absent is fine, unreadable is not.
    """
    rows, unreadable = [], []

    staging_dirs, walk_errors = find_staging_dirs(hub_root)
    unreadable.extend(walk_errors)

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

    return rows, unreadable


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    explain = "--explain" in sys.argv

    if len(args) != 2:
        print(__doc__)
        return 2

    placements_path, hub_root = args

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
        if "/staging/" in tp or tp.startswith("staging/"):
            skipped_staging.append(cid)
            continue

        targets.setdefault(tp, []).append(cid)

    existing, new_file, unresolvable = [], [], []
    for tp in sorted(targets):
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
    staged, unreadable = collect_staged(hub_root)

    if not explain:
        for _, full, _ in existing:
            print(full)
        for row in staged:
            print(row["path"])
        if unresolvable:
            for tp, ids, full in unresolvable:
                print(f"error: cannot resolve target '{tp}' (chunks: {', '.join(ids)})",
                      file=sys.stderr)
                print(f"    no such directory for: {full}", file=sys.stderr)
        for path, err in unreadable:
            print(f"error: cannot read staging: {path} ({err})", file=sys.stderr)
        if unresolvable or unreadable:
            return 1
        return 0

    print(f"Dedup read set: {len(existing)} canonical file(s) + {len(staged)} staged "
          f"candidate(s).")
    print(f"  CANONICAL: bounded by {len(chunks)} chunk(s) -- routing chose these targets "
          f"from the index.")
    print("  STAGED:    bounded by the unpromoted pool -- earlier ingestions, not yet "
          "promoted.")
    print("Read both sets and nothing else.")
    print()

    if existing:
        print("READ THESE -- CANONICAL (they exist, so they may already contain the claim):")
        for tp, full, ids in existing:
            print(f"  {tp}")
            print(f"      -> {full}")
            print(f"      chunks routed here: {', '.join(ids)}")
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
        print("UNREADABLE STAGING -- dedup cannot run, and that is an error:")
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

    if unresolvable or unreadable:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
