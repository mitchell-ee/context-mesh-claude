#!/usr/bin/env python3
"""Check whether the Hub root, or one domain folder, is set up to receive ingested context.

Answers one question: can ingestion actually run here? Two things decide it --
  1. an index exists (routing reads it, and only it)
  2. it lists something, and what it lists is real

Deliberately does NOT check for the default manifest's context files. The file list is the
manifest -- per-implementation config, not a spec to conform to. A repo missing
`design-principles.md` isn't broken; it's a repo without design principles. Absent files are
an honest gap ingestion reports when it hits them.

Workflow config was check #3 through v2.1 ("a workflow is declared, or every Todo is
unroutable"). The whole workflow layer is deferred as of vocabulary v2.2 -- the mesh holds
context, not work; the design is retained privately.

Usage:
    check_setup.py <hub-root-or-domain-dir>
    check_setup.py <hub-root-or-domain-dir> --quiet

Exit codes: 0 = ingestion can run, 1 = it cannot (or would misroute), 2 = bad input.
"""

import os
import re
import sys

INDEX = "context-index.md"

# A markdown link to a repo-relative .md file: [label](path/to/file.md)
#
# This regex is the ONLY way a context file gets declared, which makes it a convention the
# author has to know about. It is stated in templates/context-index.md, which ships an
# example row -- earlier it shipped an empty table and said nothing, and an index written
# with backticked paths parsed to zero files while reporting READY (fail-open #9).
LINK = re.compile(r"\[[^\]]+\]\(([^)#]+\.md)\)")

# HTML comments are guidance for the author, not entries. The index templates explain the
# row format inside a comment, and a commented-out row is a normal way to park an entry --
# in both cases the text is NOT a claim that the file exists, so parsing it would report a
# missing file the index never actually listed. Stripped before any link is read.
COMMENT = re.compile(r"<!--.*?-->", re.S)


def find_listed_files(index_text):
    """Paths the index links to, minus external/absolute ones we can't check.

    A `../`-prefixed link used to be skipped wholesale as "cross-repo, not ours to verify".
    With all context in one Hub that is too broad: a domain index linking
    `../product/personas/repeat-buyer.md` at the cross-cutting root is an ordinary reference
    inside the same repo, and it is checkable. Skipping it would be a fail-open hole of exactly
    the kind this project keeps finding.

    What still cannot be checked is a link that climbs *past* the root -- documentation
    outside the mesh entirely. The caller resolves against the root and knows where that is,
    so both kinds are returned and the caller decides; see `find_missing`.
    """
    out = []
    for m in LINK.finditer(COMMENT.sub("", index_text)):
        p = m.group(1).strip()
        if p.startswith(("http://", "https://", "/")):
            continue
        out.append(p)
    return sorted(set(out))


def escapes_root(base, rel_path, root):
    """Does this link resolve outside the mesh root? Then it is not ours to verify."""
    full = os.path.abspath(os.path.join(base, rel_path))
    root = os.path.abspath(root)
    return not full.startswith(root + os.sep)


