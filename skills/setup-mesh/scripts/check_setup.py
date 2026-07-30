#!/usr/bin/env python3
"""Check whether the Hub root, or one domain folder, is set up to receive ingested context.

Answers one question: can ingestion actually run here? Three things decide it --
  1. an index exists (routing reads it, and only it)
  2. what it lists is real (a listed-but-missing file routes into a vacuum)
  3. a workflow is declared (or every Todo is unroutable)

Deliberately does NOT check for the default manifest's context files. The file list is the
manifest -- per-implementation config, not a spec to conform to. A repo missing
`design-principles.md` isn't broken; it's a repo without design principles. Absent files are
an honest gap ingestion reports when it hits them.

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
LINK = re.compile(r"\[[^\]]+\]\(([^)#]+\.md)\)")


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
    for m in LINK.finditer(index_text):
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


def has_workflows_section(index_text):
    return bool(re.search(r"^##+\s*Workflows\b", index_text, re.M | re.I))


def find_workflow_files(repo_root):
    d = os.path.join(repo_root, "process", "workflows")
    if not os.path.isdir(d):
        return []
    return sorted(f for f in os.listdir(d) if f.endswith(".md"))


def workflow_ownership(path, repo):
    """Does this workflow declare who owns its queue, and does that pointer resolve?

    Returns (system, external_ref, dangling) where `dangling` is True only when
    external_ref names a repo-relative path that does not exist.

    Deliberately does NOT look for checkbox characters. Through v2.0 it did, and that
    test was wrong in both directions: it blocked a repo-native backlog that is
    legitimately the single record of work, and it would pass a genuine shadow copy
    written without checkboxes. The hazard is a SECOND SOURCE OF TRUTH -- a queue some
    other system already owns -- so the thing to check is whether an owner is declared
    and whether the pointer resolves. (vocabulary.md v2.1)
    """
    try:
        with open(path) as fh:
            text = fh.read()
    except OSError:
        return None, None, False

    m_sys = re.search(r"^system:\s*(\S+)", text, re.M)
    m_ref = re.search(r"^external_ref:\s*(\S+)", text, re.M)
    system = m_sys.group(1).strip() if m_sys else None
    ref = m_ref.group(1).strip() if m_ref else None

    # `null`/`none` is an absent ref written out longhand, not a pointer.
    if ref and ref.lower() in ("null", "none", "~"):
        ref = None

    dangling = False
    if ref and not re.match(r"^[a-z][a-z0-9+.-]*://", ref):
        # Not a URL -- treat as a repo-relative path, which must actually exist.
        # A dangling path is a real failure: it points at nothing.
        dangling = not os.path.exists(os.path.join(repo, ref))

    return system, ref, dangling


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

    # 2. Does what it lists exist?
    listed = find_listed_files(index_text)
    missing = find_missing(listed, repo)
    for p in missing:
        problems.append(
            f"Index lists `{p}` but the file does not exist. Ingestion will route facts to "
            f"it and they will land in a vacuum. Remove the entry, or create the file.")

    # 3. Present but unlisted -- invisible to routing.
    #
    # Only PATH-REFERENCED singletons need a link. Discovery artifacts (the OST) are
    # ID-referenced by design: the index lists the tree as IDs + titles so an agent can
    # reference payments:OPP-0001 without loading the file. That IS progressive
    # disclosure -- demanding a link per artifact would invert it, and would mean re-editing
    # the index on every new opportunity.
    listed_set = set(listed)
    ost_ids = set(re.findall(
        r"\b(OUTCOME|OPP|SOL|ASSUMPTION|STORY|EPIC|TASK)-(\d{4})\b", index_text))

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
                # Workflows are declared in their own section; checked below.
                if rel.startswith(os.path.join("process", "workflows")):
                    continue

                # An ID'd discovery artifact is declared by its ID, not a link.
                m = re.search(
                    r"(outcome|opportunity|solution|assumption|story|epic|task)-(\d{4})",
                    os.path.basename(rel))
                if m:
                    prefix = {"outcome": "OUTCOME", "opportunity": "OPP", "solution": "SOL",
                              "assumption": "ASSUMPTION", "story": "STORY", "epic": "EPIC",
                              "task": "TASK"}
                    if (prefix[m.group(1)], m.group(2)) in ost_ids:
                        continue  # declared by ID in the index tree. Correct.
                    notes.append(
                        f"`{rel}` is a discovery artifact whose ID is not in the index's "
                        f"tree -- an agent cannot reference it.")
                    continue

                notes.append(
                    f"`{rel}` exists but is not listed in the index -- routing cannot see it.")

    # 4. The workflow. This is the one that decides whether a Todo can route.
    wf_files = find_workflow_files(repo)
    wf_declared = has_workflows_section(index_text)

    if not wf_files:
        # NOT blocking. A domain without a workflow is one where Todos cannot route -- a
        # real consequence, but not a broken domain. The Hub root has no team backlog by
        # design (Todos route to the domain that owns the work); a team may genuinely have
        # no tracker. "Blocked" must mean ingestion cannot run, not "this differs
        # from payments" -- otherwise the check nags every domain that is legitimately
        # different, and gets ignored.
        notes.append(
            "No workflow declared (`process/workflows/`). Knowledge and facts still route "
            "fine; **`Todo`s cannot** -- a Todo may only be `routed-to` a Workflow. If this "
            "team queues work somewhere (Jira, Linear), run setup-mesh job 2. If it doesn't "
            "-- e.g. this is the Hub root, where Todos route to the owning domain -- "
            "this is correct.")
    else:
        if not wf_declared:
            problems.append(
                f"Workflow file(s) exist ({', '.join(wf_files)}) but the index has no "
                f"Workflows section. Routing reads the index -- an undeclared workflow is "
                f"invisible, so Todos still cannot route.")
        for f in wf_files:
            full = os.path.join(repo, "process", "workflows", f)
            system, ref, dangling = workflow_ownership(full, repo)
            if not system and not ref:
                problems.append(
                    f"`process/workflows/{f}` declares no owning system: it has neither "
                    f"`system:` nor `external_ref:`. Nothing owns this queue, so a Todo "
                    f"routed here lands in a list that is a second source of truth for work "
                    f"tracked elsewhere. Name the system (`jira`, `linear`, or `repo`) and "
                    f"where it is.")
            elif dangling:
                problems.append(
                    f"`process/workflows/{f}` points at `{ref}`, which does not exist. A "
                    f"workflow is a pointer; one that resolves to nothing sends action items "
                    f"nowhere.")
            elif not ref:
                notes.append(
                    f"`process/workflows/{f}` names `system: {system}` but has no "
                    f"`external_ref`. Legal for a genuinely mesh-native process (a ritual "
                    f"that is only a description). For a queue, add where it actually is.")

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
        todos_ok = not any("No workflow declared" in n for n in notes)
        if todos_ok:
            print("READY. An index exists, what it lists is real, and a Todo has somewhere "
                  "to go.")
        else:
            print("READY for context -- but NOT for Todos. An index exists and what it lists "
                  "is real, so Knowledge and facts route fine. No workflow is declared, so "
                  "action items have nowhere to go (see notes).")
        print()
        print("Missing context files are NOT checked -- the file list is the manifest, and a")
        print("repo without a given file is a repo without that context, not a broken repo.")
        print("Ingestion reports those gaps honestly when it hits them.")


if __name__ == "__main__":
    sys.exit(main())
