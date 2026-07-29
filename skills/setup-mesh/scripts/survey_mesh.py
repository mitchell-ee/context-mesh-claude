#!/usr/bin/env python3
"""Survey the Hub and its domains: which are ready, which need a human, what's missing.

This is the triage half of setup. It runs `check_setup`'s logic over the Hub root and
every domain folder, and answers the only question that matters at onboarding scale:
*where does a human actually need to look?*

READ-ONLY. Writes nothing, ever. `scaffold_domain.py` does the writing, and only for
what this survey classifies as needing it.

Three states, and the middle one is the point:

  READY      an index exists, what it lists is real, a Todo can route. Nothing to do.
  PARTIAL    ingestion can run, but something is degraded (usually: no workflow, so
             Todos can't route). A note, not a blocker.
  BLOCKED    ingestion cannot run or would misroute. Needs a human.

The Hub ROOT is surveyed like a domain, with one difference: having no workflow is
CORRECT there (Todos route to the domain that owns the work), so it is not counted
against it.

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

INDEX = check_setup.INDEX


def looks_like_domain(path):
    """A directory we should survey rather than skip.

    Deliberately loose: a domain with an index is obviously one, but a domain WITHOUT an
    index is exactly the case the survey exists to report. So we also accept anything
    holding the usual context dirs.
    """
    if not os.path.isdir(path):
        return False
    if os.path.isfile(os.path.join(path, INDEX)):
        return True
    return any(os.path.isdir(os.path.join(path, d))
               for d in ("technical", "product", "process"))


def discover(hub_root):
    """Every domain folder in the Hub. One level down, never deeper -- domains do not nest.

    This used to have to guess a mesh layout (`hub/` beside `repos/<name>/`, or flat) and
    identify which repo was the control plane by reading its index. With one repo the
    answer is structural: the root is the root, and its subdirectories are the domains.
    """
    found = []
    for name in sorted(os.listdir(hub_root)):
        if name.startswith("."):
            continue
        p = os.path.join(hub_root, name)
        if looks_like_domain(p):
            found.append(p)
    return found


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
            "needs": [INDEX, "staging/candidates/", "process/workflows/"],
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

    wf_files = check_setup.find_workflow_files(repo)
    wf_declared = check_setup.has_workflows_section(index_text)

    # Two different kinds of missing thing, and conflating them is what makes a survey
    # useless at scale:
    #   needs      -- CONTAINERS. scaffold_domain.py creates them unattended.
    #   asks       -- CLAIMS. Only the team knows the answer; a script cannot invent it.
    needs, asks = [], []

    if not wf_files:
        if hub:
            notes.append("No workflow -- correct at the Hub root; Todos route to the "
                         "domain that owns the work.")
        else:
            notes.append("No workflow declared -- Knowledge and facts route fine, "
                         "**Todos cannot**.")
            # NOT scaffoldable. A workflow file needs `system` + `external_ref` pointing
            # at the real tracker -- a fact about the team, not a container. Scaffolding
            # an empty one would create exactly the smell check_setup warns about: a
            # workflow with no external system, i.e. the mesh becoming the tracker.
            asks.append("where this team queues work (Jira/Linear/...)")
    else:
        if not wf_declared:
            problems.append("Workflow file(s) exist but the index has no Workflows section "
                            "-- routing cannot see them, so Todos still cannot route.")
        for f in wf_files:
            full = os.path.join(repo, "process", "workflows", f)
            has_ref, has_list = check_setup.workflow_is_pointer(full)
            if not has_ref:
                notes.append(f"`process/workflows/{f}` has no `external_ref` -- legal, "
                             f"but the mesh is about to become a tracker.")
            if has_list:
                problems.append(f"`process/workflows/{f}` contains a checkbox list -- "
                                f"a workflow is a pointer, not a container.")

    # Containers scaffolding would create. Absent ones are not problems -- they are
    # exactly what `scaffold_domain.py` fixes without a human.
    if not os.path.isdir(os.path.join(repo, "staging", "candidates")):
        needs.append("staging/candidates/")
    if not hub and not os.path.isdir(os.path.join(repo, "process", "workflows")):
        needs.append("process/workflows/")

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
        print("  per thing you want context about: scaffold_domain.py <hub> <domain>.")
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
        print("    What a file is about, when to load it, and where work gets queued are")
        print("    claims about the team. A script that guessed them would be believed.")
        print()
    if not scaffoldable and not human:
        print("  Nothing. The Hub and every domain are ready.")


if __name__ == "__main__":
    sys.exit(main())
