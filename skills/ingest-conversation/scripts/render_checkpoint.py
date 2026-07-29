#!/usr/bin/env python3
"""Render proposed placements as a scannable approval list, riskiest first.

The in-run checkpoint is THE human gate for ingestion: shown BEFORE anything is written,
while the transcript is still in context and re-proposing is cheap. On approval the chunks
are written straight to staging -- there is no staging PR (the PR gate lives at promotion
into canonical context). The summary form below becomes the commit message body, so the run
stays auditable after the fact.

Ordering is the whole point. Low confidence sorts first, so the placements most likely to
be wrong are read while attention is freshest. Everything is always shown -- the skill's own
confidence decides the *order*, never the *visibility*. A miscalibrated chunk marked high is
exactly the failure that matters, and hiding it behind a confidence filter is how it ships.

Usage:
    render_checkpoint.py <placements.json>
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


def flags(chunk):
    out = []
    if chunk.get("target_path", "") is None:
        out.append("NO HOME")
    if any(e.get("edge") == "contradicts" for e in chunk.get("edges", [])):
        out.append("CONTRADICTS")
    if chunk.get("duplicate_of"):
        out.append("DUPLICATE")
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
        return (f"Source: {ref}  (no datastore behind it -- sanitized copy archived at "
                f"{conv.get('source_archive')})")
    if kind == "ephemeral":
        return ("Source: EPHEMERAL -- nothing to point at. Facts below cannot be checked "
                "against the original, now or ever.")
    return f"Source: UNSPECIFIED (source_kind missing -- this should have failed validation)"


def render_terminal(chunks, dropped, conv=None):
    live = [c for c in chunks if not c.get("duplicate_of")]
    dupes = [c for c in chunks if c.get("duplicate_of")]
    ordered = sorted(live, key=sort_key)

    print(BANNER)
    print("INGESTION CHECKPOINT -- approve before anything is written to staging")
    print(BANNER)
    print()
    prov = provenance_line(conv)
    if prov:
        print(prov)
        print()

    print(f"{len(ordered)} placement(s) proposed. Listed riskiest first: read from the top.")
    if dupes:
        print(f"{len(dupes)} dropped as duplicates of existing context (listed below).")
    if dropped:
        print(f"{dropped} chunk(s) discarded during distillation as non-durable.")
    print()

    if not ordered:
        print("  Nothing to place.")
        print()
    else:
        for i, c in enumerate(ordered, 1):
            conf = c.get("confidence") or "UNRATED"
            fl = flags(c)
            marker = "  <-- " + ", ".join(fl) if fl else ""
            print(f"[{i}] {conf.upper():7} {c.get('type','?'):13} {c.get('id','?')}{marker}")
            title = c.get("title") or "(untitled)"
            print(f"    {title}")
            print(f"    -> {fmt_target(c)}")
            rationale = c.get("rationale")
            if rationale:
                print(f"    why: {rationale}")
            edges = c.get("edges", [])
            if edges:
                es = ", ".join(f"{e.get('edge')}->{e.get('target')}" for e in edges)
                print(f"    edges: {es}")
            print()

    if dupes:
        print("-" * 78)
        print("DROPPED AS DUPLICATES (already present at the target; not written)")
        print("-" * 78)
        print()
        for c in dupes:
            print(f"  {c.get('id','?'):10} {c.get('title') or '(untitled)'}")
            print(f"    already in: {c.get('duplicate_of')}")
            print()

    print(BANNER)
    print("Approve, or say what's wrong.")
    print()
    print("  approve            -> validate, then write to staging")
    print("  retry N [reason]   -> re-propose chunk N with your correction")
    print("  drop N             -> discard chunk N entirely")
    print()
    print("Retry works only while this run is live: the transcript is still in context")
    print("and is discarded at the end. Once written, a wrong placement is hand-edited.")
    print(BANNER)


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
            print(f"Source `{ref}` — no datastore behind it, so a **sanitized copy was "
                  f"archived** at `{conv.get('source_archive')}`. Retention and deletion "
                  f"for that copy are not set by this tool.")
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
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
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
    conv = next((c for c in chunks if c.get("type") == "Conversation"), None)
    chunks = [c for c in chunks if c.get("type") != "Conversation"]

    # --summary is the current flag; --pr-body is kept as a deprecated alias.
    if "--summary" in sys.argv or "--pr-body" in sys.argv:
        render_pr_body(chunks, dropped, conv)
    else:
        render_terminal(chunks, dropped, conv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
