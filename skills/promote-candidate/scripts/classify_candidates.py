#!/usr/bin/env python3
"""Classify staging candidates by what promotion actually means for each, batched by target.

Promotion is not one verb. Candidates need SIX different outcomes -- and only two of them
write anything into canonical context:

  MERGE       the claim lands in a section of an existing context file
  APPEND      the target is a collection; create a NEW member file in it
  CONTRADICTS the target says the opposite; a human decides which one moves. NEVER auto-apply
  RESOLVE     an OpenQuestion does not promote -- it resolves into another type first
  NO-HOME     target_path is null; nothing to promote into until the manifest grows a file
  NEVER       provenance roots (Conversation) stay in staging forever, by definition

(This docstring has been wrong twice: it said "four" while classify() returned five, and
SKILL.md said "six" over that same five. COUNT AGAINST classify() -- it is the only one of
the three that decides anything. The count is six because APPEND was added, not because the
old "six" was right.)

A sixth verb, HANDOVER, existed through v2.1: the target was a Workflow, so the item belonged
in Jira/Linear and the mesh handed it over rather than filing it. The workflow layer is
deferred as of v2.2: the mesh holds context, and a queue is the work itself.

Candidates ingestion linked as duplicates are grouped, not re-judged: a `duplicate_of`
pointing at another candidate means an earlier ingestion already made this claim, and dedup
declined to resolve it because ingestion only ever adds. Promotion is where a human sees both
at once, so the link is surfaced with the batch rather than left for them to re-derive.

Batched by target file: three candidates landing in one document are one edit, reviewed
whole, not three sequential passes that conflict with each other.

Usage:
    classify_candidates.py <hub-root>
    classify_candidates.py <hub-root> --json
    classify_candidates.py <hub-root> --mesh     # accepted, no-op (see below)

`--mesh` meant "walk the root plus every domain's staging" when a domain had its own staging
tree. Staging is centralized as of v0.17.0, so every run reads the one tree and the flag does
nothing. It is still accepted so existing invocations do not break.

Exit codes: 0 = classified, 1 = a staging dir exists but could not be read, 2 = bad input.
"""

import json
import os
import re
import sys

# One definition of where staging lives -- see staging_config.py. This walk and the one in
# collect_dedup_targets.py must agree about where candidates live or a claim becomes invisible
# to one of them, which is precisely why both import the same module rather than restating it.
_SETUP_SCRIPTS = os.path.join(
    os.environ.get("CLAUDE_PLUGIN_ROOT",
                   os.path.dirname(os.path.dirname(os.path.dirname(
                       os.path.dirname(os.path.abspath(__file__)))))),
    "skills", "setup-mesh", "scripts")
sys.path.insert(0, _SETUP_SCRIPTS)
import staging_config  # noqa: E402

FM = re.compile(r"^---\s*\n(.*?)\n---", re.S)


def parse_frontmatter(text):
    """Minimal YAML-ish reader: flat scalars plus the `edges:` list-of-dicts we emit."""
    m = FM.search(text)
    if not m:
        return {}
    out, edges, cur = {}, [], None
    for line in m.group(1).splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        if re.match(r"^\s*-\s*edge:", line):
            if cur:
                edges.append(cur)
            cur = {"edge": line.split("edge:", 1)[1].strip()}
            continue
        if re.match(r"^\s+target:", line) and cur is not None:
            cur["target"] = line.split("target:", 1)[1].strip()
            continue
        m2 = re.match(r"^([a-z_-]+):\s*(.*)$", line)
        if m2:
            if cur:
                edges.append(cur); cur = None
            k, v = m2.group(1), m2.group(2).strip()
            if k == "edges":
                continue
            out[k] = v
    if cur:
        edges.append(cur)
    out["_edges"] = edges
    return out


