#!/usr/bin/env python3
"""The placements file, made durable -- so a review can be resumed in a later session.

Placements used to be a scratch file that lived and died with one run. That made the async
review mode a dead end: the reviewer got a markdown file to read at their own pace, but the
run ended, and with it any ability to act on what they had read. Coming back meant hand-editing
candidates against a transcript that no longer existed.

A run now lives at `<staging>/runs/<run-id>/`:

    placements.json    the proposals, PLUS a decision per chunk
    transcript.md      the working copy, when the Hub keeps one (see staging_config)

WHAT MAKES IT RESUMABLE IS THE DECISION FIELD, NOT THE FILE. Every chunk carries
`decision: pending | approved | dropped` and, once decided, `decided_at`. A resumed walk
presents only what is still `pending`. Without that, resuming would re-ask about chunks the
reviewer already approved, and the second answer would silently overwrite the first.

DECISIONS ARE ONLY EVER RECORDED, NEVER ACTED ON HERE. This module does not write candidates,
does not validate, and does not promote. A run whose chunks are all decided is *ready* to be
written to staging; writing is still stage 5, after validation, exactly as before.

`pending` is the safe default in both directions. A chunk with no decision field is treated as
pending and gets asked about -- an extra question costs the reviewer seconds. The inverse
default would silently approve something nobody looked at.

Usage:
    run_state.py init <hub-root> <placements.json> [--slug <name>]   # start a durable run
    run_state.py show <hub-root> <run-id>                            # progress summary
    run_state.py decide <hub-root> <run-id> <chunk-id> <decision>    # record one decision
    run_state.py decide-rest <hub-root> <run-id> <decision> [--target <path>]
    run_state.py list <hub-root>                                     # runs with work left
"""

import json
import os
import shutil
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "setup-mesh", "scripts"))
import staging_config  # noqa: E402

PENDING = "pending"
APPROVED = "approved"
DROPPED = "dropped"
DECISIONS = (PENDING, APPROVED, DROPPED)

PLACEMENTS = "placements.json"
TRANSCRIPT = "transcript.md"


def _now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _run_dir(hub_root, run_id):
    return os.path.join(hub_root, staging_config.runs_dir(), run_id)