def find_missing(listed, base, root=None):
    """Which listed files don't exist. Links escaping `root` are skipped, not reported.

    `root` defaults to `base` (the single-directory case). Pass the Hub root when checking a
    domain folder, so a domain's link up to the cross-cutting root is verified rather than
    skipped -- it is inside the same repo.
    """
    root = root or base
    out = []
    for p in listed:
        if escapes_root(base, p, root):
            continue
        if not os.path.isfile(os.path.join(base, p)):
            out.append(p)
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    quiet = "--quiet" in sys.argv

    if len(args) != 1:
        print(__doc__)
        return 2

    repo = args[0]
    if not os.path.isdir(repo):
        print(f"error: not a directory: {repo}", file=sys.stderr)
        return 2

    problems, notes = [], []

    # 1. The index.
    index_path = os.path.join(repo, INDEX)
    if not os.path.isfile(index_path):
        problems.append(
            f"No {INDEX}. Routing reads the index and only the index -- without one, this "
            f"repo is invisible to ingestion. Run setup-mesh job 1.")
        if not quiet:
            report(repo, problems, notes)
        return 1

    with open(index_path) as fh:
        index_text = fh.read()

    # 2. Does it list anything at all?
    #
    # An index that parses to ZERO files used to sail through: find_missing() had nothing
    # to iterate, no problem was appended, and the report printed "READY. An index exists,
    # what it lists is real" -- a claim about an empty set. That is fail-open #9, and the
    # one that mattered most, because READY is the gate for running ingestion. Routing
    # reads the index and only the index; an index listing nothing routes nothing.
    #
    # The usual cause is not an empty index but an index whose rows aren't markdown links
    # (backticked paths, plain text), so LINK matches none of them. Say that out loud --
    # the author's index may look complete to them.
    listed = find_listed_files(index_text)
    if not listed:
        # A NOTE, not a problem -- but it must be said out loud, which is the whole fix.
        # This case used to be invisible: zero listed files meant find_missing() had
        # nothing to iterate, no problem was raised, and the report printed "READY ...
        # what it lists is real" -- a claim about an empty set (fail-open #9). READY is
        # the gate for running ingestion, so a silent pass here is the worst of them.
        #
        # It is not BLOCKED because `scaffold_domain.py` deliberately writes an index with
        # no rows: a container, never a claim. Calling the scaffold's own output broken
        # would make the two scripts contradict each other, which is the shape of the bug
        # that started this. Empty is an honest gap to fill, not an error -- so say so,
        # name the usual cause, and let the READY line stop over-claiming.
        notes.append(
            f"{INDEX} lists no context files, so routing can see nothing here yet. Rows are "
            f"only read as markdown links -- `[label](technical/system-behavior.md)`; a "
            f"backticked or plain-text path parses to nothing. If this is a fresh scaffold, "
            f"this is expected: fill the index in before ingesting here.")

    # 3. Does what it lists exist?
    missing = find_missing(listed, repo)
    for p in missing:
        problems.append(
            f"Index lists `{p}` but the file does not exist. Ingestion will route facts to "
            f"it and they will land in a vacuum. Remove the entry, or create the file.")

    # 4. Present but unlisted -- invisible to routing.
    #
    # Only PATH-REFERENCED singletons need a link. Discovery artifacts (the OST) are
    # ID-referenced by design: the index lists the tree as IDs + titles so an agent can
    # reference payments:OPP-0001 without loading the file. That IS progressive
    # disclosure -- demanding a link per artifact would invert it, and would mean re-editing
    # the index on every new opportunity.
    listed_set = set(listed)
    ost_ids = set(re.findall(
        r"\b(OUTCOME|OPP|SOL|ASSUMPTION|STORY|EPIC)-(\d{4})\b", index_text))

    for sub in ("technical", "product", "process"):
        d = os.path.join(repo, sub)
        if not os.path.isdir(d):
            continue
        for root, _, files in os.walk(d):
            for f in files:
                if not f.endswith(".md"):
                    continue
                rel = os.path.relpath(os.path.join(root, f), repo)
                if rel in listed_set:
                    continue

                # An ID'd discovery artifact is declared by its ID, not a link.
                m = re.search(
                    r"(outcome|opportunity|solution|assumption|story|epic)-(\d{4})",
                    os.path.basename(rel))
                if m:
                    prefix = {"outcome": "OUTCOME", "opportunity": "OPP", "solution": "SOL",
                              "assumption": "ASSUMPTION", "story": "STORY", "epic": "EPIC"}
                    if (prefix[m.group(1)], m.group(2)) in ost_ids:
                        continue  # declared by ID in the index tree. Correct.
                    notes.append(
                        f"`{rel}` is a discovery artifact whose ID is not in the index's "
                        f"tree -- an agent cannot reference it.")
                    continue

                notes.append(
                    f"`{rel}` exists but is not listed in the index -- routing cannot see it.")

    if quiet:
        return 1 if problems else 0

    report(repo, problems, notes)
    return 1 if problems else 0


def report(repo, problems, notes):
    print(f"Setup check: {repo}")
    print()

    if problems:
        print(f"BLOCKED ({len(problems)}) -- ingestion cannot run correctly here:")
        print()
        for p in problems:
            print(f"  - {p}")
        print()

    if notes:
        print(f"Notes ({len(notes)}) -- not blocking:")
        print()
        for n in notes:
            print(f"  - {n}")
        print()

    if not problems:
        # The verdict must not claim more than was checked. "What it lists is real" is
        # vacuously true of an empty list, which is precisely how fail-open #9 read as a
        # pass -- so an index that lists nothing gets its own wording.
        empty = any("lists no context files" in n for n in notes)
        if empty:
            print("READY to run -- but NOTHING TO ROUTE TO. The index exists and nothing in "
                  "it is broken, because it lists nothing (see notes). Ingestion will report "
                  "every fact as having no home until the index lists a file.")
        else:
            print("READY. An index exists, it lists context files, and those files are real.")
        print()
        print("Missing context files are NOT checked -- the file list is the manifest, and a")
        print("repo without a given file is a repo without that context, not a broken repo.")
        print("Ingestion reports those gaps honestly when it hits them.")


if __name__ == "__main__":
    sys.exit(main())