def classify(fm, body):
    """Return (verdict, why). Order matters: the disqualifying cases come first."""
    ntype = fm.get("type", "")
    target = fm.get("target", "")
    edges = fm.get("_edges", [])

    if ntype == "Conversation":
        return "NEVER", ("Provenance root. Every ingested fact hangs off it via derives-from; "
                         "it stays in staging permanently, by definition (vocabulary.md).")

    # Type before target: an OpenQuestion has no promotion path at all, whatever it targets.
    # It is not undecided about WHERE it goes -- it is undecided FULL STOP. Promotion moves
    # a settled fact; there is no fact here yet.
    if ntype == "OpenQuestion":
        return "RESOLVE", ("An OpenQuestion does not promote -- it RESOLVES into another type "
                           "(vocabulary.md: 'resolves into one of the above'). It needs a "
                           "human decision, not a routing confirmation. Run the "
                           "guided-resolution flow (see the RESOLVE section of SKILL.md): "
                           "surface the "
                           "question with the context that raised it, offer the options and "
                           "what each would route to, and on a decision convert it to a "
                           "decided node. Only then is there anything to promote.")

    if target in ("null", "", None):
        return "NO-HOME", ("target_path is null -- this mesh has no file for it. Nothing to "
                           "promote into. Fix the manifest (add the file to an index) first, "
                           "then re-route. The gap is the finding.")

    if any(e.get("edge") == "contradicts" for e in edges):
        return "CONTRADICTS", ("The target file says the opposite. A human decides which one "
                               "moves -- the doc or the world it describes. NEVER auto-apply: "
                               "a contradicts edge is never auto-resolved (vocabulary.md).")

    if staging_config.is_staging_path(target):
        return "NO-HOME", ("Target is inside staging -- that is output, not canonical context. "
                           "This candidate has no canonical destination.")

    # A trailing slash means the target is a COLLECTION -- a folder of same-typed files where
    # nothing traverses a member. That is a different act from MERGE: MERGE edits prose inside
    # an existing document, APPEND generates a filename and creates a new one. Folding it into
    # MERGE would make the summary lie about what promotion is going to do.
    if target.endswith("/"):
        return "APPEND", ("The target is a collection -- a folder of same-typed files. This "
                          "does not edit an existing document: it CREATES a new member, named "
                          "from the collection's declared pattern in the index. The row must "
                          "already exist (promotion never creates a collection and its "
                          "justifying row in one motion). Ordinal patterns number by reading "
                          "the directory, so run promotion single-threaded.")

    # A candidate whose target is a collection MEMBER (`.../personas/first-time-buyer.md`)
    # falls through to MERGE below, and needs no branch of its own: by the time it is here,
    # ingestion's stage 3.4 has already chosen the member, and the target is an ordinary file
    # path that MERGE handles like any other.
    #
    # A member that has since been renamed or deleted needs no branch either, and a check for
    # it was written and then REMOVED. It cannot distinguish a vanished member from a pending
    # home -- both are "a target whose file is absent but whose directory exists" -- so it
    # would have downgraded every pending home, which is the fail-CLOSED shape v2.5 found
    # (reporting broken when it isn't). Promotion already does the right thing: step 0 of the
    # merge flow creates a missing target, and for a collection member that is exactly the
    # APPEND outcome under a name the human already approved at the checkpoint.

    return "MERGE", "The claim lands in a section of the target file."


def domain_of_target(target):
    """The domain a target path belongs to, or `(cross-cutting)` for a Hub-root path.

    `domains/payments/technical/x.md` -> `payments`. Anything not under `domains/` is
    cross-cutting context at the Hub root, which is a real answer and not a missing one.

    Presentational only -- it groups the promotion plan for a human reader. Nothing routes or
    decides on it.
    """
    segs = [s for s in str(target).replace(os.sep, "/").split("/") if s]
    if len(segs) >= 2 and segs[0] == "domains":
        return segs[1]
    return "(cross-cutting)"


def find_staging_dirs(root):
    """Every `<staging>/candidates/` in the Hub -- the root one plus one per domain.

    Ingestion writes each candidate into the domain that owns the fact, and cross-cutting
    facts into the root staging dir, so `--mesh` finds them rather than assuming one location.

    Delegates to the same function the dedup collector calls. These were two hand-written
    walks kept identical by a comment; the pool promotion offers must equal the pool dedup
    compared against, so they are now one function and cannot drift.

    Returns (found, unreadable) -- an existing-but-unreadable staging dir is reported rather
    than silently dropped.
    """
    return staging_config.find_candidates_dirs(root)


