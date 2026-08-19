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
import staging_config  # noqa: E402  (likewise, for where staging lives)

INDEX = check_setup.INDEX

# Directories that are never context, whatever they contain. Kept deliberately short: this is
# not a heuristic for what IS context, only a list of things that certainly are not. A false
# entry here HIDES real context, so it stays boring.
# NOTE: staging is NOT in this set. It is a PATH, possibly nested (`docs/staging`), and this
# set is matched against single directory NAMES. Putting it here failed in both directions: a
# nested value never matched, so candidates were surveyed as context; and a value whose first
# segment is an ordinary folder (`docs/staging`) would have matched `docs` and skipped the
# entire documentation tree. `walk_markdown` prunes staging by path instead.
SKIP_DIRS = {
    ".git", ".github", "node_modules", "venv", ".venv", "__pycache__", "dist", "build",
    "target", "vendor", ".idea", ".vscode", "coverage", ".next", ".cache",
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

# A collection is many files of ONE KIND in one folder. Count alone does not establish that,
# and treating it as if it did was the bug this section exists to prevent: the test used to be
# `len(files) >= 2`, so any directory holding two markdown files became a proposed collection.
# Run against a normal repo, a `docs/` holding architecture.md, deployment.md, glossary.md and
# security-model.md -- four mutually exclusive singletons -- was proposed as a collection,
# which claims they are the same kind and that a fifth of them is coming. Proximity is not
# sameness. Two is still the floor for "many", but it is now necessary rather than sufficient.
COLLECTION_MIN = 2

# Folder names that ARE a collection kind, near enough to say so. This is the "obviously a
# collection of a type we recognize" test, and it is the strongest signal available without
# reading a single file. Kept to kinds that are genuinely many-of-one-thing by nature -- a
# folder called `docs` or `notes` is a location, not a kind, and must never appear here.
COLLECTION_DIR_NAMES = {
    "personas", "adr", "adrs", "decisions", "decision-records", "rfcs", "rfc",
    "journeys", "journey-maps", "runbooks", "postmortems", "post-mortems",
    "interviews", "playbooks", "policies", "profiles",
}

# Filenames that name a SINGLETON kind -- one of this thing exists, and a second would be a
# contradiction rather than a sibling. Their presence is positive evidence AGAINST the folder
# being a collection: a directory holding `architecture.md` is a place documents live, not a
# set of one kind. This is the inverse signal, and it outranks every other -- a folder with a
# recognized singleton in it is never proposed as a collection, whatever else it contains.
SINGLETON_STEMS = {
    "architecture", "glossary", "deployment", "security-model", "security", "roadmap",
    "onboarding", "troubleshooting", "faq", "overview", "vision", "charter", "readme",
    "coding-standards", "style-guide", "conventions", "ways-of-working", "process",
    "business-context", "product-overview", "system-design", "design-principles",
    "getting-started", "installation", "configuration", "changelog", "index",
}

# Member-name shapes that mean "these are siblings of one kind": `001-slug.md` and
# `2026-08-19-slug.md`. These are the two ordinal/dated patterns the taxonomy already names.
#
# NOTE, because it brushes against a rule: decisions.md section 8 says member naming patterns
# are OPAQUE -- used only to GENERATE a new member's name, never parsed to read meaning back
# out of an existing filename. That rule governs routing and promotion, where parsing a name
# would make the pattern into schema. This is neither: nothing here extracts data from a name
# or acts on it. It observes that several filenames share a shape, reports that shape to a
# human as its reason, and lets them decide. The pattern is evidence presented, not schema read.
ORDINAL_RE = re.compile(r"^\d{3,4}[-_]")
DATED_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[-_]")

# What fraction of a folder's members must share a naming shape before that shape counts as a
# signal. Not 1.0: a real ADR folder acquires a README or a template, and demanding purity
# would drop the folder over one stray file.
PATTERN_MIN_SHARE = 0.6

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

        # Prune staging BY PATH, not by directory name -- it may be nested (`docs/staging`),
        # in which case no single name identifies it. Checked against the path each child
        # would have, so the staging tree is never descended into and its candidates are never
        # proposed as context. Both the Hub root's staging and each domain's are caught,
        # because `is_staging_path` matches the segments at any offset.
        dirnames[:] = [
            d for d in dirnames
            if not staging_config.is_staging_path(
                os.path.relpath(os.path.join(dirpath, d), root))
        ]

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


def stem(path):
    """A filename reduced to its comparable core: no directory, no extension, `_` as `-`."""
    base = os.path.basename(path)
    if base.endswith(".md"):
        base = base[:-3]
    return base.lower().replace("_", "-")


def pattern_share(files):
    """The dominant member-name shape in a folder, and what fraction shares it.

    Returns (label, share). Reports the STRONGER shape when both appear, since a folder mixing
    `001-x.md` and `2026-01-01-y.md` is homogeneous under neither on its own but is plainly not
    a set of unrelated documents either.
    """
    if not files:
        return None, 0.0
    names = [os.path.basename(p) for p in files]

    # Test DATED first and let it win outright. `2026-01-05-standup.md` matches ORDINAL_RE too
    # -- `^\d{3,4}[-_]` accepts the four-digit year -- so scoring them independently and taking
    # the max reported a folder of dated meeting notes as "numbered `NNN-{slug}.md`". The
    # verdict was right and the REASON was wrong, which in a report whose whole purpose is to
    # show its reasoning is the more damaging half. Dated is the more specific pattern: every
    # dated name is an ordinal match, so it must be given the chance to claim its files first.
    dated = sum(1 for n in names if DATED_RE.match(n))
    if dated:
        return "dated `{date}-{slug}.md`", dated / len(names)

    ordinal = sum(1 for n in names if ORDINAL_RE.match(n))
    if ordinal:
        return "numbered `NNN-{slug}.md`", ordinal / len(names)

    return None, 0.0


def collection_evidence(d, files):
    """Why this folder looks like a collection -- or None if it does not.

    Positive recognition, not proximity. The old rule was `len(files) >= 2`, which made every
    directory with two markdown files a collection. This asks what the files ARE.

    Order matters. The singleton veto runs FIRST and outranks everything, because a recognized
    singleton is positive evidence the folder is a location rather than a kind: `architecture.md`
    is one-of-one by nature, so its neighbours are its neighbours, not its siblings.
    """
    if len(files) < COLLECTION_MIN or not d:
        return None

    # The veto. A folder holding a recognized singleton is a grab-bag, whatever else is true.
    vetoes = sorted({stem(f) for f in files} & SINGLETON_STEMS)
    if vetoes:
        return None

    # Strongest signal: the folder is NAMED as a kind we recognize.
    #
    # Strip the decorations teams put around the kind rather than demanding an exact match:
    # `Personas_Dir`, `ADRs/`, `docs-decisions` all name a kind we know, and matching only the
    # bare word missed every one of them. Confirmed on a fixture -- `Personas_Dir/` produced
    # nothing at all. The stripping is deliberately narrow (case, separators, a plural `s`, and
    # a short list of noise words) because each thing removed is a chance to match a folder
    # that never meant the kind at all.
    leaf = os.path.basename(d).lower().replace("_", "-")
    candidates = {leaf}
    parts = [p for p in leaf.split("-") if p and p not in {"dir", "docs", "doc", "folder", "all"}]
    if parts:
        candidates.add("-".join(parts))
        candidates.add(parts[-1])
    for c in list(candidates):
        if c.endswith("s"):
            candidates.add(c[:-1])
        else:
            candidates.add(c + "s")

    hit = candidates & COLLECTION_DIR_NAMES
    if hit:
        return (f"the folder name `{os.path.basename(d)}` names a kind "
                "that is many-of-one by nature")

    # Weaker but real: the members share a naming shape.
    label, share = pattern_share(files)
    if label and share >= PATTERN_MIN_SHARE:
        pct = round(share * 100)
        return f"{pct}% of members share a {label} naming shape"

    return None


def singleton_veto(files):
    """The recognized-singleton filenames in a folder, if any. Used for the mixed-folder note."""
    return sorted({stem(f) for f in files} & SINGLETON_STEMS)


def classify(paths):
    """Sort found markdown into the three kinds of home.

    Groups by parent directory, then asks of each group what its files ARE -- see
    `collection_evidence`. A folder with no collection evidence yields SINGLETONS, one row per
    file, which is the safe default: a wrong singleton row is one redundant line in an index,
    while a wrong collection row claims a kind the team never had and tells future ingestion to
    keep adding members to it.

    Every output is a PROPOSAL for a human to confirm, never a determination -- which is the
    difference between this and the domain-detection heuristic v2.2 deleted. The evidence is
    reported alongside each proposal so the human judges the reason, not just the verdict.
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
            continue

        why = collection_evidence(d, files)
        if why:
            collections.append({"dir": d + "/", "count": len(files),
                                "members": sorted(files), "why": why})
        else:
            singletons.extend(sorted(files))
    return known, collections, sorted(singletons)


def find_mixed(by_dir, collections):
    """Folders where single documents and a set-of-one-kind are tangled together.

    Two shapes, and the second was missed on the first pass. Both are reported as OBSERVATIONS,
    never demands -- the survey cannot tell which reading the team wants, so it names the
    situation, explains the consequence, and leaves the call to a human.

      PARENT  a folder holding individual documents that also PARENTS a collection.
              `docs/` with architecture.md and glossary.md, plus `docs/adr/` underneath.

      SPOILED a folder that would have been proposed as a collection, but holds a recognized
              singleton, so the veto suppressed it. `rfcs/` holding 0001-thing.md,
              0002-other.md and architecture.md. This is the case the veto exists for and it
              was going out SILENTLY -- three unexplained singleton rows, with the near-miss
              and its one-file cause invisible. A veto whose reason is never surfaced looks
              indistinguishable from the survey simply not recognizing the folder.
    """
    collection_dirs = {c["dir"].rstrip("/") for c in collections}
    mixed = []
    for d, files in sorted(by_dir.items()):
        if not d or d in collection_dirs:
            continue
        vetoes = singleton_veto(files)
        if not vetoes:
            continue

        nested = sorted(cd + "/" for cd in collection_dirs
                        if cd.startswith(d + "/") and cd != d)
        if nested:
            mixed.append({"dir": d + "/", "kind": "parent",
                          "singletons": vetoes, "collections": nested})
            continue

        # Would this have been a collection without the singleton(s) in it?
        rest = [f for f in files if stem(f) not in SINGLETON_STEMS]
        why = collection_evidence(d, rest)
        if why:
            mixed.append({"dir": d + "/", "kind": "spoiled",
                          "singletons": vetoes, "collections": [], "why": why})
    return mixed


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

    by_dir = {}
    for p in undeclared:
        by_dir.setdefault(os.path.dirname(p), []).append(p)

    return {
        "root": root,
        "has_index": os.path.isfile(os.path.join(root, INDEX)),
        "total_markdown": len(paths),
        "already_declared": len(paths) - len(undeclared),
        "known_structures": known,
        "collections": collections,
        "singletons": singletons,
        "mixed": find_mixed(by_dir, collections),
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
            print(f"      why: {c['why']}")
            for m in c["members"][:3]:
                print(f"      {os.path.basename(m)}")
            if c["count"] > 3:
                print(f"      ... and {c['count'] - 3} more")
        print()
        print("  What a collection row means, so you can judge these:")
        print("    - It says these files are all the SAME KIND, and more will arrive.")
        print("    - ONE row covers the whole folder, so the tenth member is not an index edit.")
        print("    - Ingestion may add members to it later, or modify an existing one.")
        print("  If a folder is really unrelated documents that share a directory, say so and")
        print("  take the singleton rows instead -- one row each, listed individually.")
        print()

    if s["singletons"]:
        print("PROPOSED SINGLETONS -- one file, one row each.")
        for p in s["singletons"]:
            print(f"  {p}")
        print()
        print("  Anything here that is really a set of one kind -- and should grow -- can be")
        print("  declared as a collection instead. This survey only proposes a collection when")
        print("  the folder name or the member names make the kind obvious, so it under-calls")
        print("  on purpose. You know your material better than the filenames do.")
        print()

    if s["mixed"]:
        print("MIXED FOLDERS -- worth a look, not an error.")
        for m in s["mixed"]:
            print(f"  {m['dir']}")
            if m["kind"] == "parent":
                print(f"      holds single documents: {', '.join(m['singletons'])}")
                print(f"      and also collection(s): {', '.join(m['collections'])}")
                print("      -> both a home for documents and a parent of a set. A collection")
                print("         row covers a folder, so a set nested inside a general-purpose")
                print("         folder can later read as though the PARENT were the collection.")
                print("         Moving the set somewhere of its own removes the ambiguity.")
            else:
                print(f"      would be a collection -- {m['why']}")
                print(f"      but also holds: {', '.join(m['singletons'])}")
                print("      -> so it was NOT proposed as a collection, and its files are")
                print("         listed individually above. Moving that one file out would make")
                print("         this a clean collection; so would leaving it and declaring")
                print("         nothing. Both are legitimate.")
        print()
        print("  Nothing here is broken, and neither shape is wrong -- these are flagged")
        print("  because the mesh represents them differently, and you are the one who knows")
        print("  which reading you meant. Leaving any of them exactly as they are is a fine")
        print("  answer; the survey has no opinion it is willing to act on.")
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
