#!/usr/bin/env python3
"""Render proposed placements as a scannable approval list, grouped by destination file.

The in-run checkpoint is THE human gate for ingestion: shown BEFORE anything is written,
while the transcript is still in context and re-proposing is cheap. On approval the chunks
are written straight to staging -- there is no staging PR (the PR gate lives at promotion
into canonical context). The summary form below becomes the commit message body, so the run
stays auditable after the fact.

GROUPED BY DESTINATION, because that is how a reviewer actually reads: everything landing in
`technical/integration-map.md` is one judgment about one document, and it is also how
promotion batches later. A flat list of 26 chunks makes the reader rebuild that grouping in
their head.

RISK STILL LEADS, via the group order. Groups are sorted by their RISKIEST MEMBER, and every
chunk shows its own confidence inline. This preserves the property the flat riskiest-first
ordering existed for -- the placements most likely to be wrong are read while attention is
freshest -- without scattering a document's chunks across the list.

EVERYTHING IS ALWAYS SHOWN. Confidence decides ORDER and DEPTH, never visibility. A
miscalibrated chunk marked high is exactly the failure that matters, so neither review mode
may omit one: the overview NAMES every chunk with its target and confidence before the
reviewer chooses how to read them.

THE MODE MENU IS NOT PRINTED. The skill presents the choice as a selection list, and every
approve/retry/drop decision in the walk is a selection list too -- the reviewer picks, they
do not type a command. The only free text at the gate is a retry REASON, which carries a
correction no list can enumerate. This script prints what a reviewer needs in order to
choose; it does not ask the question.

Usage:
    render_checkpoint.py <placements.json>             # the grouped overview
    render_checkpoint.py <placements.json> --full      # every chunk in full, grouped
    render_checkpoint.py <placements.json> --group <target>   # ONE group in full, for the walk
    render_checkpoint.py <placements.json> --summary   # markdown for the commit body
    render_checkpoint.py <placements.json> --pr-body   # deprecated alias for --summary
"""

import json
import sys

CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}
# No confidence at all is more suspect than low -- it means the model didn't judge.
NO_CONFIDENCE = -1

BANNER = "=" * 78


def sort_key(chunk):
    """Least-confident first. Flags break ties WITHIN a confidence band, never across it.

    Confidence leads because it is the skill's own statement of where it might be wrong,
    and that is what a reviewer's attention should track. Flags do not outrank it: a
    high-confidence NO HOME is not risky -- the skill is certain there is no home, and
    usually right. Sorting flags first would push those above genuine medium-confidence
    judgment calls, burying the chunks that actually need a human.
    """
    conf = CONFIDENCE_ORDER.get(chunk.get("confidence"), NO_CONFIDENCE)
    contradicts = 0 if any(e.get("edge") == "contradicts"
                           for e in chunk.get("edges", [])) else 1
    homeless = 0 if chunk.get("target_path", "") is None else 1
    return (conf, contradicts, homeless, str(chunk.get("id", "")))


def group_by_target(chunks):
    """Group chunks by destination file, groups ordered by their riskiest member.

    The group's sort key is the sort_key of its worst chunk, so a file holding one low
    confidence placement sorts above a file of six high-confidence ones. Within a group,
    chunks keep the same riskiest-first order.

    `(no home in this mesh)` is a real group, not an error state -- those chunks have nowhere
    to land and the reviewer needs to see them together, since the finding is the gap itself.
    """
    groups = {}
    for c in chunks:
        groups.setdefault(fmt_target(c), []).append(c)

    out = []
    for target, members in groups.items():
        members.sort(key=sort_key)
        out.append((target, members))
    # Riskiest group first; ties broken by target path so the order is stable run to run.
    out.sort(key=lambda g: (sort_key(g[1][0]), g[0]))
    return out


def id_ranges(chunks):
    """Compress consecutive same-prefix IDs: k-0001, k-0002, k-0003 -> k-0001-0003.

    26 chunks listed individually is a wall of IDs nobody reads. Collapsing runs makes the
    shape of a group visible at a glance -- and a gap in a run is itself informative, since
    it means a sibling chunk went somewhere else.
    """
    parsed = []
    for c in chunks:
        cid = str(c.get("id", "?"))
        prefix, _, num = cid.rpartition("-")
        if prefix and num.isdigit():
            parsed.append((prefix, int(num), len(num), cid))
        else:
            parsed.append((None, None, None, cid))

    runs, current = [], []
    for item in sorted(parsed, key=lambda p: (p[0] or "", p[1] if p[1] is not None else -1)):
        if not current:
            current = [item]
            continue
        prev = current[-1]
        same_prefix = item[0] is not None and item[0] == prev[0]
        consecutive = same_prefix and item[1] == prev[1] + 1
        if consecutive:
            current.append(item)
        else:
            runs.append(current)
            current = [item]
    if current:
        runs.append(current)

    parts = []
    for run in runs:
        if len(run) == 1:
            parts.append(run[0][3])
        elif len(run) == 2:
            # A run of two reads worse as a range than as two IDs.
            parts.extend(r[3] for r in run)
        else:
            parts.append(f"{run[0][3]}-{str(run[-1][1]).zfill(run[-1][2])}")
    return ", ".join(parts)