def collect(cand_dir, rows):
    """Read the Hub's candidates into `rows`.

    Took a `domain_label` until v0.17.0, derived from which staging dir the candidate sat in.
    With one staging tree that label was the same for every candidate; the domain now comes
    from each candidate's target path instead (`domain_of_target`).
    """
    for f in sorted(os.listdir(cand_dir)):
        if not f.endswith(".md") or f.endswith("-transcript.md"):
            continue
        path = os.path.join(cand_dir, f)
        with open(path) as fh:
            text = fh.read()
        fm = parse_frontmatter(text)
        if not fm:
            continue
        # Anything not still in staging has already been promoted -- `canonical`, i.e.
        # merged into a context file. Re-offering one means merging the same claim twice,
        # which is exactly the accretion dedup exists to prevent. Skip on "not staging"
        # rather than listing the done states: a state added later should default to safe.
        # (That defaulting is why a pre-v2.2 `resolved` candidate is still skipped
        # correctly, rather than being re-offered once the state left the vocabulary.)
        state = fm.get("state", "staging")
        if state != "staging":
            continue
        verdict, why = classify(fm, text)
        rows.append({
            "id": fm.get("id", f[:-3]),
            "file": f,
            # Read from the TARGET PATH, not from which staging dir the candidate sat in.
            # With staging centralized (v0.17.0) every candidate comes from the same folder,
            # so the old source-derived label said "(root)" for all of them. The target is
            # where the domain actually shows: `domains/payments/technical/x.md` -> payments.
            "domain": domain_of_target(fm.get("target", "")),
            "type": fm.get("type", "?"),
            "tag": fm.get("tag", ""),
            "target": fm.get("target", ""),
            "duplicate_of": fm.get("duplicate_of", ""),
            "verdict": verdict,
            "why": why,
        })


