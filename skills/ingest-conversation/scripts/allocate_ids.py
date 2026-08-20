#!/usr/bin/env python3
"""Allocate chunk IDs that do not collide with anything already in the mesh.

THE BUG THIS EXISTS FOR. Every run used to start numbering at 1, so two ingestions produced
`conv-0001` and `k-0001` apiece. Stage 5 writes each chunk to `<staging>/candidates/<id>.md`,
so the second run SILENTLY OVERWROTE the first: one file where there should have been two, no
error, exit 0. Worse than lost text -- `derives-from: conv-0001` in the second run then
resolved to the FIRST run's Conversation node, so every chunk carried confidently wrong
provenance that `check_references.py` reports as valid, because the ID does exist.

The docs asserted the opposite ("unique IDs, so two concurrent ingests never collide") and
used it to justify having no staging PR. Nothing ever made them unique.

WHY NOT A RUN-SCOPED PREFIX. `20260820-124410-a:k-0001` is trivially unique and unusable: the
whole point of an ID here is that a human says "retry that one" at a gate. IDs stay short --
`k-0001`, `k-0002` -- and uniqueness comes from allocating against the pool that already
exists rather than from decorating each ID.

So a first run in an empty mesh still gets `k-0001`, and a concurrent second run gets `k-0005`.
Nothing about the format changes, and `render_checkpoint.py`'s range collapsing
(`k-0001-0004`) keeps working because the shape is untouched.

THIS NARROWS THE WINDOW; IT DOES NOT CLOSE IT. Two runs that scan at the same moment can still
choose the same next number -- a genuine TOCTOU race. That is why the write in stage 5 must
REFUSE to overwrite an existing candidate rather than trusting this. Allocation makes
collisions rare; the write guard makes a surviving one loud. Neither alone is enough, and the
guard is the one that must never be removed: it is what turns silent data loss into a stopped
run.

Scans BOTH pools, for the same reason dedup does:
  - `<staging>/candidates/` -- everything written by past runs, promoted or not
  - `<staging>/runs/*/placements.json` -- IDs an OPEN run has already claimed but not yet
    written. Without this, two runs open at once (which is now the normal workflow, since a
    run outlives its session) would allocate identically until the first one writes.

Usage:
    allocate_ids.py <hub-root>                  # report the next free number per prefix
    allocate_ids.py <hub-root> <placements.json> --apply
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "setup-mesh", "scripts"))
import staging_config  # noqa: E402

# `k-0001` -> ("k", 1, 4). Matches the shape render_checkpoint.py parses with rpartition("-"),
# deliberately: an ID this cannot read is also an ID the checkpoint cannot group.
ID_RE = re.compile(r"^([a-z][a-z0-9-]*)-(\d+)$")

FRONTMATTER_ID = re.compile(r"^id:\s*(\S+)\s*$", re.MULTILINE)


def parse_id(cid):
    """(prefix, number, width) or None for an ID this scheme does not manage."""
    m = ID_RE.match(str(cid).strip())
    if not m:
        return None
    return m.group(1), int(m.group(2)), len(m.group(2))


def scan_candidates(hub_root):
    """Every ID in `<staging>/candidates/`, by filename AND by frontmatter.

    Both, because they can disagree: a file's `id:` is authoritative, but a file whose
    frontmatter is unreadable still occupies its filename. Taking the union means a
    malformed candidate cannot hand its number to a new chunk.
    """
    found = set()
    cand_dir = os.path.join(hub_root, staging_config.candidates_dir())
    try:
        names = os.listdir(cand_dir)
    except OSError:
        # No candidates dir yet is a fresh mesh, not an error -- allocation starts at 1.
        return found

    for name in names:
        if not name.endswith(".md"):
            continue
        found.add(name[:-3])
        try:
            with open(os.path.join(cand_dir, name)) as fh:
                text = fh.read()
        except OSError:
            continue
        m = FRONTMATTER_ID.search(text)
        if m:
            found.add(m.group(1))
    return found


def scan_open_runs(hub_root):
    """Every ID claimed by a run that has not been written to staging yet.

    A run is durable now, so two can sit open for days. Their IDs are claimed the moment
    placements are created, long before stage 5 writes anything -- so a scan of
    `candidates/` alone would hand the same numbers to both.
    """
    found = set()
    runs_root = os.path.join(hub_root, staging_config.runs_dir())
    if not os.path.isdir(runs_root):
        return found

    for run_id in os.listdir(runs_root):
        path = os.path.join(runs_root, run_id, "placements.json")
        if not os.path.isfile(path):
            continue
        try:
            with open(path) as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            # UNREADABLE RUNS ARE NOT SKIPPED SILENTLY -- see next_numbers(). Skipping here
            # would let a corrupt run's IDs be reissued, which is the exact bug this file
            # exists to prevent, reintroduced through the back door.
            continue
        for c in data.get("chunks", []):
            if c.get("id"):
                found.add(str(c["id"]))
    return found


def unreadable_runs(hub_root):
    """Runs whose placements could not be parsed. Their claimed IDs are UNKNOWN."""
    bad = []
    runs_root = os.path.join(hub_root, staging_config.runs_dir())
    if not os.path.isdir(runs_root):
        return bad
    for run_id in sorted(os.listdir(runs_root)):
        path = os.path.join(runs_root, run_id, "placements.json")
        if not os.path.isfile(path):
            continue
        try:
            with open(path) as fh:
                json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            bad.append((run_id, str(exc)))
    return bad


def next_numbers(hub_root):
    """The next free number per prefix: {"k": 5, "conv": 2}. Prefixes unseen start at 1."""
    highest = {}
    for cid in scan_candidates(hub_root) | scan_open_runs(hub_root):
        parsed = parse_id(cid)
        if not parsed:
            continue
        prefix, num, _ = parsed
        highest[prefix] = max(highest.get(prefix, 0), num)
    return {p: n + 1 for p, n in highest.items()}


def allocate(data, hub_root, width=4):
    """Renumber a placements payload so nothing collides. Returns {old_id: new_id}.

    Rewrites EDGE TARGETS TOO. A chunk's `derives-from` names its Conversation by ID, so
    renumbering the node without renumbering the references pointing at it would produce
    exactly the dangling-provenance failure this module exists to prevent -- and
    `check_references.py` would then report a broken edge for a mesh that is internally
    consistent apart from this rewrite.
    """
    counters = next_numbers(hub_root)
    mapping = {}

    for c in data.get("chunks", []):
        cid = str(c.get("id", ""))
        parsed = parse_id(cid)
        if not parsed:
            continue
        prefix, _, seen_width = parsed
        nxt = counters.get(prefix, 1)
        new = f"{prefix}-{str(nxt).zfill(max(width, seen_width))}"
        counters[prefix] = nxt + 1
        if new != cid:
            mapping[cid] = new
        c["id"] = new

    if not mapping:
        return mapping

    # Point every reference at the renumbered node.
    for c in data.get("chunks", []):
        for e in c.get("edges", []):
            t = str(e.get("target", ""))
            if t in mapping:
                e["target"] = mapping[t]
        for key in ("duplicate_of", "member_near_match"):
            v = c.get(key)
            if v and str(v) in mapping:
                c[key] = mapping[str(v)]
        tp = c.get("target_path")
        if isinstance(tp, str):
            for old, new in mapping.items():
                if tp.endswith(f"/{old}.md"):
                    c["target_path"] = tp[: -len(f"/{old}.md")] + f"/{new}.md"
                    break

    return mapping


def main():
    argv = sys.argv[1:]
    apply = "--apply" in argv
    args = [a for a in argv if not a.startswith("--")]

    if not args:
        print(__doc__)
        return 2

    hub_root = args[0]
    if not os.path.isdir(hub_root):
        print(f"error: not a directory: {hub_root}", file=sys.stderr)
        return 2
    staging_config.configure(hub_root)

    # A run whose placements cannot be read has claimed IDs nobody can enumerate. Allocating
    # around it is guesswork, and the failure mode is the silent overwrite this exists to
    # stop -- so it is FAIL-CLOSED, not a warning.
    bad = unreadable_runs(hub_root)
    if bad:
        print("error: cannot determine which IDs are already claimed --", file=sys.stderr)
        for run_id, exc in bad:
            print(f"  run {run_id}: {exc}", file=sys.stderr)
        print("Fix or remove those runs before allocating; allocating around an unreadable\n"
              "run risks reissuing an ID it already holds.", file=sys.stderr)
        return 1

    if len(args) == 1:
        counters = next_numbers(hub_root)
        if not counters:
            print("No IDs in use. A first run starts at 0001.")
            return 0
        print("Next free number per prefix:")
        for prefix in sorted(counters):
            print(f"  {prefix}-{str(counters[prefix]).zfill(4)}")
        return 0

    placements = args[1]
    try:
        with open(placements) as fh:
            data = json.load(fh)
    except OSError as exc:
        print(f"error: cannot read {placements}: {exc}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"error: {placements} is not valid JSON: {exc}", file=sys.stderr)
        return 2

    mapping = allocate(data, hub_root)

    if not apply:
        if not mapping:
            print("No renumbering needed -- nothing in this run collides.")
            return 0
        print("Would renumber (re-run with --apply):")
        for old in sorted(mapping):
            print(f"  {old} -> {mapping[old]}")
        return 0

    with open(placements, "w") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")

    if mapping:
        print(f"Renumbered {len(mapping)} chunk(s); edges rewritten to match.")
        for old in sorted(mapping):
            print(f"  {old} -> {mapping[old]}")
    else:
        print("No renumbering needed -- nothing in this run collides.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
