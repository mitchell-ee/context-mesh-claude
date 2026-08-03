#!/usr/bin/env python3
"""Survey the Hub and its domains: which are ready, which need a human, what's missing.

This is the triage half of setup. It runs `check_setup`'s logic over the Hub root and
every domain folder, and answers the only question that matters at onboarding scale:
*where does a human actually need to look?*

READ-ONLY. Writes nothing, ever. `scaffold_domain.py` does the writing, and only for
what this survey classifies as needing it.

Three states, and the middle one is the point:

  READY      an index exists and what it lists is real. Nothing to do.
  PARTIAL    ingestion can run, but something is degraded (an index listing nothing,
             a scaffold stub nobody filled in). A note, not a blocker.
  BLOCKED    ingestion cannot run or would misroute. Needs a human.

Usage:
    survey_mesh.py <hub-root>
    survey_mesh.py <hub-root> --json

Exit codes: 0 = everything is READY or PARTIAL, 1 = at least one is BLOCKED,
2 = bad input.
"""

import json
import os
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
    missing = check_setup.find_missing(listed, repo, root=hub_root or repo)
    for p in missing:
        problems.append(f"Index lists `{p}` but it does not exist -- facts would route "
                        f"into a vacuum.")

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
    if "SCAFFOLD:" in index_text:
        asks.append("index entries (what each file is about, and when to load it)")
        notes.append("Index is a scaffold stub -- it lists nothing, so routing can see "
                     "nothing here. Honest, but empty until someone fills it in.")
    elif not listed:
        notes.append("Index lists no context files -- routing can see nothing here.")

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


def main():
    argv = sys.argv[1:]
    as_json = "--json" in argv
    args = [a for a in argv if not a.startswith("--")]

    if len(args) != 1:
        print(__doc__)
        return 2

    hub_root = args[0]
    if not os.path.isdir(hub_root):
        print(f"error: not a directory: {hub_root}", file=sys.stderr)
        return 2

    # The root is always surveyed, and always first -- it is the one thing that must exist.
    results = [survey_one(hub_root, hub=True, hub_root=hub_root)]
    results += [survey_one(d, hub_root=hub_root) for d in discover(hub_root)]
    blocked = [r for r in results if r["state"] == "BLOCKED"]

    if as_json:
        print(json.dumps(results, indent=2))
        return 1 if blocked else 0

    report(results)
    return 1 if blocked else 0


def report(results):
    ready = [r for r in results if r["state"] == "READY"]
    partial = [r for r in results if r["state"] == "PARTIAL"]
    blocked = [r for r in results if r["state"] == "BLOCKED"]

    domains = [r for r in results if not r["is_hub"]]

    print(f"Mesh survey: Hub root + {len(domains)} domain(s)")
    print()

    if not domains:
        print("  NO DOMAINS YET. The Hub holds only cross-cutting context so far. Add one")
        print("  per thing you want context about: scaffold_domain.py <hub> <domain>,")
        print(f"  which creates {DOMAINS_DIR}/<domain>/.")
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
        print("  Nothing. The Hub and every domain are ready.")


if __name__ == "__main__":
    sys.exit(main())