def main():
    argv = sys.argv[1:]
    args = [a for a in argv if not a.startswith("--")]
    as_json = "--json" in argv
    # `--mesh` is accepted and ignored (v0.17.0). It used to mean "walk every domain's
    # staging"; there is one staging tree now, so every run is what --mesh used to be. Kept as
    # a silent no-op rather than an error so existing invocations and docs do not break.

    if len(args) != 1:
        print(__doc__)
        return 2

    hub = args[0]
    rows = []

    # Resolve where staging lives for THIS Hub before looking for it: env var, then
    # `<hub>/.context-mesh`, then the default. The pool promotion offers must equal the pool
    # dedup compared against, so both scripts resolve it the same way, from the same module.
    staging_config.configure(hub)

    # ONE staging tree (v0.17.0), so there is one path here rather than two. `--mesh` used to
    # select "walk every domain's staging" and is now a no-op, accepted so existing scripts,
    # docs, and muscle memory keep working rather than erroring on an unknown flag.
    cand_dirs, unreadable = find_staging_dirs(hub)

    # An existing staging dir that cannot be read is an error, not an empty one. Reported
    # before the not-found branch, because it must never be mistaken for "nothing here".
    if unreadable:
        print("error: staging director(ies) exist but could not be read:", file=sys.stderr)
        for path, err in unreadable:
            print(f"  {path}  ({err})", file=sys.stderr)
        print("  Their candidates would be silently missing from this plan.", file=sys.stderr)
        return 1

    if not cand_dirs:
        print(f"error: no {staging_config.candidates_rel()} under {hub}", file=sys.stderr)
        # Name the likely cause instead of leaving the reader to guess. A relocated tree with
        # the variable unset -- or a per-domain tree left over from before centralization --
        # is indistinguishable from an empty mesh from the error text alone.
        misplaced = staging_config.find_misplaced_candidates(hub)
        if misplaced:
            print(staging_config.misconfig_message(misplaced), file=sys.stderr)
        return 2

    for d in cand_dirs:
        collect(d, rows)

    if as_json:
        print(json.dumps({"hub": hub, "candidates": rows}, indent=2))
        return 0

    # Batch by target file: candidates landing in one document are ONE edit.
    #
    # The key is the bare `target`, which is now Hub-relative and therefore unique.
    # It used to have to be (repo, target): a target was REPO-relative, and
    # `technical/system-behavior.md` existed in most repos, so keying on it alone merged
    # one service's facts into another's document -- cross-repo fact corruption under a
    # confident review. The single-Hub collapse makes that impossible by construction.
    # APPEND batches here too: it has a real destination, and several new members landing in
    # one collection are still one reviewed change. It is NOT one edit to one file, though --
    # each appended candidate becomes its own new file -- so the batch header says which kind
    # of target it is rather than claiming every batch is a single-document edit.
    batches = {}
    for r in rows:
        if r["verdict"] in ("MERGE", "CONTRADICTS", "APPEND"):
            batches.setdefault(r["target"], []).append(r)

    print(f"Promotion plan: {hub}")
    print(f"{len(rows)} candidate(s) awaiting a decision.")
    print()

    if batches:
        print("=" * 76)
        print("BATCHED BY TARGET -- one change per target, so it is reviewed whole")
        print("=" * 76)

        # Everything lives in one repo, so the whole batch is ONE PR regardless of how many
        # domains it spans. This used to fan out into one PR per repo (a PR lives in exactly
        # one repo -- a git fact), with independent fates per PR. That fan-out is gone.
        for target in sorted(batches):
            group = batches[target]
            blocked = [r for r in group if r["verdict"] == "CONTRADICTS"]
            domains = sorted({r["domain"] for r in group})
            appends = [r for r in group if r["verdict"] == "APPEND"]
            print()
            kind = "collection" if target.endswith("/") else "file"
            print(f"  {target}  ({len(group)} candidate(s), {kind})")
            # Always shown now. It used to be gated on `--mesh`, because only that mode could
            # span domains; with one staging tree every run can, so gating it would hide the
            # answer in exactly the runs that need it.
            print(f"    domain: {', '.join(domains)}")
            linked = [r for r in group if r["duplicate_of"]]
            for r in group:
                mark = "  BLOCKED" if r["verdict"] == "CONTRADICTS" else ""
                if r["duplicate_of"]:
                    mark += f"  DUPLICATE OF {r['duplicate_of']}"
                print(f"    [{r['verdict']:11}] {r['id']:12} {r['type']}{mark}")
            if linked:
                print(f"    -> {len(linked)} candidate(s) already linked as duplicates by "
                      f"dedup at ingestion.")
                print("       Ingestion never resolves these -- it only links, so nothing "
                      "was rewritten.")
                print("       Merge the claim ONCE. Mark the duplicates canonical without "
                      "merging them again.")
            if appends:
                print(f"    -> {len(appends)} of these CREATE a new member file, one each, "
                      f"named from the")
                print("       collection's pattern in the index. Nothing existing is edited. "
                      "The collection's")
                print("       row must already exist. Ordinal patterns number by reading the "
                      "directory, so")
                print("       run promotion single-threaded.")
            if blocked:
                print(f"    -> This batch contains {len(blocked)} contradiction(s). "
                      f"Resolve them with a human")
                print(f"       BEFORE merging the rest -- they may change what the "
                      f"others say.")
        print()
        if len(batches) > 1:
            print(f"  {len(batches)} file(s) affected -> 1 PR. All context lives in one "
                  f"repo, so the")
            print("  batch is reviewed and merged as a single change.")
            print()

    others = [r for r in rows if r["verdict"] not in ("MERGE", "CONTRADICTS", "APPEND")]
    if others:
        print("=" * 76)
        print("NOT A WRITE INTO CANONICAL CONTEXT")
        print("=" * 76)
        for r in others:
            print()
            print(f"  [{r['verdict']:8}] {r['id']:12} {r['type']}  -> {r['target']}")
            print(f"      {r['why']}")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