def flags(chunk):
    out = []
    if chunk.get("target_path", "") is None:
        out.append("NO HOME")
    if any(e.get("edge") == "contradicts" for e in chunk.get("edges", [])):
        out.append("CONTRADICTS")
    if chunk.get("duplicate_of"):
        out.append("DUPLICATE")
    # Collection member resolution (stage 3.4). `NEW MEMBER` is routine and not flagged --
    # it is what most collection chunks do. `NEAR-MATCH` is flagged because it is the case
    # most likely to be WRONG: resolution found a plausible member, was not confident, and
    # created rather than merged. Nothing downstream re-examines that judgement, so if it is
    # not caught here it is not caught at all.
    if chunk.get("member_resolution") == "created-near-match":
        out.append("NEAR-MATCH")
    return out


def fmt_target(chunk):
    tp = chunk.get("target_path", "")
    if tp is None:
        return "(no home in this mesh)"
    return tp or "(none proposed)"


def provenance_line(conv):
    """One line on where this came from, and whether anyone can check it later.

    Shown at the top because it qualifies everything below it: these placements are only as
    trustworthy as the source they derive from, and 'ephemeral' means nobody can ever go back
    and check. That is a decision for the human at the gate, not a footnote.
    """
    if not conv:
        return None
    kind = conv.get("source_kind")
    ref = conv.get("source_ref")

    if kind == "referenced":
        return f"Source: {ref}  (held by its own datastore -- nothing archived here)"
    if kind == "archived":
        return (f"Source: {ref}  (no datastore behind it -- transcript archived AS RECEIVED "
                f"at {conv.get('source_archive')})")
    if kind == "ephemeral":
        return ("Source: EPHEMERAL -- nothing to point at. Facts below cannot be checked "
                "against the original, now or ever.")
    return f"Source: UNSPECIFIED (source_kind missing -- this should have failed validation)"


