#!/usr/bin/env python3
"""Walk every edge in a mesh and check its target resolves. Including the one that doesn't.

Every edge in the mesh points at another file -- except one. A `rendered-on` edge points at
a `Board` living in Miro or Claude Design, addressed by a board ID rather than a filesystem
path. A validator that assumes "target = path" reports every sidecar as a dangling link, and
a validator that then gets silenced stops catching the real ones.

So the exception is the point of this script, and it is a positive rule, not a mute:

    A `rendered-on` target MUST be an off-filesystem board reference,
    and MUST NOT be a path. Both directions are errors.

That second direction matters. `rendered-on -> product/story-map.md` is not a sidecar with a
sloppy target; it is a claim that a *file* is the visual surface, which inverts the rule that
a board is a view and never canonical. Accepting it would let the board become the source of
truth by accident -- exactly what board-sidecars.md forbids.

Target forms, and how each resolves:

  conv-0001                              node ID declared anywhere in the Hub
  payments                               a Domain (namespace node)
  payments:OPP-0001                      domain-prefixed artifact ID
  payments/technical/x.md                Hub-relative path
  technical/x.md                         Hub-relative path (cross-cutting)
  miro:board:uXjVA1b2c3                  a Board -- NOT a path, and correct

Every path is Hub-relative and therefore unambiguous. This used to be much harder: a target
could be repo-relative, meaning it resolved differently depending on which repo declared it,
so the walker had to track a declaring repo and try several layouts. The single-Hub collapse
removes that entirely -- and with it the bug class where a repo-relative reference stopped
meaning what it meant once it left its repo (2026-07-21).

Usage:
    check_references.py <hub-root>
    check_references.py <hub-root> --json
    check_references.py <hub-root> --quiet

Exit codes: 0 = every edge resolves, 1 = at least one dangling or malformed, 2 = bad input.
"""

import json
import os
import re
import sys

# A board reference is a scheme-prefixed opaque ID: `miro:board:<id>`, `claude-design:<id>`.
# Deliberately permissive about the vendor and the ID -- the mesh does not own either, and a
# validator that hard-codes today's vendors becomes the reason a new one can't be adopted.
# It is strict about the ONE thing the mesh does own: this is not a filesystem path.
BOARD_REF = re.compile(r"^[a-z][a-z0-9-]*:(?:board:)?[A-Za-z0-9_=-]+$")

# Domains live under `domains/` and nowhere else (v2.2).
DOMAINS_DIR = "domains"

# `<domain>:TYPE-NNNN` -- a domain-prefixed discovery or work artifact ID.
# TASK was here from v2.1 until v2.2 deferred the type; if it is ever restored it must be
# added back here too, or every Task reference goes silently unvalidated -- the fail-open
# shape this project keeps rediscovering.
ARTIFACT_ID = re.compile(
    r"^([a-z0-9][a-z0-9-]*):(OUTCOME|OPP|SOL|ASSUMPTION|STORY|EPIC)-(\d{4})$")

# A bare node ID as written in staging: `conv-0001`, `rf-0003`, `oq-0002`.
NODE_ID = re.compile(r"^[a-z]+-\d{4}$")

# An artifact ID with no domain prefix: `OUTCOME-0001`. Resolves in the declaring domain.
BARE_ARTIFACT_ID = re.compile(r"^(OUTCOME|OPP|SOL|ASSUMPTION|STORY|EPIC)-(\d{4})$")

FRONTMATTER = re.compile(r"\A---\n(.*?)\n---", re.S)


def looks_like_path(s):
    """Does this target name a file? A path has a separator or a file extension."""
    return "/" in s or s.endswith(".md") or s.endswith(".json")


# The OST files declare parentage as a bare frontmatter key -- `parent-outcome: OUTCOME-0001`
# -- not as an `edges:` entry. Both are real conventions in the mesh, and a walker that reads
# only `edges:` silently misses the ENTIRE outcome->story traceability chain, which is the one
# structure the vocabulary says Group B exists to form. Missing edges are the dangerous kind of
# invisible: the check passes, so the chain looks verified when nothing looked at it.
PARENT_KEY = re.compile(
    r"^(parent-(?:outcome|opportunity|solution|epic|story)):\s*(\S+)\s*$", re.M)

