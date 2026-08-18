#!/usr/bin/env python3
"""Check whether the Hub root, or one domain folder, is set up to receive ingested context.

Answers one question: can ingestion actually run here? Two things decide it --
  1. an index exists (routing reads it, and only it)
  2. it lists something, and what it lists is real -- context FILES (singletons, linked by
     path) and COLLECTIONS (folders of same-typed files, linked with a trailing slash)

Deliberately does NOT check for the default manifest's context files. The file list is the
manifest -- per-implementation config, not a spec to conform to. A repo missing
`design-principles.md` isn't broken; it's a repo without design principles. Absent files are
an honest gap ingestion reports when it hits them.

Workflow config was check #3 through v2.1 ("a workflow is declared, or every Todo is
unroutable"). The whole workflow layer is deferred as of vocabulary v2.2 -- the mesh holds
context, not work -- a queue is the work itself.

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

# A markdown link to a COLLECTION -- a folder of same-typed files addressed by path, where
# nothing traverses a member: [decisions/](decisions/). The trailing slash is what tells a
# collection from a singleton, for a human and for this regex both.
#
# This needs its own pattern because LINK requires a literal `.md`, so a directory target
# never matched it: the path was not extracted, not existence-checked, and a row pointing at
# a nonexistent folder passed while the verdict said "those files are real". Collections were
# not passing by accident -- they were invisible (fail-open #13).
COLLECTION_LINK = re.compile(r"\[[^\]]+\]\(([^)#]+/)\)")

# HTML comments are guidance for the author, not entries. The index templates explain the
# row format inside a comment, and a commented-out row is a normal way to park an entry --
# in both cases the text is NOT a claim that the file exists, so parsing it would report a
# missing file the index never actually listed. Stripped before any link is read.
COMMENT = re.compile(r"<!--.*?-->", re.S)

# The root index's `- **Mesh vocabulary:** v2.2` line -- the schema version this mesh's
# content is written in. Read from the ROOT index only; domains do not carry it.
VOCABULARY_LINE = re.compile(r"^\s*-\s*\*\*Mesh vocabulary:\*\*\s*(\S+)", re.M)


def read_vocabulary(index_text):
    """The mesh's declared vocabulary version, or None if unmarked.

    None is a normal state, not an error: every mesh scaffolded before the marker existed
    lacks one, and so does one whose index was hand-authored. It means "unknown", never
    "old" -- migrations decide whether they apply by inspecting DATA, not this value. The
    marker exists so setup can PROMPT; if it were the selector, an unmarked mesh would
    silently skip every migration.
    """
    m = VOCABULARY_LINE.search(COMMENT.sub("", index_text))
    return m.group(1).strip() if m else None


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


def find_listed_collections(index_text):
    """Collection folders the index links to, minus external/absolute ones we can't check.

    Same filtering as `find_listed_files`, on trailing-slash targets. Staging folders are
    excluded: the index's Staging table names `staging/candidates/` and friends as backticked
    text, not links, precisely because they are not context homes -- but a hand-authored index
    may link one anyway, and reporting a lazily-created staging folder as a broken collection
    would be a fail-CLOSED bug (broken when it isn't).
    """
    out = []
    for m in COLLECTION_LINK.finditer(COMMENT.sub("", index_text)):
        p = m.group(1).strip()
        if p.startswith(("http://", "https://", "/")):
            continue
        if p.split("/")[0] == "staging":
            continue
        out.append(p)
    return sorted(set(out))


def check_collections(listed, base, root=None):
    """Split declared collections into (missing, empty).

    Two different findings, deliberately:

      * MISSING -- the directory does not exist. The row points at nothing, which is an error.
      * EMPTY   -- the directory exists with no members. A NOTE, not an error, for the same
                   reason a listed-but-unwritten file is a pending home: the row declares
                   *where this kind of context goes*, and never claimed the folder was
                   occupied yet.

    Only `.md` members count. A folder holding just a README or a .gitkeep is empty as far as
    context is concerned, and saying otherwise would let a placeholder satisfy the check.
    """
    root = root or base
    missing, empty = [], []
    for p in listed:
        if escapes_root(base, p, root):
            continue
        full = os.path.join(base, p)
        if not os.path.isdir(full):
            missing.append(p)
            continue
        try:
            members = [f for f in os.listdir(full) if f.endswith(".md")]
        except OSError as exc:
            # Fail CLOSED: an unreadable directory is not an empty one. Guessing "empty"
            # here would report a populated collection as unfilled; guessing "fine" would
            # hide it entirely. Say what happened instead.
            missing.append(f"{p} (unreadable: {exc.strerror})")
            continue
        if not members:
            empty.append(p)
    return missing, empty


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
    #
    # A listed-but-missing file is a PENDING HOME, not a failure. The index row is a human's
    # declaration of *where this kind of context goes*, made before anyone wrote it -- it
    # never claimed the home was occupied. Promotion creates the file when it has content
    # for it (and updates the row), so this is a note about work not yet done, not a break.
    #
    # This used to be a `problem`, which withheld READY and blocked ingestion. That applied
    # the "never create an empty context file" rule at the wrong moment: setup must not
    # invent files, but the index legitimately lists files nobody has written yet.
    #
    # The cost of the change, stated honestly: a pending home and a TYPO'd path are the same
    # shape, and neither blocks now.
    #
    # NOTHING AUTOMATED CATCHES THE TYPO. `check_references.py` walks edges, not index rows,
    # so it passes a misspelled row exactly as it passes a real pending home. The guard that
    # remains is narrower than it sounds: promotion may only create a file for a row that
    # ALREADY EXISTED, so a typo cannot be invented and then self-certified in one motion --
    # but a human who typed the row wrong still gets a file at the misspelling.
    #
    # So this note IS the check. It names the paths and asks a person to read them, which is
    # why the verdict below states the count rather than passing silently.
    missing = find_missing(listed, repo)
    for p in missing:
        notes.append(
            f"Index lists `{p}` but it has not been written yet -- a pending home. Promotion "
            f"will create it when it has content for it. If the path is a typo, nothing else "
            f"will catch that, so check it here.")

    # 3b. Declared collections -- a folder of same-typed files, addressed by path.
    #
    # A MISSING directory is a problem: unlike a pending home, there is no promotion step that
    # creates a *folder* for a row. An EMPTY one is a note, for exactly the pending-home
    # reason -- the row says where this kind of context goes, not that any exists yet.
    collections = find_listed_collections(index_text)
    missing_dirs, empty_dirs = check_collections(collections, repo)
    for p in missing_dirs:
        problems.append(
            f"Index declares the collection `{p}` but no such directory exists. A collection "
            f"row points at a folder; nothing creates that folder for you.")
    for p in empty_dirs:
        notes.append(
            f"Collection `{p}` is declared but holds no .md members yet. That is a normal "
            f"state -- the row declares where this kind of context goes. Promotion adds "
            f"members when it has content for them.")

    # 4. Present but unlisted -- invisible to routing.
    #
    # Only PATH-REFERENCED singletons need a link. Discovery artifacts (the OST) are
    # ID-referenced by design: the index lists the tree as IDs + titles so an agent can
    # reference payments:OPP-0001 without loading the file. That IS progressive
    # disclosure -- demanding a link per artifact would invert it, and would mean re-editing
    # the index on every new opportunity.
    # Nor does a COLLECTION member. The whole point of a collection row is that one row
    # covers the folder -- flagging each member as unlisted would recreate the per-file rows
    # collections exist to avoid, and would punish a correctly declared collection with a
    # note per ADR.
    listed_set = set(listed)
    ost_ids = set(re.findall(
        r"\b(OUTCOME|OPP|SOL|ASSUMPTION|STORY|EPIC)-(\d{4})\b", index_text))
    collection_dirs = [os.path.normpath(c) for c in collections]

    def in_collection(rel):
        parent = os.path.dirname(os.path.normpath(rel))
        return any(parent == c or parent.startswith(c + os.sep) for c in collection_dirs)

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
                if in_collection(rel):
                    continue  # covered by its collection's row. Correct.

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

    report(repo, problems, notes, n_files=len(listed), n_collections=len(collections))
    return 1 if problems else 0


def report(repo, problems, notes, n_files=0, n_collections=0):
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
        # pass -- so an index that routes to nothing gets its own wording.
        #
        # `n_files`/`n_collections` are PASSED IN, not re-derived from the note text. Reading
        # them back out of prose would mean the verdict and the check could disagree while
        # looking consistent -- and a verdict that speaks only of files silently omits a
        # populated collection, which is how collections went unmentioned before (#13).
        pending = sum(1 for n in notes if "a pending home" in n)
        routable = n_files + n_collections

        if not routable:
            print("READY to run -- but NOTHING TO ROUTE TO. The index exists and nothing in "
                  "it is broken, because it lists nothing (see notes). Ingestion will report "
                  "every fact as having no home until the index lists a file.")
        else:
            # Name what was actually checked, in the units it was checked in.
            parts = []
            if n_files:
                parts.append(f"{n_files} context file{'s' if n_files != 1 else ''}")
            if n_collections:
                parts.append(
                    f"{n_collections} collection{'s' if n_collections != 1 else ''}")
            listed_desc = " and ".join(parts)

            if pending:
                # Say the count out loud rather than a bare READY. These rows are legitimate
                # (promotion fills them), but a typo has the same shape, and the number is
                # the only prompt a human gets to look.
                noun = "is a PENDING HOME" if pending == 1 else "are PENDING HOMES"
                print(f"READY. An index exists and it lists {listed_desc}. {pending} of the "
                      f"files {noun} -- declared but not yet written (see notes). That is a "
                      f"normal state; promotion creates them. Check they are not typos.")
            else:
                print(f"READY. An index exists, it lists {listed_desc}, and every listed "
                      f"path resolves to something real.")
        print()
        print("Missing context files are NOT checked -- the file list is the manifest, and a")
        print("repo without a given file is a repo without that context, not a broken repo.")
        print("Ingestion reports those gaps honestly when it hits them.")


if __name__ == "__main__":
    sys.exit(main())
