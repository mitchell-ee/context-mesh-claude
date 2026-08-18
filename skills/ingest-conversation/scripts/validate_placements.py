#!/usr/bin/env python3
"""Validate proposed placements against the context-mesh vocabulary (LOCKED v1).

This is the deterministic half of ingestion stage 3. The LLM proposes placements; this
script decides whether they are legal. It encodes docs/vocabulary.md and nothing else --
if this disagrees with that doc, the doc wins and this is a bug.

Usage:
    validate_placements.py <placements.json>            # validate, human-readable report
    validate_placements.py <placements.json> --quiet    # exit code only

Exit codes: 0 = all legal, 1 = at least one violation, 2 = malformed input.
"""

import json
import re
import sys

# --- docs/vocabulary.md, transcribed. Node type -> legal outgoing edges. ------------

LEGAL_EDGES = {
    # Group A -- ingestion types
    "Conversation": {"references"},
    "Knowledge": {"derives-from", "applies-to", "references", "contradicts"},
    "Requirement": {"derives-from", "references", "contradicts"},
    "DomainFact": {"derives-from", "applies-to", "references", "contradicts"},
    "OpenQuestion": {"derives-from", "references"},
    # Group B -- discovery & work artifacts
    "Outcome": {"parent-of", "rendered-on"},
    "Opportunity": {"parent-of", "references", "rendered-on"},
    "Solution": {"parent-of", "references", "rendered-on"},
    "Assumption": {"references", "rendered-on"},
    "Story": {"parent-of", "references", "rendered-on"},
    "Epic": {"parent-of", "rendered-on"},
    "Interview": {"references"},
    # Group C -- canonical context & structural
    "ContextFile": {"applies-to", "references", "loaded-by", "owned-by"},
    "Persona": {"applies-to", "references"},
    "Architecture": {"applies-to", "references"},
    "Domain": {"owned-by"},
    "Board": set(),  # terminal -- only ever a rendered-on target
}

# v2.2: `Todo`, `Task`, and `Workflow` were removed along with the edges `routed-to`,
# `triggers`, and `creates`. The mesh holds context; a queue is the work itself. An
# ingested action item is now reported as out of scope rather than typed and routed.
# The mesh holds context, not work: a queue is the work itself, and every team tracks it
# differently. Action items are noticed and reported, never filed.

# Group A nodes must carry derives-from: provenance is mandatory (vocabulary.md).
GROUP_A = {"Conversation", "Knowledge", "Requirement", "DomainFact", "OpenQuestion"}

# Conversation is the provenance root -- it is what others derive FROM.
PROVENANCE_EXEMPT = {"Conversation"}

VALID_TAGS = {"decided", "undecided"}

# vocabulary.md v1.1: the Conversation node is the provenance root every ingested fact hangs
# off. It must point at something a human can go and read, or provenance bottoms out in a
# node the agent wrote about a source nobody can check.
VALID_SOURCE_KINDS = {"referenced", "archived", "ephemeral"}

# 4-digit zero-padded, domain-prefixed: payments:OPP-0042 (file-taxonomy.md).
# 0000 is in range -- it conventionally means "precedes everything".
ID_PATTERN = re.compile(
    r"^[a-z0-9][a-z0-9-]*:(OUTCOME|OPP|SOL|ASSUMPTION|STORY|EPIC)-\d{4}$"
)


class Violation:
    def __init__(self, chunk_id, rule, detail):
        self.chunk_id = chunk_id
        self.rule = rule
        self.detail = detail

    def __str__(self):
        return f"  [{self.rule}] {self.chunk_id}\n      {self.detail}"


def validate_conversation(chunk, cid):
    """Provenance-root rules (vocabulary.md v1.1).

    Deliberately does NOT reject source_kind 'ephemeral'. Weak provenance is legal -- it is
    surfaced at the checkpoint for a human, not blocked here. Blocking would make the tool
    unusable wherever conversations genuinely arrive as pasted text, and would push people
    toward inventing a source_ref to get past the check, which is worse than an honest
    'ephemeral'.
    """
    out = []

    kind = chunk.get("source_kind")
    if not kind:
        out.append(Violation(
            cid, "no-source-kind",
            "Conversation has no source_kind. Must be one of: "
            f"{', '.join(sorted(VALID_SOURCE_KINDS))}. This decides whether the raw "
            "transcript survives the run -- it cannot be left implicit."))
    elif kind not in VALID_SOURCE_KINDS:
        out.append(Violation(
            cid, "bad-source-kind",
            f"source_kind '{kind}' invalid. Must be one of: "
            f"{', '.join(sorted(VALID_SOURCE_KINDS))}."))

    # 'ephemeral' has nothing to point at, by definition -- that is what it means.
    if kind in ("referenced", "archived") and not chunk.get("source_ref"):
        out.append(Violation(
            cid, "no-source-ref",
            f"source_kind is '{kind}' but there is no source_ref. Every fact this run "
            "produces hangs off this node; it has to point at something a human can read."))

    if kind == "archived" and not chunk.get("source_archive"):
        out.append(Violation(
            cid, "no-archive-path",
            "source_kind is 'archived' but no source_archive path is recorded. 'archived' "
            "exists precisely because nothing else will hold this transcript -- without the "
            "path, the archive is a claim rather than a fact."))

    # An archive path on a referenced source means a copy was kept that didn't need keeping.
    # The whole point of 'referenced' is that context-mesh takes no custody of PII.
    if kind == "referenced" and chunk.get("source_archive"):
        out.append(Violation(
            cid, "unnecessary-archive",
            "source_kind is 'referenced' but a source_archive was written. A referenced "
            "source is already held by its own datastore -- archiving it takes custody of "
            "PII for no benefit. Drop the archive, or the kind is wrong."))

    if not chunk.get("content_hash"):
        out.append(Violation(
            cid, "no-content-hash",
            "Conversation has no content_hash. Re-ingesting the same conversation would "
            "duplicate rather than update."))

    return out