# A staging candidate's promotion destination, declared as a bare top-level `target:` key.
# This is NOT an edge, but it is a reference, and it is the single most consequential one in
# the file: it is where promotion will write the claim. It went unchecked until the fixtures
# were re-qualified for the single-Hub layout and a deliberately-broken target sailed through
# -- the same fail-open shape as the `parent-of` chain being invisible. `null` is legal and
# meaningful (the "no home in this mesh" finding), so it is skipped rather than flagged.
TARGET_KEY = re.compile(r"^target:\s*(\S+)\s*$", re.M)

# `duplicate_of:` -- another bare top-level key, set by dedup to whatever already carries the
# claim. Two shapes are legal, because dedup now compares against two things: a Hub-relative
# PATH when canonical context already says it, or a candidate ID when an unpromoted candidate
# from an earlier ingestion does (added 2026-08-14). Both resolve through the same machinery.
#
# It is walked for the reason `target:` is: it is a reference, and an unwalked reference is
# invisible rather than merely unchecked. The staged case makes that sharper -- the candidate
# it names may be promoted or dropped later, so this is a pointer that can go stale AFTER
# being written correctly, which is exactly when nobody thinks to look at it again.
DUPLICATE_OF_KEY = re.compile(r"^duplicate_of:\s*(\S+)\s*$", re.M)

# A `Workflow`'s `external_ref` was walked here until v2.2 deferred the workflow layer.
# The check is gone with the type, but the finding is worth carrying: it was fail-open #8
# (2026-07-30) -- a workflow pointing at a nonexistent directory passed clean, because the
# walker read `edges:`, `parent-*:` and `target:` and nothing else. If workflows return, the
# pointer is the entire value of a pointer type, so the reference must be walked with it.
# The design is retained privately.


def parse_edges(text):
    """Pull (edge, target) pairs out of a file's YAML frontmatter.

    Handles both conventions the mesh uses: an explicit `edges:` list, and the OST's bare
    `parent-*:` keys (normalised to `parent-of`, the vocabulary's edge name).

    Deliberately a small regex parser rather than a YAML dependency: the mesh is a dumb
    markdown substrate and the skills must run with nothing installed.
    """
    m = FRONTMATTER.search(text)
    if not m:
        return []
    fm = m.group(1)

    out, current = [], None
    for line in fm.splitlines():
        e = re.match(r"^\s*-\s*edge:\s*(\S+)", line)
        if e:
            current = e.group(1)
            continue
        t = re.match(r"^\s*target:\s*(\S.*?)\s*$", line)
        if t and current:
            out.append((current, t.group(1).strip().strip("'\"")))
            current = None

    tm = TARGET_KEY.search(fm)
    if tm:
        dest = tm.group(1).strip().strip("'\"")
        if dest.lower() not in ("null", "~", "none"):
            out.append(("target", dest))

    dm = DUPLICATE_OF_KEY.search(fm)
    if dm:
        dest = dm.group(1).strip().strip("'\"")
        if dest.lower() not in ("null", "~", "none"):
            out.append(("duplicate_of", dest))

    for pm in PARENT_KEY.finditer(fm):
        # Reported as `parent-of` so a broken traceability link reads in the vocabulary's
        # terms, not the file's spelling. The direction is inverted from the vocabulary's
        # (parent -> child); what is being checked is that the named parent EXISTS.
        out.append(("parent-of", pm.group(2).strip().strip("'\"")))

    return out


def find_domains(hub_root):
    """Domain folders in the Hub: the directories under `domains/`.

    v2.2: a domain is declared by its location, not detected from what it holds. Every
    directory under `domains/` is one -- including a scaffolded folder that has no index
    yet, which the previous rule (any subdirectory holding a context-index.md) silently
    skipped. A domain the walker cannot see is a domain whose edges go unchecked.
    """
    domains = {}
    root = os.path.join(hub_root, DOMAINS_DIR)
    if not os.path.isdir(root):
        return domains
    for entry in sorted(os.listdir(root)):
        path = os.path.join(root, entry)
        if entry.startswith(".") or not os.path.isdir(path):
            continue
        domains[entry] = path
    return domains