def type_breakdown(chunks):
    """`19 Knowledge + 7 OpenQuestion` -- what KIND of review this is, before the detail."""
    counts = {}
    for c in chunks:
        counts[c.get("type", "?")] = counts.get(c.get("type", "?"), 0) + 1
    return " + ".join(f"{n} {t}" for t, n in
                      sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def render_chunk_full(c, indent="    "):
    """One chunk, in full: what it claims, where it goes, why, and what it links to."""
    conf = (c.get("confidence") or "UNRATED").upper()
    fl = flags(c)
    marker = "  <-- " + ", ".join(fl) if fl else ""
    print(f"{indent}{c.get('id','?'):10} {conf:7} {c.get('type','?')}{marker}")
    print(f"{indent}  {c.get('title') or '(untitled)'}")
    body = c.get("body") or c.get("claim")
    if body:
        for line in str(body).splitlines():
            print(f"{indent}  {line}")
    if c.get("rationale"):
        print(f"{indent}  why: {c['rationale']}")
    # What member resolution decided, and -- for a near-match -- WHAT it nearly matched.
    # Naming the rejected member is the point: "created a new persona" is not reviewable,
    # "created a new persona, but `first-time-buyer` was close" is.
    mr = c.get("member_resolution")
    if mr == "resolved":
        print(f"{indent}  member: MODIFY existing -> {c.get('member_path', '?')}")
    elif mr == "created":
        print(f"{indent}  member: CREATE new (no existing member matched)")
    elif mr == "created-near-match":
        near = c.get("member_near_match") or "?"
        print(f"{indent}  member: CREATE new -- but `{near}` was close. Merge instead?")
    edges = c.get("edges", [])
    if edges:
        es = ", ".join(f"{e.get('edge')}->{e.get('target')}" for e in edges)
        print(f"{indent}  edges: {es}")
    print()


def render_terminal(chunks, dropped, conv=None, full=False, conv_count=0):
    live = [c for c in chunks if not c.get("duplicate_of")]
    dupes = [c for c in chunks if c.get("duplicate_of")]
    groups = group_by_target(live)

    print(BANNER)
    print("INGESTION CHECKPOINT -- approve before anything is written to staging")
    print(BANNER)
    print()
    prov = provenance_line(conv)
    if prov:
        print(prov)
        print()

    if not live:
        print("  Nothing to place.")
        print()
    else:
        print(f"{len(live)} chunk(s) need your approval ({type_breakdown(live)}).")
        if conv_count:
            # Say why they are absent. A count that doesn't add up reads as a bug.
            noun = "node is a provenance root" if conv_count == 1 else "nodes are provenance roots"
            print(f"The {conv_count} Conversation {noun}, not claims -- not reviewed.")
        if dupes:
            print(f"{len(dupes)} dropped as duplicates of existing context (listed below).")
        if dropped:
            print(f"{dropped} chunk(s) discarded during distillation as non-durable.")
        print()
        print("Grouped by destination, which is how they will be presented either way.")
        print("Groups are ordered by their riskiest chunk; confidence is shown per chunk.")
        print()

        # The group's worst confidence, spelled out: it is WHY a row sorts where it does,
        # and without it a 3-chunk group above a 6-chunk one looks arbitrary.
        def worst_label(members):
            fl = flags(members[0])
            return fl[0].lower() if fl else (members[0].get("confidence") or "unrated").lower()

        w = max([len(t) for t, _ in groups] + [11])
        cw = max([len(worst_label(m)) for _, m in groups] + [6])
        print(f"  {'Destination'.ljust(w)}  {'Chunks':>6}  {'Lowest'.ljust(cw)}  IDs")
        print(f"  {'-' * w}  {'-' * 6}  {'-' * cw}  {'-' * 38}")
        for target, members in groups:
            print(f"  {target.ljust(w)}  {len(members):>6}  "
                  f"{worst_label(members).ljust(cw)}  {id_ranges(members)}")
        print()

        risky = [c for c in live if flags(c) or c.get("confidence") == "low"]
        if risky:
            print(f"{len(risky)} of them need your eye: "
                  f"{id_ranges(risky)} (low confidence, or flagged).")
            print()

    if full and live:
        for target, members in groups:
            print("-" * 78)
            print(f"{target}  ({len(members)})")
            print("-" * 78)
            print()
            for c in members:
                render_chunk_full(c)

    if dupes:
        print("-" * 78)
        print("DROPPED AS DUPLICATES (already present at the target; not written)")
        print("-" * 78)
        print()
        for c in dupes:
            print(f"  {c.get('id','?'):10} {c.get('title') or '(untitled)'}")
            print(f"    already in: {c.get('duplicate_of')}")
            print()

    if full or not live:
        # No command syntax here either: the reviewer is offered these as a selection
        # list, so printing `retry <id> [reason]` would teach a vocabulary they never
        # need to type. What they DO need is what the choices mean, and that retry has
        # a deadline.
        print(BANNER)
        print("For each chunk you can approve it, correct it, or drop it -- and you can")
        print("approve the rest of a file, or all the rest, once the remainder looks")
        print("routine. Correcting a chunk re-proposes it against the transcript.")
        print()
        print("That works only while this run is live: the transcript is still in context")
        print("and is discarded at the end. Once written, a wrong placement is hand-edited.")
        print(BANNER)
        return

    # The MODE CHOICE IS NOT PRINTED HERE. The skill presents it as a selection list
    # (AskUserQuestion), so printing a numbered menu would duplicate it and invite the
    # free-text answer the selection list exists to replace. What is printed is the
    # context a reviewer needs BEFORE choosing -- notably the retry trade-off, which is
    # the one consequence that cannot be undone once the run ends.
    print(BANNER)
    print("TWO WAYS TO REVIEW THEM")
    print(BANNER)
    print()
    print("  Walk them with me   -- group by group, riskiest first. Each chunk in full,")
    print("                         then you approve it, correct it, or drop it. You can")
    print("                         approve the rest of a file, or all the rest, whenever")
    print("                         the remainder looks routine.")
    print()
    print("  Write a review file -- everything in full to one markdown file, to read at")
    print("                         your own pace.")
    print()
    print("Nothing is hidden either way: every chunk is at least named, with its target")
    print("and confidence. A high-confidence chunk that is wrong is the failure that")
    print("matters, so neither mode omits one -- they differ in DEPTH, not coverage.")
    print()
    print("The review file costs the retry loop. The transcript is discarded when this")
    print("run ends, so a placement you dislike later is a hand-edit against a transcript")
    print("that no longer exists -- not a re-proposal. Walking keeps the run live, where")
    print("retry is nearly free.")
    print(BANNER)


def render_group(chunks, target):
    """One destination file's chunks, in full -- the unit the walk presents at a time.

    Returns 0 when the group was rendered, 1 when the target names no group. It MUST fail
    loudly: a walk that asks for a group and gets a silent empty render would step over
    every chunk in it, approving nothing and showing nothing, and the reviewer would see a
    file scroll past with no content and reasonably assume it held none. That is the
    fail-open shape -- an exclusion that looks like an absence.
    """
    groups = dict(group_by_target([c for c in chunks if not c.get("duplicate_of")]))
    members = groups.get(target)
    if members is None:
        print(f"error: no group with destination {target!r}", file=sys.stderr)
        known = "\n  ".join(sorted(groups)) or "(none -- nothing to place)"
        print(f"known destinations:\n  {known}", file=sys.stderr)
        return 1

    print("-" * 78)
    print(f"{target}  ({len(members)})")
    print("-" * 78)
    print()
    for c in members:
        render_chunk_full(c)
    return 0


def render_pr_body(chunks, dropped, conv=None):
    live = [c for c in chunks if not c.get("duplicate_of")]
    dupes = [c for c in chunks if c.get("duplicate_of")]
    ordered = sorted(live, key=sort_key)

    print("## Proposed placements")
    print()
    print("Reviewed and approved at the in-run checkpoint before this was written to "
          "staging. Ordered riskiest first.")
    print()

    if conv:
        kind = conv.get("source_kind")
        ref = conv.get("source_ref")
        print("**Provenance.** ", end="")
        if kind == "referenced":
            print(f"Source `{ref}` — held by its own datastore. No transcript archived here.")
        elif kind == "archived":
            # Say "as received" rather than "sanitized": through v2.3 the archived copy was
            # redacted, and a checkpoint line claiming that when nothing was modified is a
            # false assurance -- the human reading it decides whether to keep the file.
            print(f"Source `{ref}` — no datastore behind it, so the transcript was "
                  f"**archived as received** at `{conv.get('source_archive')}`. It is not "
                  f"redacted. Retention and deletion for that copy are not set by this tool; "
                  f"`.gitignore` it if this mesh should not keep transcripts.")
        elif kind == "ephemeral":
            print("**Source is ephemeral** — there is nothing to point at. The facts below "
                  "cannot be checked against the original.")
        print()
    print("| # | Confidence | Type | Tag | Chunk | Target |")
    print("|---|---|---|---|---|---|")
    for i, c in enumerate(ordered, 1):
        fl = flags(c)
        flag_s = " **" + ", ".join(fl) + "**" if fl else ""
        target = fmt_target(c)
        target_s = "_no home_" if c.get("target_path", "") is None else f"`{target}`"
        print(f"| {i} | {c.get('confidence','UNRATED')} | {c.get('type','?')} | "
              f"{c.get('tag','—')} | {c.get('id','?')}{flag_s} | {target_s} |")
    print()

    attention = [c for c in ordered if flags(c) or c.get("confidence") == "low"]
    if attention:
        print("### Needs your eye")
        print()
        for c in attention:
            fl = ", ".join(flags(c)) or "low confidence"
            print(f"- **{c.get('id')}** ({fl}) — {c.get('rationale') or 'no rationale given'}")
        print()

    if dupes:
        print("### Dropped as duplicates")
        print()
        print("Already present at the target file; not written.")
        print()
        for c in dupes:
            print(f"- **{c.get('id')}** — already in `{c.get('duplicate_of')}`")
        print()

    if dropped:
        print(f"### Discarded during distillation")
        print()
        print(f"{dropped} chunk(s) carried no durable claim.")
        print()


def main():
    # `--group` takes a VALUE, so it cannot be filtered with the rest of the flags -- its
    # argument is a bare word and would otherwise be mistaken for the placements file.
    argv = sys.argv[1:]
    group_target = None
    rest = []
    i = 0
    while i < len(argv):
        if argv[i] == "--group":
            if i + 1 >= len(argv):
                print("error: --group needs a destination path", file=sys.stderr)
                return 2
            group_target = argv[i + 1]
            i += 2
            continue
        rest.append(argv[i])
        i += 1

    args = [a for a in rest if not a.startswith("--")]
    if len(args) != 1:
        print(__doc__)
        return 2

    try:
        with open(args[0]) as fh:
            data = json.load(fh)
    except FileNotFoundError:
        print(f"error: no such file: {args[0]}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"error: {args[0]} is not valid JSON: {exc}", file=sys.stderr)
        return 2

    if isinstance(data, dict):
        chunks = data.get("chunks", [])
        dropped = data.get("dropped_count", 0)
    else:
        chunks, dropped = data, 0

    # The Conversation node isn't a placement decision -- don't make the human read it at a
    # gate that exists to catch bad routing. But keep it: it carries the provenance the rest
    # of the list depends on.
    convs = [c for c in chunks if c.get("type") == "Conversation"]
    conv = convs[0] if convs else None
    chunks = [c for c in chunks if c.get("type") != "Conversation"]

    # --summary is the current flag; --pr-body is kept as a deprecated alias.
    if "--summary" in rest or "--pr-body" in rest:
        render_pr_body(chunks, dropped, conv)
    elif group_target is not None:
        return render_group(chunks, group_target)
    else:
        render_terminal(chunks, dropped, conv,
                        full="--full" in rest, conv_count=len(convs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