def validate_chunk(chunk, index):
    """Return a list of Violations for one proposed placement."""
    out = []
    cid = chunk.get("id") or f"<chunk {index} has no id>"
    ntype = chunk.get("type")

    if not ntype:
        out.append(Violation(cid, "no-type", "Chunk has no node type."))
        return out

    if ntype not in LEGAL_EDGES:
        known = ", ".join(sorted(LEGAL_EDGES))
        out.append(Violation(cid, "unknown-type",
                             f"'{ntype}' is not in the vocabulary. Known types: {known}"))
        return out

    legal = LEGAL_EDGES[ntype]
    edges = chunk.get("edges", [])

    for edge in edges:
        etype = edge.get("edge")
        target = edge.get("target")

        if not etype:
            out.append(Violation(cid, "malformed-edge", f"Edge with no type: {edge!r}"))
            continue

        if etype not in legal:
            legal_list = ", ".join(sorted(legal)) if legal else "(none -- terminal type)"
            out.append(Violation(
                cid, "illegal-edge",
                f"'{ntype}' may not originate '{etype}'. Legal for {ntype}: {legal_list}"))

        if not target:
            out.append(Violation(cid, "no-target",
                                 f"Edge '{etype}' has no target. Edges need real targets."))
            continue

        # An ID-shaped target must be well-formed. Path targets are checked by eye at the checkpoint.
        if re.match(r"^[a-z0-9-]+:[A-Z]", str(target)) and not ID_PATTERN.match(str(target)):
            out.append(Violation(
                cid, "malformed-id",
                f"Target '{target}' looks like an ID but isn't valid. "
                f"Expected domain-prefixed 4-digit, e.g. payments:OPP-0042"))

    # Provenance is mandatory for every Group-A node except the Conversation root.
    if ntype in GROUP_A and ntype not in PROVENANCE_EXEMPT:
        if not any(e.get("edge") == "derives-from" for e in edges):
            out.append(Violation(
                cid, "no-provenance",
                f"'{ntype}' is a Group-A node and must carry derives-from back to the "
                f"Conversation. Provenance is mandatory."))

    if ntype == "Conversation":
        out.extend(validate_conversation(chunk, cid))

    tag = chunk.get("tag")
    if ntype != "Conversation":
        if not tag:
            out.append(Violation(cid, "no-tag",
                                 "Chunk must be tagged 'decided' or 'undecided'."))
        elif tag not in VALID_TAGS:
            out.append(Violation(cid, "bad-tag",
                                 f"Tag '{tag}' invalid. Must be 'decided' or 'undecided'."))

    # target_path is required, but null is a legal, meaningful value: "this mesh has no
    # home for this chunk." That is a finding, not an error -- forcing a target would push
    # homeless chunks into the nearest surviving file, which is how a taxonomy rots.
    # Absent (never proposed) and null (proposed, no home) are different things.
    if "target_path" not in chunk:
        out.append(Violation(cid, "no-target-path",
                             "Chunk has no target_path key. Propose a path, or null to "
                             "declare the mesh has no home for it."))
    elif chunk["target_path"] is None and not chunk.get("rationale"):
        out.append(Violation(cid, "unexplained-no-home",
                             "target_path is null but no rationale explains what file "
                             "would need to exist. A gap in the mesh is a finding; it "
                             "has to be legible to be useful."))

    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    quiet = "--quiet" in sys.argv

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

    chunks = data.get("chunks") if isinstance(data, dict) else data
    if not isinstance(chunks, list):
        print("error: expected a JSON list of chunks, or {\"chunks\": [...]}", file=sys.stderr)
        return 2

    violations = []
    for i, chunk in enumerate(chunks):
        if not isinstance(chunk, dict):
            violations.append(Violation(f"<chunk {i}>", "malformed", "Not an object."))
            continue
        violations.extend(validate_chunk(chunk, i))

    if quiet:
        return 1 if violations else 0

    n = len(chunks)
    if not violations:
        print(f"OK: {n} placement{'s' if n != 1 else ''} validated, all legal.")
        return 0

    by_rule = {}
    for v in violations:
        by_rule.setdefault(v.rule, []).append(v)

    print(f"FAIL: {len(violations)} violation(s) across {n} placement(s).\n")
    for rule in sorted(by_rule):
        print(f"{rule} ({len(by_rule[rule])}):")
        for v in by_rule[rule]:
            print(v)
        print()
    print("Fix the proposals and re-validate. Do not write to staging with violations:")
    print("an illegal edge is a validation error, surfaced pre-write (vocabulary.md).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