def collect_ids(hub_root, domains):
    """Every node ID declared anywhere in the Hub, and the ID'd artifact IDs."""
    node_ids, artifact_ids = set(), set()
    scopes = [("", hub_root)] + sorted(domains.items())
    seen_dirs = set()
    for domain_name, scope_path in scopes:
        for dirpath, dirnames, filenames in os.walk(scope_path):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            # The root scope walks into `domains/` too; don't double-count them.
            if not domain_name:
                dirnames[:] = [d for d in dirnames if d != DOMAINS_DIR]
            if dirpath in seen_dirs:
                continue
            seen_dirs.add(dirpath)
            for f in filenames:
                if not f.endswith(".md"):
                    continue
                try:
                    with open(os.path.join(dirpath, f)) as fh:
                        head = fh.read(4000)
                except OSError:
                    continue
                # ONLY a declared `id:` counts as an artifact existing.
                #
                # An earlier cut scraped any `OPP-NNNN`-shaped string out of the file text,
                # which made every reference self-satisfying: writing
                # `parent-opportunity: OPP-9999` registered OPP-9999 as existing, so the link
                # validated against itself and NO parent link could ever dangle. Verified by
                # breaking a real parent link and watching the check pass.
                #
                # A mention is not a declaration. Only the `id:` line declares.
                m = re.search(r"^id:\s*(\S+)\s*$", head, re.M)
                if not m:
                    continue
                declared = m.group(1).strip().strip("'\"")
                if BARE_ARTIFACT_ID.match(declared):
                    artifact_ids.add(f"{domain_name}:{declared}" if domain_name else declared)
                elif ARTIFACT_ID.match(declared):
                    artifact_ids.add(declared)
                else:
                    node_ids.add(declared)
    return node_ids, artifact_ids


def resolve(edge, target, domain_name, hub_root, domains, node_ids, artifact_ids):
    """Classify and resolve one edge target. Returns (kind, ok, detail)."""

    # THE EXCEPTION, and it runs first -- before any path logic can mislabel a board ID
    # as a dangling file.
    if edge == "rendered-on":
        if looks_like_path(target):
            return ("board", False,
                    f"`rendered-on` points at a path (`{target}`). A board is an external "
                    f"VIEW addressed by ID, never a file -- a file target would make the "
                    f"board canonical, which board-sidecars.md forbids.")
        if not BOARD_REF.match(target):
            return ("board", False,
                    f"`rendered-on` target `{target}` is not a board reference. Expected "
                    f"`<vendor>:board:<id>` (e.g. `miro:board:uXjVA1b2c3`).")
        # Correct, and deliberately NOT checked further. Whether that board exists is a
        # question for the vendor's API, not for a mesh validator -- and reaching out to
        # answer it would couple the mesh to a vendor. Off-filesystem is the whole point.
        return ("board", True, "off-filesystem board reference (not checked -- by design)")

    # A non-rendered-on edge pointing at something board-shaped is the inverse mistake.
    if BOARD_REF.match(target) and not looks_like_path(target) \
            and not ARTIFACT_ID.match(target) and not NODE_ID.match(target) \
            and target not in domains:
        return ("unknown", False,
                f"`{edge}` points at what looks like a board reference (`{target}`). Only "
                f"`rendered-on` may target a Board.")

    if ARTIFACT_ID.match(target):
        if target in artifact_ids:
            return ("artifact-id", True, "")
        return ("artifact-id", False, f"no artifact `{target}` found in the mesh.")

    # An UNPREFIXED artifact ID (`OUTCOME-0001`) -- the OST's own convention for pointing at
    # a sibling. It resolves in the DECLARING domain: the same ID may exist in another domain
    # and means a different thing there.
    if BARE_ARTIFACT_ID.match(target):
        qualified = f"{domain_name}:{target}" if domain_name else target
        if qualified in artifact_ids:
            return ("artifact-id", True, "")
        where = domain_name or "the Hub root"
        return ("artifact-id", False,
                f"no artifact `{target}` in {where} (looked for `{qualified}`). "
                f"Unprefixed IDs resolve in the declaring domain.")

    if NODE_ID.match(target):
        if target in node_ids:
            return ("node-id", True, "")
        return ("node-id", False, f"no node with id `{target}` found in the mesh.")

    if target in domains:
        return ("domain", True, "")

    if looks_like_path(target):
        # Every path is Hub-relative -- one candidate, no guessing, no declaring-repo context.
        full = os.path.join(hub_root, target)
        if os.path.isfile(full):
            return ("path", True, "")
        return ("path", False, f"`{target}` does not exist ({full}).")

    return ("unknown", False, f"cannot classify target `{target}`.")