def _load(hub_root, run_id):
    """The run's placements, or exit non-zero saying which run is missing.

    A missing run must not read as an empty one: a resumed walk over zero chunks would
    report 'nothing left to review' about a run whose work is entirely intact.
    """
    path = os.path.join(_run_dir(hub_root, run_id), PLACEMENTS)
    try:
        with open(path) as fh:
            return json.load(fh), path
    except FileNotFoundError:
        print(f"error: no run {run_id!r} at {path}", file=sys.stderr)
        known = list_runs(hub_root)
        if known:
            print("known runs:\n  " + "\n  ".join(r for r, _ in known), file=sys.stderr)
        else:
            print("no runs recorded in this Hub", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as exc:
        print(f"error: {path} is not valid JSON: {exc}", file=sys.stderr)
        sys.exit(1)


def _save(data, path):
    with open(path, "w") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")


def _reviewable(data):
    """Chunks the gate actually asks about.

    Conversation nodes are provenance roots, not placement decisions, and dedup-dropped
    duplicates were never going to be written. Neither is a chunk a reviewer decides, so
    neither may count toward 'pending' -- a run that is finished must report as finished.
    """
    return [c for c in data.get("chunks", [])
            if c.get("type") != "Conversation" and not c.get("duplicate_of")]


def decision_of(chunk):
    """A chunk's decision, defaulting to pending. Unknown values are pending, deliberately."""
    value = chunk.get("decision", PENDING)
    return value if value in DECISIONS else PENDING


def init(hub_root, placements_path, slug=None):
    """Copy a placements file into a durable run directory, stamping every chunk pending."""
    try:
        with open(placements_path) as fh:
            data = json.load(fh)
    except OSError as exc:
        print(f"error: cannot read {placements_path}: {exc}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"error: {placements_path} is not valid JSON: {exc}", file=sys.stderr)
        return 1

    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    run_id = f"{stamp}-{slug}" if slug else stamp
    dest = _run_dir(hub_root, run_id)
    if os.path.exists(dest):
        print(f"error: run {run_id!r} already exists at {dest}", file=sys.stderr)
        return 1
    os.makedirs(dest)

    for c in data.get("chunks", []):
        if c.get("type") == "Conversation" or c.get("duplicate_of"):
            continue
        c.setdefault("decision", PENDING)

    data["run_id"] = run_id
    data["started_at"] = _now()
    _save(data, os.path.join(dest, PLACEMENTS))

    print(run_id)
    print(f"run at {dest}", file=sys.stderr)
    return 0


def archive_transcript(hub_root, run_id, transcript_path):
    """Keep a working copy of the transcript beside the run, so retry survives the session.

    Retry re-proposes a chunk FROM THE SOURCE, so it is the one operation that cannot work
    without the transcript. Approve and drop are decisions about text already written down
    and need nothing.
    """
    dest_dir = _run_dir(hub_root, run_id)
    if not os.path.isdir(dest_dir):
        print(f"error: no run {run_id!r} at {dest_dir}", file=sys.stderr)
        return 1
    dest = os.path.join(dest_dir, TRANSCRIPT)
    shutil.copyfile(transcript_path, dest)
    print(dest)
    return 0


def decide(hub_root, run_id, chunk_id, decision):
    """Record one chunk's decision. An unknown chunk ID is an error, never a silent no-op."""
    if decision not in (APPROVED, DROPPED):
        print(f"error: decision must be {APPROVED} or {DROPPED}, got {decision!r}",
              file=sys.stderr)
        return 1

    data, path = _load(hub_root, run_id)
    for c in data.get("chunks", []):
        if str(c.get("id")) == chunk_id:
            if c.get("type") == "Conversation":
                print(f"error: {chunk_id} is a Conversation node -- not reviewed",
                      file=sys.stderr)
                return 1
            c["decision"] = decision
            c["decided_at"] = _now()
            _save(data, path)
            print(f"{chunk_id} -> {decision}")
            return 0

    print(f"error: no chunk {chunk_id!r} in run {run_id}", file=sys.stderr)
    print("pending chunks:\n  " + ("\n  ".join(
        str(c.get("id")) for c in _reviewable(data)
        if decision_of(c) == PENDING) or "(none)"), file=sys.stderr)
    return 1


def decide_rest(hub_root, run_id, decision, target=None):
    """The batch-outs: approve the rest of one destination file, or all the rest.

    With `--target`, only that group. Without it, every pending chunk in the run. A target
    naming no pending group EXITS NON-ZERO rather than deciding nothing quietly -- a batch
    approval that silently covers zero chunks would leave the reviewer believing a file was
    approved when the walk will ask about it again.
    """
    if decision not in (APPROVED, DROPPED):
        print(f"error: decision must be {APPROVED} or {DROPPED}, got {decision!r}",
              file=sys.stderr)
        return 1

    data, path = _load(hub_root, run_id)
    pending = [c for c in _reviewable(data) if decision_of(c) == PENDING]
    if target is not None:
        matched = [c for c in pending if _target_of(c) == target]
        if not matched:
            print(f"error: no pending chunks with destination {target!r}", file=sys.stderr)
            groups = sorted({_target_of(c) for c in pending})
            print("pending destinations:\n  " + ("\n  ".join(groups) or "(none)"),
                  file=sys.stderr)
            return 1
    else:
        matched = pending

    # BOTH forms must refuse an empty batch, not just the targeted one. "0 chunk(s) ->
    # approved" with exit 0 tells a reviewer their batch approval landed when it decided
    # nothing -- and on an already-complete run that reads as confirmation rather than as
    # the no-op it was.
    if not matched:
        print(f"error: nothing pending in run {run_id} -- no chunks to {decision}",
              file=sys.stderr)
        return 1

    stamp = _now()
    for c in matched:
        c["decision"] = decision
        c["decided_at"] = stamp
    _save(data, path)

    print(f"{len(matched)} chunk(s) -> {decision}")
    for c in matched:
        print(f"  {c.get('id')}")
    return 0


def _target_of(chunk):
    tp = chunk.get("target_path", "")
    if tp is None:
        return "(no home in this mesh)"
    return tp or "(none proposed)"


def show(hub_root, run_id):
    """What is left to review, and what has been settled."""
    data, _ = _load(hub_root, run_id)
    reviewable = _reviewable(data)
    by = {PENDING: [], APPROVED: [], DROPPED: []}
    for c in reviewable:
        by[decision_of(c)].append(c)

    print(f"run {run_id}   started {data.get('started_at', '?')}")
    transcript = os.path.join(_run_dir(hub_root, run_id), TRANSCRIPT)
    if os.path.isfile(transcript):
        print(f"transcript kept -- correcting a placement still works")
    else:
        print("no transcript kept -- approve and drop work; correcting one does not")
    print()
    print(f"  pending   {len(by[PENDING]):>3}")
    print(f"  approved  {len(by[APPROVED]):>3}")
    print(f"  dropped   {len(by[DROPPED]):>3}")
    print()

    if not by[PENDING]:
        print("Nothing left to review. Validate, then write the approved chunks to staging.")
        return 0

    groups = {}
    for c in by[PENDING]:
        groups.setdefault(_target_of(c), []).append(c)
    print("Still pending, by destination:")
    for target, members in sorted(groups.items()):
        ids = ", ".join(str(c.get("id")) for c in members)
        print(f"  {target}  ({len(members)})  {ids}")
    return 0


def list_runs(hub_root):
    """Every run on disk, newest first, as (run_id, pending_count)."""
    root = os.path.join(hub_root, staging_config.runs_dir())
    if not os.path.isdir(root):
        return []
    out = []
    for name in sorted(os.listdir(root), reverse=True):
        path = os.path.join(root, name, PLACEMENTS)
        if not os.path.isfile(path):
            continue
        try:
            with open(path) as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            # A run we cannot parse is reported, not skipped: silence would hide work.
            out.append((name, -1))
            continue
        out.append((name, sum(1 for c in _reviewable(data)
                              if decision_of(c) == PENDING)))
    return out


def cmd_list(hub_root):
    runs = list_runs(hub_root)
    if not runs:
        print("no runs recorded in this Hub")
        return 0
    for run_id, pending in runs:
        if pending < 0:
            print(f"  {run_id}   UNREADABLE -- placements.json could not be parsed")
        elif pending:
            print(f"  {run_id}   {pending} pending")
        else:
            print(f"  {run_id}   complete")
    return 0


def main():
    argv = sys.argv[1:]
    if not argv:
        print(__doc__)
        return 2

    cmd = argv[0]

    def flag(name):
        if name in argv:
            i = argv.index(name)
            if i + 1 < len(argv):
                return argv[i + 1]
            print(f"error: {name} needs a value", file=sys.stderr)
            sys.exit(2)
        return None

    positional = []
    skip = False
    for i, a in enumerate(argv[1:], 1):
        if skip:
            skip = False
            continue
        if a.startswith("--"):
            skip = True
            continue
        positional.append(a)

    if cmd == "init" and len(positional) == 2:
        hub = positional[0]
        staging_config.configure(hub)
        return init(hub, positional[1], flag("--slug"))
    if cmd == "archive" and len(positional) == 3:
        hub = positional[0]
        staging_config.configure(hub)
        return archive_transcript(hub, positional[1], positional[2])
    if cmd == "show" and len(positional) == 2:
        hub = positional[0]
        staging_config.configure(hub)
        return show(hub, positional[1])
    if cmd == "decide" and len(positional) == 4:
        hub = positional[0]
        staging_config.configure(hub)
        return decide(hub, positional[1], positional[2], positional[3])
    if cmd == "decide-rest" and len(positional) == 3:
        hub = positional[0]
        staging_config.configure(hub)
        return decide_rest(hub, positional[1], positional[2], flag("--target"))
    if cmd == "list" and len(positional) == 1:
        hub = positional[0]
        staging_config.configure(hub)
        return cmd_list(hub)

    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
