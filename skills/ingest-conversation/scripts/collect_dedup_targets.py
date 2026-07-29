#!/usr/bin/env python3
"""List the target files a dedup pass must read -- and nothing else.

This enforces the bound on the dedup read. Routing picks targets from the index alone;
dedup then opens ONLY the files routing already chose. This script derives that list from
the placements, so the read set is a consequence of the routing decision rather than a
judgement call made in the moment.

Why a script and not just "read the target file": the failure mode is drift. Opening one
more file to be sure, then another, is how index-only routing erodes into the whole-mesh
load the project exists to kill. The read set is N-chunks-bounded, never N-domains-bounded,
and it is computed here so that bound is visible and auditable.

The list contains only files that ALREADY EXIST. A target that doesn't exist yet cannot
contain a duplicate, so there is nothing to read.

Usage:
    collect_dedup_targets.py <placements.json> <hub-root>
    collect_dedup_targets.py <placements.json> <hub-root> --explain

Exit codes: 0 = read set resolved, 1 = a target could not be resolved (see below), 2 = bad input.
"""

import json
import os
import sys

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

        # A staging path is where this run WRITES, not canonical context to dedup against.
        # Reading it would compare a chunk to its own candidate file from a prior run --
        # self-referential, and it would flag a re-run of the same transcript as duplicating
        # itself. Dedup asks "does canonical context already say this?"; staging is not
        # canonical, by definition. (Dedup against sibling candidates is a different problem,
        # deliberately out of scope -- the human sees both at the gate.)
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

    if not explain:
        for _, full, _ in existing:
            print(full)
        if unresolvable:
            for tp, ids, full in unresolvable:
                print(f"error: cannot resolve target '{tp}' (chunks: {', '.join(ids)})",
                      file=sys.stderr)
                print(f"    no such directory for: {full}", file=sys.stderr)
            return 1
        return 0

    print(f"Dedup read set: {len(existing)} file(s), bounded by {len(chunks)} chunk(s).")
    print("Routing chose these targets from the index; dedup reads only these.")
    print()

    if existing:
        print("READ THESE (they exist, so they may already contain the claim):")
        for tp, full, ids in existing:
            print(f"  {tp}")
            print(f"      -> {full}")
            print(f"      chunks routed here: {', '.join(ids)}")
        print()

    if new_file:
        print("SKIP (location exists, file does not yet -- nothing to duplicate):")
        for tp, _, ids in new_file:
            print(f"  {tp}  ({', '.join(ids)})")
        print()

    if skipped_homeless:
        print(f"SKIP (no home in this mesh): {', '.join(skipped_homeless)}")
    if skipped_staging:
        print(f"SKIP (staging is output, not canonical context): {', '.join(skipped_staging)}")
    if skipped_conversation:
        print(f"SKIP (provenance root, not a claim): {', '.join(skipped_conversation)}")

    if unresolvable:
        print()
        print("UNRESOLVABLE -- dedup cannot run for these, and that is an error:")
        for tp, ids, full in unresolvable:
            print(f"  {tp}  (chunks: {', '.join(ids)})")
            print(f"      no such directory for: {full}")
        print()
        print("An unresolved target looks exactly like 'no duplicates found'. Fix the")
        print("target path or the Hub root before writing anything.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
