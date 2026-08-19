#!/usr/bin/env python3
"""Survey the Hub and its domains: which are ready, which need a human, what's missing.

This is the triage half of setup. It runs `check_setup`'s logic over the Hub root and
every domain folder, and answers the only question that matters at onboarding scale:
*where does a human actually need to look?*

READ-ONLY. Writes nothing, ever. `scaffold_domain.py` does the writing, and only for
what this survey classifies as needing it.

**Domains are optional.** A Hub with cross-cutting context and no `domains/` at all is a
complete mesh, not a half-built one, and this survey must never report it as unfinished.
Whether domains exist is a per-engagement decision independent of repo topology -- a
multi-repo product will probably use them, a monorepo probably won't, and either may do
the opposite. Nothing here infers the deployment shape from the domain count.

Three states, and the middle one is the point:

  READY      an index exists and what it lists is real. Nothing to do.
  PARTIAL    ingestion can run, but something is degraded (an index listing nothing,
             a scaffold stub nobody filled in). A note, not a blocker.
  BLOCKED    ingestion cannot run or would misroute. Needs a human.

Usage:
    survey_mesh.py <hub-root>
    survey_mesh.py <hub-root> --json
    survey_mesh.py <hub-root> --manifest    # every tracked home, grouped by container

`--manifest` answers a different question from the triage above: not "where must a human
look?" but "what does this mesh claim to hold?" -- every file the indexes track, grouped
by the Hub root and each domain, so a person can read the list and spot what is missing,
misfiled, or wrong. Triage tells you what is broken; the manifest lets you check what is
RIGHT, which is not the same thing and cannot be derived from an exit code.

Exit codes: 0 = everything is READY or PARTIAL, 1 = at least one is BLOCKED,
2 = bad input. (`--manifest` reports and always exits 0 unless input is bad -- it is a
listing, not a verdict.)
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import check_setup  # noqa: E402  (deliberate: the survey is a layer over the checker)
import scaffold_domain  # noqa: E402  (for what it actually creates -- never a second copy)

INDEX = check_setup.INDEX
DOMAINS_DIR = scaffold_domain.DOMAINS_DIR


def scaffold_dirs(is_hub):
    """The containers scaffold_domain.py would create here. Imported, never restated.

    The survey used to keep its own hardcoded list, which drifted: it promised
    `process/workflows/` for every BLOCKED repo including the root, while the scaffold
    correctly created it only for domains (Minotaur finding 5). Reading the constants
    means the promise cannot disagree with the behaviour.
    """
    dirs = scaffold_domain.ROOT_DIRS if is_hub else scaffold_domain.DOMAIN_DIRS
    return [d.replace(os.sep, "/") + "/" for d in dirs]


def discover(hub_root):
    """Every domain folder in the Hub: the directories under `domains/`. Never deeper.

    There is no heuristic here, deliberately. Through v2.1 domains sat at the Hub root
    beside the cross-cutting folders, so this had to GUESS which top-level directories
    were domains -- it accepted anything containing a `product/`, `technical/`, or
    `process/` subdirectory. In the first third-party run that reported a `docs/product/`
    market-research folder as a BLOCKED domain and printed scaffold instructions for it,
    while the repo's actual product tree went undetected because it had no such subdir.
    The heuristic found the wrong one of the two.

    A domain is now a directory under `domains/`, and nothing else is one. That deletes
    the problem class rather than tuning it: no ignore list, no detection rule, nothing
    to misfire. (vocabulary v2.2)
    """
    root = os.path.join(hub_root, DOMAINS_DIR)
    if not os.path.isdir(root):
        return []
    return [os.path.join(root, name) for name in sorted(os.listdir(root))
            if not name.startswith(".") and os.path.isdir(os.path.join(root, name))]


def unreadable_context(hub_root):
    """Root-level directories holding a `context-index.md`, which routing cannot see.

    THIS DOES NOT DETECT DOMAINS, and must never be made to. A domain is a directory under
    `domains/` and nothing else is one -- that rule is what deleted a whole class of bug
    (the old heuristic accepted any top-level dir containing `product/`, `technical/` or
    `process/`, and in the first third-party run it reported a `docs/product/` research
    folder as a domain while missing the real one).

    What this reports is narrower and makes no claim about what the directory IS: it holds
    an index, it is not under `domains/`, therefore routing cannot see it. That is a fact
    about visibility, not a diagnosis. The human decides whether it is a domain that should
    move, or something else entirely that should be left alone.

    Keyed on `context-index.md` rather than on subdirectory shape deliberately: an index is
    something a person WROTE for this mesh, so its presence outside `domains/` is worth
    mentioning. A bare `docs/product/` folder is not evidence of anything and stays silent.
    """
    out = []
    for name in sorted(os.listdir(hub_root)):
        if name.startswith(".") or name == DOMAINS_DIR:
            continue
        d = os.path.join(hub_root, name)
        if os.path.isdir(d) and os.path.isfile(os.path.join(d, INDEX)):
            out.append(name)
    return out


def survey_one(repo, hub=False, hub_root=None):
    """Classify one domain (or the Hub root, with hub=True). Returns a dict; never writes."""
    problems, notes = [], []

    index_path = os.path.join(repo, INDEX)
    has_index = os.path.isfile(index_path)

    if not has_index:
        return {
            "repo": repo,
            "name": os.path.basename(os.path.abspath(repo)),
            "state": "BLOCKED",
            "is_hub": hub,
            "has_index": False,
            "problems": [f"No {INDEX} -- invisible to routing."],
            "notes": [],
            # Must match what scaffold_domain.py actually creates. It listed
            # `process/workflows/` here unconditionally -- hardcoded into the BLOCKED
            # branch, before anything knew whether this was the root -- while the scaffold
            # correctly created it only for domains. The survey promised a directory the
            # scaffold would not produce (Minotaur finding 5). The workflow layer is gone
            # as of v2.2, but the lesson stands: this list is a claim about another
            # script's behaviour, so it belongs next to that script's constants.
            "needs": [INDEX] + list(scaffold_dirs(hub)),
            "asks": ["index entries (what each file is about, and when to load it)"],
        }

    with open(index_path) as fh:
        index_text = fh.read()

    # Reuse the checker's rules rather than restating them -- one source of truth for
    # what "listed but missing" means.
    listed = check_setup.find_listed_files(index_text)
    # A domain's links up to the cross-cutting root stay inside the Hub, so they ARE
    # checkable; only links escaping the Hub entirely are skipped.
    # A listed-but-missing file is a PENDING HOME, not a break -- the row declares where a
    # kind of context goes, and promotion creates the file when it has content for it. This
    # was a `problem` (and so BLOCKED the domain) until 2026-08-06; it is a note now, and the
    # checker's wording is the single source of truth for how it reads.
    missing = check_setup.find_missing(listed, repo, root=hub_root or repo)
    if missing:
        notes.append(f"{len(missing)} pending home(s) -- listed in the index, not yet "
                     f"written: {', '.join('`' + p + '`' for p in missing)}. Promotion "
                     f"creates them. Check none is a typo.")

    # Collections, on the SAME terms the checker uses. Omitting them here was fail-open #14:
    # this module imports check_setup precisely so the two cannot drift, then called
    # `find_listed_files`/`find_missing` and neither collection function -- so a mesh whose
    # only breakage was a collection row pointing at a nonexistent directory got BLOCKED from
    # check_setup and READY from the survey. That is this project's canary (fail-open #9): two
    # validators disagreeing about one directory. Verified by running both against an index
    # whose collection target does not exist.
    #
    # The split is the checker's, not restated: MISSING is a problem, EMPTY is a note.
    collections = check_setup.find_listed_collections(index_text)
    missing_dirs, empty_dirs = check_setup.check_collections(
        collections, repo, root=hub_root or repo)
    for p in missing_dirs:
        problems.append(f"Index declares the collection `{p}` but no such directory exists.")
    for p in empty_dirs:
        notes.append(f"Collection `{p}` is declared but holds no .md members yet -- a "
                     f"pending home for a whole kind of context, not an error.")

    # Two different kinds of missing thing, and conflating them is what makes a survey
    # useless at scale:
    #   needs      -- CONTAINERS. scaffold_domain.py creates them unattended.
    #   asks       -- CLAIMS. Only the team knows the answer; a script cannot invent it.
    needs, asks = [], []

    # Containers scaffolding would create. Absent ones are not problems -- they are
    # exactly what `scaffold_domain.py` fixes without a human.
    dirs = scaffold_domain.ROOT_DIRS if hub else scaffold_domain.DOMAIN_DIRS
    for d in dirs:
        if not os.path.isdir(os.path.join(repo, d)):
            needs.append(d.replace(os.sep, "/") + "/")

    # A scaffolded-but-unfilled index: the container exists and the claims don't. This
    # is the state scaffolding deliberately leaves behind, and the survey is how a human
    # finds it again -- otherwise an empty index looks "set up" forever.
    #
    # BOTH conditions are required, and the marker alone was the bug this replaces:
    # `SCAFFOLD:` lives inside the template's HTML guidance comments, which are meant to
    # STAY (they carry the markdown-link rule). So the marker is present whether or not
    # anyone filled the index in, and a fully populated index was reported as an empty stub
    # FOREVER, with nothing the team could do to clear it short of deleting the guidance.
    # Meanwhile check_setup read the same file, counted the links, and said READY -- two
    # validators contradicting each other about one directory, which is this project's
    # canary. Fail-CLOSED, not fail-open -- the inverse shape, and NOT one of the eleven.
    # It survived because every hunt so far looked for validators reporting success while
    # checking nothing; this one reported failure while checking the wrong thing. Worth
    # sweeping for deliberately: a check no amount of correct work can clear.
    #
    # Do NOT strip comments before the marker check, tempting as the symmetry is:
    # check_setup strips them for the vocabulary line and the link scan (fail-open #10),
    # but this marker appears ONLY inside comments, by design. Stripping them makes the
    # condition permanently false and this branch dead code -- a worse bug than the one
    # being fixed, and one that looks like a principled consistency fix. Verified by
    # running it: a pristine scaffold fell through to the `elif`.
    #
    # `listed` is what does the discriminating, and it is links, not table rows: how many
    # distinct local paths the index points at. A table row without a markdown link is
    # invisible here, deliberately (fail-open #9).
    #
    # `listed` alone is NOT the discriminator: a collection row is a real context home, so an
    # index declaring only collections lists something and must not be called empty. Both
    # branches test files-or-collections for that reason (part of fail-open #14 -- the same
    # omission, in its fail-CLOSED direction: reporting "routing can see nothing here" about
    # an index routing can read perfectly well).
    routable = listed or collections
    if "SCAFFOLD:" in index_text and not routable:
        asks.append("index entries (what each file is about, and when to load it)")
        notes.append("Index is a scaffold stub -- it lists nothing, so routing can see "
                     "nothing here. Honest, but empty until someone fills it in.")
    elif not routable:
        notes.append("Index lists no context files or collections -- routing can see "
                     "nothing here.")

    if problems:
        state = "BLOCKED"
    elif needs or asks or notes:
        state = "PARTIAL"
    else:
        state = "READY"

    return {
        "repo": repo,
        "name": os.path.basename(os.path.abspath(repo)),
        "state": state,
        "is_hub": hub,
        "has_index": True,
        "problems": problems,
        "notes": notes,
        "needs": needs,
        "asks": asks,
    }


def manifest(hub_root):
    """Every file the indexes track, grouped by container. Read-only.

    Reuses `check_setup.find_listed_files` rather than re-deriving what "tracked" means --
    routing reads markdown links and only those, so a manifest built on a looser rule would
    show files routing cannot actually see, which is the opposite of useful.

    Each entry carries whether the file EXISTS, because the two failure modes look identical
    in an index and are not: a tracked file that is missing is a broken promise, and an
    untracked file that exists is invisible to routing.
    """
    # ONE INDEX, at the Hub root (v0.17.0). A domain's files are declared there with
    # `domains/<name>/...` paths, so there is nothing per-domain to read. Iterating domains
    # here would report every one of them as `no_index`, which is now the normal state.
    groups = []
    containers = [("(hub root)", hub_root, True)]

    for label, path, _is_hub in containers:
        index_path = os.path.join(path, INDEX)
        if not os.path.isfile(index_path):
            groups.append({"label": label, "no_index": True, "tracked": [], "untracked": []})
            continue

        with open(index_path) as fh:
            text = fh.read()

        tracked = []
        for rel in check_setup.find_listed_files(text):
            # A link climbing out of the Hub is documentation elsewhere, not mesh content.
            if check_setup.escapes_root(path, rel, hub_root):
                continue
            tracked.append({"path": rel,
                            "exists": os.path.isfile(os.path.join(path, rel))})

        # Collections are tracked homes too, listed as the folder they are -- one entry per
        # row, never one per member, which is the entire point of a collection row.
        collections = [c for c in check_setup.find_listed_collections(text)
                       if not check_setup.escapes_root(path, c, hub_root)]
        for rel in collections:
            tracked.append({"path": rel, "collection": True,
                            "exists": os.path.isdir(os.path.join(path, rel))})

        # Present-but-unlisted: exists on disk, invisible to routing. Same walk the checker
        # does, kept to the three canonical subtrees.
        #
        # A discovery artifact is NOT unlisted when the index names its ID. The OST is
        # ID-referenced by design -- the index carries the tree as IDs + titles so an agent
        # can reference `payments:OPP-0001` without loading the file. Demanding a link per
        # artifact would invert progressive disclosure and mean re-editing the index on
        # every new opportunity. Reporting these as "add an index row" would advise exactly
        # that, so the checker's ID rule is reused here rather than re-derived.
        listed = {t["path"] for t in tracked}
        ost_ids = set(re.findall(
            r"\b(OUTCOME|OPP|SOL|ASSUMPTION|STORY|EPIC)-(\d{4})\b", text))
        prefix = {"outcome": "OUTCOME", "opportunity": "OPP", "solution": "SOL",
                  "assumption": "ASSUMPTION", "story": "STORY", "epic": "EPIC"}

        # A COLLECTION MEMBER is not untracked -- its folder's row covers it. Without this,
        # a correctly declared collection reports every member as "invisible to routing" and
        # advises adding the per-file rows collections exist to remove. It was masked in
        # test-mesh only because that index happens to link each persona individually as
        # well; a plain ADR folder would have shown every member as untracked.
        collection_dirs = [os.path.normpath(c) for c in collections]

        def in_collection(rel):
            parent = os.path.dirname(os.path.normpath(rel))
            return any(parent == c or parent.startswith(c + os.sep)
                       for c in collection_dirs)

        untracked = []
        for sub in ("technical", "product", "process"):
            d = os.path.join(path, sub)
            if not os.path.isdir(d):
                continue
            for root, _, files in os.walk(d):
                for f in sorted(files):
                    if not f.endswith(".md"):
                        continue
                    rel = os.path.relpath(os.path.join(root, f), path)
                    if rel in listed or in_collection(rel):
                        continue
                    m = re.search(
                        r"(outcome|opportunity|solution|assumption|story|epic)-(\d{4})",
                        os.path.basename(rel))
                    if m and (prefix[m.group(1)], m.group(2)) in ost_ids:
                        continue  # declared by ID in the index tree. Correct.
                    untracked.append(rel)

        groups.append({"label": label, "no_index": False,
                       "tracked": sorted(tracked, key=lambda t: t["path"]),
                       "untracked": sorted(untracked)})
    return groups


def report_manifest(groups):
    total = sum(len(g["tracked"]) for g in groups)
    n_coll = sum(1 for g in groups for t in g["tracked"] if t.get("collection"))
    # Say "homes", not "files": a collection row is one tracked home covering many files, so
    # calling the total a file count would misdescribe it. Same rule as the checker's verdict
    # -- a count must not claim more than it counted.
    print(f"Mesh manifest: {total} tracked home(s) across {len(groups)} container(s)"
          + (f", {n_coll} of them collection(s)" if n_coll else ""))
    print()
    print("Read this to check what the mesh CLAIMS to hold against what you expect it to.")
    print("Routing can see the tracked files and nothing else.")
    print()

    for g in groups:
        if g["no_index"]:
            print(f"{g['label']} — no {INDEX}; routing cannot see this container at all")
            print()
            continue

        print(f"{g['label']} — {len(g['tracked'])} tracked")
        if not g["tracked"]:
            print("    (nothing tracked — the index lists no context files or collections)")
        for t in g["tracked"]:
            # "pending", not "MISSING": the row is a declared home that nobody has written
            # yet, which is a normal state promotion resolves -- not a broken link.
            # A collection is marked, because "ok" against a folder means the DIRECTORY is
            # there and says nothing about its members -- a distinction an unmarked row would
            # hide behind identical output.
            mark = "  [collection]" if t.get("collection") else ""
            print(f"    {'ok     ' if t['exists'] else 'pending'} {t['path']}{mark}")
        for u in g["untracked"]:
            print(f"    unlisted {u}")
        print()

    missing = [(g["label"], t["path"])
               for g in groups for t in g["tracked"] if not t["exists"]]
    unlisted = [(g["label"], u) for g in groups for u in g["untracked"]]

    if missing:
        # A declared home nobody has written yet -- normal, and promotion resolves it. The
        # only reason to surface it is that a TYPO'd path has the identical shape and
        # nothing downstream will catch one, so the list is the human's chance to look.
        print(f"pending ({len(missing)}) — declared in an index, not yet written. Promotion")
        print("  creates the file when it has content for it, patterned on its siblings, and")
        print("  updates the index row in the same PR. Read the paths: a typo looks the same.")
        print()
    if unlisted:
        print(f"unlisted ({len(unlisted)}) — on disk but not tracked. Routing cannot see")
        print("  these; add an index row if they should receive facts.")
        print()
    if not missing and not unlisted:
        # "Every tracked file exists" is VACUOUSLY TRUE OF ZERO TRACKED FILES -- the same
        # shape as the empty-index and zero-domain fail-opens. A manifest listing nothing
        # is the normal state of a fresh scaffold, so it is not an error; but it must not
        # be reported in words that sound like a clean bill of health.
        if total:
            # "home(s)", not "file(s)": for a collection this line means the DIRECTORY is
            # there. It says nothing about whether any member exists -- an empty collection
            # is a note the survey raises, not something this verdict has checked.
            print(f"All {total} tracked home(s) exist, every context file is tracked, and")
            print("nothing is pending.")
        else:
            print("NOTHING IS TRACKED anywhere in this mesh, so there is nothing to check.")
            print("Routing reads the indexes and only the indexes: until one lists a file,")
            print("ingestion will report every fact as having no home. Expected for a fresh")
            print("scaffold -- fill the indexes in before ingesting.")


def main():
    argv = sys.argv[1:]
    as_json = "--json" in argv
    as_manifest = "--manifest" in argv
    args = [a for a in argv if not a.startswith("--")]

    if len(args) != 1:
        print(__doc__)
        return 2

    hub_root = args[0]
    if not os.path.isdir(hub_root):
        print(f"error: not a directory: {hub_root}", file=sys.stderr)
        return 2

    if as_manifest:
        groups = manifest(hub_root)
        if as_json:
            print(json.dumps(groups, indent=2))
        else:
            report_manifest(groups)
        # A listing, not a verdict -- it reports missing files rather than ruling on them,
        # and the triage run above is what decides whether ingestion can proceed.
        return 0

    # The root is surveyed, and it is the ONLY container (v0.17.0). Domains do not hold an
    # index or a staging tree, so surveying one would ask a question it cannot answer and
    # report BLOCKED for every domain in a correctly built mesh -- a fail-CLOSED bug, the
    # family this codebase has twice.
    results = [survey_one(hub_root, hub=True, hub_root=hub_root)]
    blocked = [r for r in results if r["state"] == "BLOCKED"]

    unreadable = unreadable_context(hub_root)

    if as_json:
        print(json.dumps(
            {"repos": results, "unreadable_context": unreadable}, indent=2))
        return 1 if blocked else 0

    report(results, unreadable,
           domain_names=[os.path.basename(d) for d in discover(hub_root)])
    return 1 if blocked else 0


def report(results, unreadable=(), domain_names=()):
    ready = [r for r in results if r["state"] == "READY"]
    partial = [r for r in results if r["state"] == "PARTIAL"]
    blocked = [r for r in results if r["state"] == "BLOCKED"]

    # Counted from the FILESYSTEM, not from `results`. Domains are no longer surveyed as
    # containers (v0.17.0), so deriving this from the result list reported "0 domain(s)" for a
    # mesh that plainly had two. They still exist and are still worth naming; they are simply
    # not things that hold an index.
    domains = list(domain_names)

    print(f"Mesh survey: Hub root + {len(domains)} domain(s)")
    print()

    # Zero domains gets NO paragraph here. The header count line above says it, and a mesh
    # with cross-cutting context only is a complete, valid mesh -- domains are optional
    # (v2.5). This used to print "NO DOMAINS YET" plus instructions for adding one, which
    # told a correctly-configured Hub it was unfinished. Silence is what "this is normal"
    # looks like. The `unreadable` block below still fires for someone who DOES have
    # domains, in the wrong place.

    if unreadable:
        # Deliberately NOT phrased as "these are domains". This says only what was checked:
        # a directory holding an index, outside `domains/`, therefore invisible to routing.
        # Naming it a domain would resurrect the detection heuristic v2.2 deleted.
        print(f"  CONTEXT ROUTING CANNOT SEE ({len(unreadable)}):")
        print()
        for name in unreadable:
            print(f"      {name}/ holds a {INDEX} but is not under {DOMAINS_DIR}/.")
        print()
        print(f"  Routing reads the Hub root and {DOMAINS_DIR}/*, so nothing above is")
        print("  visible to it. This is NOT a claim that these are domains -- only that")
        print("  someone wrote an index there. If one IS a domain, move it to")
        print(f"  {DOMAINS_DIR}/<name>/ (meshes built before v2.2 put domains at the root).")
        print("  If it is not, ignore this. Nothing here is moved for you.")
        print()

    for label, group in (("BLOCKED", blocked), ("PARTIAL", partial), ("READY", ready)):
        if not group:
            continue
        print(f"{label} ({len(group)}):")
        print()
        for r in group:
            label = "(hub root)" if r["is_hub"] else r["name"]
            print(f"  {label}")
            for p in r["problems"]:
                print(f"      ! {p}")
            for n in r["notes"]:
                print(f"      - {n}")
            if r["needs"]:
                print(f"      -> scaffold creates: {', '.join(r['needs'])}")
            for a in r.get("asks", []):
                print(f"      ?  needs a human: {a}")
        print()

    scaffoldable = [r for r in results if r["needs"]]
    human = [r for r in results if r.get("asks")]

    print("What happens next:")
    print()
    if scaffoldable:
        names = ", ".join("(hub root)" if r["is_hub"] else r["name"] for r in scaffoldable)
        print(f"  SCAFFOLD (unattended) -- {names}")
        print("    scaffold_domain.py creates the missing containers: directories and an")
        print("    empty index. It never authors a context file or an index row.")
        print()
    if human:
        names = ", ".join("(hub root)" if r["is_hub"] else r["name"] for r in human)
        print(f"  NEEDS A HUMAN -- {names}")
        print("    What a file is about and when to load it are claims about the team.")
        print("    A script that guessed them would be believed.")
        print()
    if not scaffoldable and not human:
        # The verdict must not claim more than was checked. "The Hub and every domain are
        # ready" is VACUOUSLY TRUE OF ZERO DOMAINS -- and a mesh whose domains sit at the
        # root (the pre-v2.2 layout) has exactly zero as far as this survey is concerned,
        # so a fully populated mesh printed this line and exited 0. That is the same shape
        # as the empty-index fail-open: a script parsing nothing and reporting success.
        #
        # That risk is real, but zero domains is NOT the thing that signals it: domains are
        # optional, so a root-only mesh is complete and gets a plain verdict (v2.5). What
        # actually discriminates the two is `unreadable` -- an index sitting outside
        # `domains/`, which is exactly what a pre-v2.2 mesh looks like from here, and which
        # the block above has already reported in full. So key the caveat on that, not on
        # the count. A silent zero-domain mesh and a silent zero-domain fail-open differ by
        # whether anything unreadable was found, and nothing else.
        if domains:
            print(f"  Nothing. The Hub root and all {len(domains)} domain(s) are ready.")
        else:
            print("  Nothing. The Hub root is ready, and holds cross-cutting context only.")
        if unreadable:
            print()
            print("  Read the note above before trusting that: context exists in this repo")
            print("  that routing cannot see, so what is READY may not be what you meant.")


if __name__ == "__main__":
    sys.exit(main())