def main():
    argv = sys.argv[1:]
    as_json = "--json" in argv
    quiet = "--quiet" in argv
    args = [a for a in argv if not a.startswith("--")]

    if len(args) != 1:
        print(__doc__)
        return 2

    hub_root = args[0]
    if not os.path.isdir(hub_root):
        print(f"error: not a directory: {hub_root}", file=sys.stderr)
        return 2

    if not os.path.isfile(os.path.join(hub_root, "context-index.md")):
        print(f"error: no context-index.md at {hub_root} -- is this the Hub root?",
              file=sys.stderr)
        return 2

    domains = find_domains(hub_root)
    node_ids, artifact_ids = collect_ids(hub_root, domains)

    rows = []
    for dirpath, dirnames, filenames in os.walk(hub_root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        # Which domain declared this file? "" means the cross-cutting root. This decides
        # only how an UNPREFIXED artifact ID resolves; paths are Hub-relative regardless.
        # A domain path is `domains/<name>/...`, so the name is the SECOND segment (v2.2).
        rel = os.path.relpath(dirpath, hub_root)
        parts = [] if rel == "." else rel.split(os.sep)
        domain_name = ""
        if len(parts) >= 2 and parts[0] == DOMAINS_DIR and parts[1] in domains:
            domain_name = parts[1]
        for f in sorted(filenames):
            if not f.endswith(".md"):
                continue
            path = os.path.join(dirpath, f)
            try:
                with open(path) as fh:
                    text = fh.read()
            except OSError:
                continue
            for edge, target in parse_edges(text):
                kind, ok, detail = resolve(edge, target, domain_name, hub_root,
                                           domains, node_ids, artifact_ids)
                rows.append({
                    "domain": domain_name or "(root)",
                    "file": os.path.relpath(path, hub_root),
                    "edge": edge,
                    "target": target,
                    "kind": kind,
                    "ok": ok,
                    "detail": detail,
                })

    bad = [r for r in rows if not r["ok"]]

    if as_json:
        print(json.dumps({"edges": rows, "broken": len(bad)}, indent=2))
        return 1 if bad else 0

    if quiet:
        return 1 if bad else 0

    boards = [r for r in rows if r["kind"] == "board" and r["ok"]]
    print(f"Reference check: {len(rows)} edge(s) across {len(domains)} domain(s) + root")
    print()

    if bad:
        print(f"BROKEN ({len(bad)}):")
        print()
        for r in bad:
            print(f"  {r['file']}")
            print(f"      {r['edge']} -> {r['target']}")
            print(f"      {r['detail']}")
        print()

    by_kind = {}
    for r in rows:
        if r["ok"]:
            by_kind[r["kind"]] = by_kind.get(r["kind"], 0) + 1
    if by_kind:
        print("Resolved:")
        for k in sorted(by_kind):
            print(f"  {by_kind[k]:3}  {k}")
        print()

    if boards:
        print(f"{len(boards)} board reference(s) accepted as off-filesystem -- a `rendered-on`")
        print("target is a view in Miro/Claude Design, not a file. Not a dangling link.")
        print()

    if not bad:
        print("OK. Every edge resolves.")

    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
