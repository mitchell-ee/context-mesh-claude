#!/usr/bin/env python3
"""Survey a repo that is not yet a mesh: what context already exists, and what is missing.

`survey_mesh.py` answers "is this mesh set up correctly?" -- it reads the indexes and checks
what they declare. That question is useless before an index exists, and it is exactly the
moment setup runs. This script answers the earlier question:

    What context does this repo ALREADY have, and how should it be declared?

READ-ONLY. Writes nothing, ever, and proposes rather than decides -- every output here is a
suggestion for a human to confirm, because the two things an index row needs (what a file is
about, when to load it) are things only they know.

## Two halves, and the second one is the easy one to get wrong

  FOUND    markdown that exists here, classified into the three kinds of home
  MISSING  kinds of context the repo appears not to have, as a SHORT list

For MISSING, recommend the HIGHEST-LEVEL artifact that closes the gap. A repo with no
architecture documentation needs `technical/architecture.md` -- not a six-file decomposition
into target-architecture, integration-map, api-standards, nfr, and two more. Splitting is a
later move, made when a real file grows too big to load for one task. Recommending the split
version to a team that has nothing is how a setup tool produces eighteen empty files and a
mesh nobody fills in.

## What this deliberately does NOT do

It does not detect domains, and must never be made to. A domain is a directory under
`domains/` and nothing else is one. The pre-v2.2 heuristic accepted any top-level directory
containing `product/`, `technical/`, or `process/`, and in the first third-party run it
reported a `docs/product/` market-research folder as a domain while the real one went
undetected. Grouping proposals by existing directory is NOT that heuristic -- it makes no
claim about what any directory IS.

It does not write an index, create a file, or move anything. `scaffold_domain.py` is the only
writer in this skill, and it creates containers only.

Usage:
    survey_repo.py <repo-root>
    survey_repo.py <repo-root> --json

Exit codes: 0 = surveyed (always, if the input was readable), 2 = bad input.
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_setup  # noqa: E402  (one definition of what an index is, never a second)

INDEX = check_setup.INDEX

# Directories that are never context, whatever they contain. Kept deliberately short: this is
# not a heuristic for what IS context, only a list of things that certainly are not. A false
# entry here HIDES real context, so it stays boring.
SKIP_DIRS = {
    ".git", ".github", "node_modules", "venv", ".venv", "__pycache__", "dist", "build",
    "target", "vendor", ".idea", ".vscode", "coverage", ".next", ".cache", "staging",
    # Tooling that DESCRIBES a mesh rather than being one. Without these, running this
    # against a repo that packages context-mesh itself proposed `skills/setup-mesh/SKILL.md`
    # as product context -- confidently, and wrongly. A mesh's own machinery is not context
    # about the product, and neither is a test fixture.
    "skills", "prompts", "test-mesh", "templates", "migrations",
}

# Files that are repo furniture rather than context. LICENSE and CHANGELOG are generated or
# legal; CONTRIBUTING and README are about the repo, not the product it describes -- a README
# is proposed separately below rather than skipped, because it is so often the only real
# context a repo has.
SKIP_FILES = {"LICENSE.md", "CHANGELOG.md", "CODE_OF_CONDUCT.md", "SECURITY.md",
              # The index is the thing being written, not a row in itself. Proposing it as
              # context produces an index that lists itself.
              INDEX}

# The folder names the plugin already knows the shape of. These are NOT proposed as
# collections: their layout, IDs, and parent chain are fixed, so they need no declaration.
KNOWN_STRUCTURES = {"opportunity-solution-tree", "iterations", "decisions"}

# A collection is many files of one kind in one folder. Below this, a folder is more likely to
# be two unrelated documents that happen to share a directory, and proposing a collection row
# for it would invent a "kind of context" the team never had. Two is the honest floor for
# "many", and the human confirms either way.
COLLECTION_MIN = 2

# The default manifest, reduced to the GAPS WORTH NAMING. Each entry is the highest-level
# artifact that covers its area -- deliberately not the full manifest, which runs to ~25 files
# across four trees. `covered_by` lists path fragments that mean "they already have this,
# however they named it", so a repo with `docs/architecture/overview.md` is not told to write
# an architecture doc.
#
# The wording matters: these are things a team may or may not have, not a checklist to
# complete. Every row in the real manifest is optional and this is a subset of it.
GAP_CHECKS = [
    {
        "recommend": "technical/architecture.md",
        "about": "how the system is put together — structure, key components, how they talk",
        "covered_by": ["architecture", "system-design", "technical-design", "hld", "design-doc"],
    },
    {
        "recommend": "product/business-context.md",
        "about": "why this exists, what problem it solves, who depends on it",
        "covered_by": ["business-context", "product-overview", "vision", "charter", "why"],
    },
    {
        "recommend": "technical/coding-standards.md",
        "about": "language and style conventions, patterns, anti-patterns",
        "covered_by": ["coding-standard", "style-guide", "conventions", "contributing"],
    },
    {
        "recommend": "process/ways-of-working.md",
        "about": "how work flows from idea to deployed — rituals, handoffs, who decides",
        "covered_by": ["ways-of-working", "process", "workflow", "runbook", "onboarding"],
    },
    {
        "recommend": "product/glossary.md",
        "about": "domain terms and shared vocabulary",
        "covered_by": ["glossary", "terminology", "ubiquitous-language"],
    },
]


def walk_markdown(root):
    """Every .md file in the repo, repo-relative, minus the obvious non-context.

    Fails CLOSED on an unreadable directory. `os.walk` swallows OSError by default, so a
    directory the walker cannot descend into simply never appears -- not found, not empty, and
    not an error. Here that would silently under-report what the repo holds and produce
    confident recommendations to write files that already exist. (fail-open #12's shape.)
    """
    found, errors = [], []

    def on_error(exc):
        errors.append((getattr(exc, "filename", "?"), str(exc)))

    for dirpath, dirnames, filenames in os.walk(root, onerror=on_error):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for f in sorted(filenames):
            if not f.endswith(".md") or f in SKIP_FILES:
                continue
            rel = os.path.relpath(os.path.join(dirpath, f), root)
            found.append(rel.replace(os.sep, "/"))
    return sorted(found), errors


def already_declared(root):
    """Paths any existing index already lists, so the survey never re-proposes them.

    A repo part-way through setup is the normal case for a re-run, and proposing rows that
    already exist would make the second run look like the first did nothing.
    """
    declared = set()
    for base, _, _ in os.walk(root):
        idx = os.path.join(base, INDEX)
        if not os.path.isfile(idx):
            continue
        try:
            with open(idx) as fh:
                text = fh.read()
        except OSError:
            continue
        prefix = os.path.relpath(base, root).replace(os.sep, "/")
        prefix = "" if prefix == "." else prefix + "/"
        for rel in check_setup.find_listed_files(text):
            declared.add((prefix + rel).lstrip("./"))
        for rel in check_setup.find_listed_collections(text):
            declared.add((prefix + rel).lstrip("./"))
    return declared


def classify(paths):
    """Sort found markdown into the three kinds of home.

    Groups by parent directory, because that is the only signal available that does not
    require reading the files: a directory holding several markdown files is what a collection
    looks like on disk. This is a PROPOSAL for a human to confirm, never a determination --
    which is the difference between this and the domain-detection heuristic v2.2 deleted.
    """
    by_dir = {}
    for p in paths:
        by_dir.setdefault(os.path.dirname(p), []).append(p)

    known, collections, singletons = [], [], []
    for d, files in sorted(by_dir.items()):
        # Match ANY path segment, not just the last one. An OST holds its artifacts in
        # `opportunity-solution-tree/opportunities/`, so testing only the basename saw
        # `opportunities` -- not a known name -- and proposed a collection row for a
        # structure whose layout is already fixed. Confirmed by running it against
        # test-mesh, where exactly that happened.
        segments = set(d.split("/"))
        if segments & KNOWN_STRUCTURES:
            known.append({"dir": d + "/", "count": len(files)})
        elif len(files) >= COLLECTION_MIN and d:
            collections.append({"dir": d + "/", "count": len(files),
                                "members": sorted(files)})
        else:
            singletons.extend(sorted(files))
    return known, collections, sorted(singletons)


def find_gaps(paths):
    """Which GAP_CHECKS this repo appears not to cover.

    Matches a fragment against each path SEGMENT, not against the whole path joined into one
    string. Joining everything made the haystack so large that unrelated files satisfied every
    check -- run against this repo, `docs/how-it-works.md` matched "workflow" via
    `workflow-routing.md` and the gap list came back empty for a repo with no ways-of-working
    doc at all. A per-segment match still accepts `docs/architecture/overview.md`, which is the
    case the loose match existed for.

    This errs toward SILENCE: a fragment that appears anywhere in a path suppresses the
    recommendation. Telling a team to write a file they already have, under another name, is
    worse than staying quiet -- they lose trust in every other line of the report.
    """
    segments = set()
    for p in paths:
        for seg in p.lower().replace("_", "-").split("/"):
            segments.add(seg)
            segments.add(seg[:-3] if seg.endswith(".md") else seg)

    def covered(g):
        return any(frag in seg for seg in segments for frag in g["covered_by"])

    return [g for g in GAP_CHECKS if not covered(g)]


def survey(root):
    paths, walk_errors = walk_markdown(root)
    declared = already_declared(root)
    undeclared = [p for p in paths if p not in declared]

    known, collections, singletons = classify(undeclared)
    return {
        "root": root,
        "has_index": os.path.isfile(os.path.join(root, INDEX)),
        "total_markdown": len(paths),
        "already_declared": len(paths) - len(undeclared),
        "known_structures": known,
        "collections": collections,
        "singletons": singletons,
        "gaps": find_gaps(paths),
        "walk_errors": walk_errors,
    }


def report(s):
    root = s["root"]
    print(f"Repo survey: {root}")
    print()

    if s["walk_errors"]:
        print("UNREADABLE -- this survey is INCOMPLETE, and its recommendations may be wrong:")
        for path, err in s["walk_errors"]:
            print(f"  {path}  ({err})")
        print("  A directory that cannot be read looks exactly like one holding no context,")
        print("  so the gaps below may name files that already exist. Fix access and re-run.")
        print()

    if s["has_index"]:
        print(f"A {INDEX} already exists here. {s['already_declared']} file(s) are already")
        print("declared and are not re-proposed below.")
    else:
        print(f"No {INDEX} yet. Everything below is a proposal for one.")
    print()

    print(f"Found {s['total_markdown']} markdown file(s) that could be context.")
    print()

    if s["known_structures"]:
        print("KNOWN STRUCTURES -- the plugin already knows these; declare nothing.")
        for k in s["known_structures"]:
            print(f"  {k['dir']:44} {k['count']} file(s)")
        print()

    if s["collections"]:
        print("PROPOSED COLLECTIONS -- many files of one kind; ONE index row covers the folder.")
        for c in s["collections"]:
            print(f"  {c['dir']:44} {c['count']} file(s)")
            for m in c["members"][:3]:
                print(f"      {os.path.basename(m)}")
            if c["count"] > 3:
                print(f"      ... and {c['count'] - 3} more")
        print()
        print("  Confirm each: is this really one KIND of context, or unrelated documents")
        print("  that share a folder? A collection row claims they are the same kind.")
        print()

    if s["singletons"]:
        print("PROPOSED SINGLETONS -- one file, one row each.")
        for p in s["singletons"]:
            print(f"  {p}")
        print()

    if not s["known_structures"] and not s["collections"] and not s["singletons"]:
        print("No undeclared markdown found. Nothing to propose.")
        print()

    if s["gaps"]:
        print("POSSIBLY MISSING -- kinds of context this repo does not appear to have.")
        print("Each is the HIGHEST-LEVEL file that covers its area. Split later, if one")
        print("grows too big to load for a single task -- do not start with the split.")
        print()
        for g in s["gaps"]:
            print(f"  {g['recommend']}")
            print(f"      {g['about']}")
        print()
        print("  These are OPTIONAL. A repo without design principles is not a broken repo;")
        print("  it is a repo without design principles. Recommend, never require -- and")
        print("  never create one empty: an indexed file that says nothing is worse than an")
        print("  absent one, because routing believes the index.")
        print()

    print("Nothing was written. Confirm what is right, then declare it in the index --")
    print("each row needs what the file is ABOUT and WHEN TO LOAD it, which only you know.")


def main():
    argv = sys.argv[1:]
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 1:
        print(__doc__)
        return 2

    root = args[0]
    if not os.path.isdir(root):
        print(f"error: not a directory: {root}", file=sys.stderr)
        return 2

    s = survey(root)
    if "--json" in argv:
        print(json.dumps(s, indent=2))
    else:
        report(s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
