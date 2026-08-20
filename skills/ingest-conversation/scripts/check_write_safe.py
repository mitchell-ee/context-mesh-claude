#!/usr/bin/env python3
"""Refuse to write a candidate over one that already exists. The last line of defence.

`allocate_ids.py` makes a collision rare by numbering above everything already claimed. This
makes a collision that happens anyway LOUD. Both are needed, and this one is the one that must
never be removed: allocation is a read-then-write, so two runs that scan at the same instant
can still choose the same number. That is a genuine TOCTOU race and no amount of scanning
closes it.

WHAT IT PREVENTS. Stage 5 writes each chunk to `<staging>/candidates/<id>.md`. A plain write
silently replaces a file that is already there -- the failure that made this whole family of
bugs invisible: one file where there should be two, no error, exit 0, and the overwritten
run's claim simply gone. Worse, edges naming the clobbered ID then resolve to the WRONG node,
so `check_references.py` reports valid provenance that points at another conversation's data.

Run it immediately before writing. Exit 0 means every ID is free; exit 1 names the collisions
and nothing should be written -- re-run allocation, then re-check.

A COLLISION IS NOT AUTOMATICALLY RESOLVED HERE, deliberately. Renumbering at write time would
mean rewriting edges in files already on disk, which is ingestion editing what a previous run
wrote -- and ingestion only ever adds. Stopping and re-allocating is the correct repair.

Usage:
    check_write_safe.py <hub-root> <placements.json>
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "setup-mesh", "scripts"))
import staging_config  # noqa: E402


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 2:
        print(__doc__)
        return 2

    hub_root, placements = args
    if not os.path.isdir(hub_root):
        print(f"error: not a directory: {hub_root}", file=sys.stderr)
        return 2
    staging_config.configure(hub_root)

    try:
        with open(placements) as fh:
            data = json.load(fh)
    except OSError as exc:
        print(f"error: cannot read {placements}: {exc}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"error: {placements} is not valid JSON: {exc}", file=sys.stderr)
        return 2

    cand_dir = os.path.join(hub_root, staging_config.candidates_dir())

    # A MISSING CANDIDATES DIR IS AN ERROR, NOT AN EMPTY POOL. "Nothing exists, so nothing
    # collides" is exactly the reasoning that makes a misconfigured staging path look safe --
    # the same fail-open shape as the dedup pool collapsing to zero on a relocated tree.
    if not os.path.isdir(cand_dir):
        print(f"error: no candidates directory at {cand_dir}", file=sys.stderr)
        print(f"Staging resolves to {staging_config.STAGING_DIR!r} "
              f"(from {staging_config.STAGING_SOURCE}). Run setup-mesh, or fix the path --\n"
              f"an absent directory is not proof that no candidate would be overwritten.",
              file=sys.stderr)
        return 1

    # Only chunks that will actually be written. A dedup-dropped duplicate is never written,
    # so a file bearing its ID is not a collision this run would cause.
    to_write = [c for c in data.get("chunks", [])
                if c.get("id") and not c.get("duplicate_of")]

    collisions = []
    for c in to_write:
        cid = str(c["id"])
        path = os.path.join(cand_dir, f"{cid}.md")
        if os.path.exists(path):
            collisions.append((cid, path))

    if collisions:
        print(f"error: {len(collisions)} candidate(s) already exist -- writing would "
              f"OVERWRITE them:", file=sys.stderr)
        for cid, path in collisions:
            print(f"  {cid}  ->  {path}", file=sys.stderr)
        print("\nWrite nothing. Re-run allocate_ids.py --apply to renumber this run, then\n"
              "re-check. Do not resolve this by overwriting: the file on disk is another\n"
              "run's claim, and edges elsewhere already point at that ID.", file=sys.stderr)
        return 1

    print(f"OK: {len(to_write)} candidate(s) can be written without overwriting anything.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
