---
# For a Conversation node (the provenance root), use the block at the bottom of this file
# instead — it carries the v1.1 source-reference properties.
id: <chunk-id>                        # e.g. k-0001
type: <Knowledge|Requirement|DomainFact|OpenQuestion>
tag: <decided|undecided>
state: staging                        # always. Nothing ingestion writes is canonical.
target: <eventual/canonical/path.md>  # or: null, with a no-home note in the body
confidence: <high|medium|low>
# duplicate_of: <path.md | candidate-id>   # set by dedup ONLY (stage 3.5). A Hub-relative
#   path when canonical context already carries the claim, or a candidate ID when an
#   unpromoted candidate from an earlier ingestion does. Omit entirely when not a duplicate.
edges:
  - edge: derives-from                # mandatory on every Group-A node
    target: <conversation-id>
  - edge: <applies-to|references|contradicts>
    target: <domain-name | domain:ID-NNNN | hub-relative path>
---

# <Title — a claim, not a topic>

<The body. It must stand alone: the transcript will not exist when someone reads this.
Write it as context, not as a record of a conversation. No "Mike said", no "we discussed" —
state the fact. Anyone who was not in the room should be able to use this.>

## Why this placement

<One line. Why this target, and what in the index pointed at it. If confidence is low, say
what you were unsure about. If target is null, say what file would need to exist.>

## Provenance

Derived from `<conversation-id>` (<source>, <date>).

---

# Conversation node — the provenance root (vocabulary.md v1.1)

Every ingested node hangs off this one via `derives-from`, so it must point at something a
human can go and read. Pick the `source_kind` honestly: it decides whether the raw transcript
survives the run.

```yaml
---
id: conv-NNNN
type: Conversation
state: staging
source: <human-readable, e.g. "checkout/payments sync, 2026-07-14">
source_kind: <referenced|archived|ephemeral>
source_ref: <granola:note/abc123 | slack:permalink | zoom:rec/456 | how it arrived>
source_archive: <path>        # REQUIRED when archived; must NOT be set when referenced
participants: [<role-anonymized>]
date: <YYYY-MM-DD>
content_hash: sha256:<hash of the raw input>   # idempotency: same hash updates, not duplicates
edges:
  - edge: references
    target: <domain-name>
---
```

- **`referenced`** — the normal case. Granola/Slack/Zoom/a ticket already holds it, with its
  own retention and access control. **Store nothing.** Never set `source_archive`.
- **`archived`** — hand-provided, no datastore behind it. Reference-only would point at
  nothing, so archive the transcript **as received** beside this node and record the path.
  The exception, not the default.
- **`ephemeral`** — nothing to point at. Legal, but the facts derived from it can never be
  checked. Flagged at the checkpoint.
