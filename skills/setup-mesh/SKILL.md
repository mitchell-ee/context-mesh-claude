---
name: setup-mesh
description: Set up the AI Hub and its domain folders to receive ingested context — survey which domains are ready, scaffold the containers they need, find or declare each context-index, and configure where to-dos go (the backlog workflow). Use when preparing the Hub for ingestion, adding a domain, when a Todo has nowhere to route, or when asked to set up / configure / onboard for context-mesh.
---

# Set up the Hub and its domains for ingestion

**All context lives in the AI Hub — one repo.** Context about one thing lives in that thing's
**domain folder** inside the Hub; code repos hold no context and are unaware of the mesh.

Runs **once, then again to add a domain** — not per transcript. Two jobs:

1. **The index** — find `context-index.md`, or declare one from what already exists.
2. **The workflow config** — where do to-dos go? Write the pointer, declare it in the index.

Both are **committed** — they're properties of the domain and its team, the same for whoever
ingests.

**There is no separate scaffolding command.** Adding a domain is **this same skill run again**;
it is idempotent, so there is no separate "add" mode
([setup-scope.md](../../docs/setup-scope.md)). Ask which domains to include — don't discover
them, and don't maintain a membership list.

**Always check the Hub root.** Every run: if it has no `context-index.md`, stand it up first.

**The root index carries the PII policy.** Its Identity section has a `**PII policy:**` line —
`strip` (the default) or `enrich` — read by both the transcript structurer
([prompts/structure-transcript.md](../../prompts/structure-transcript.md)) and
`ingest-conversation`. `strip` redacts speaker identity; `enrich` preserves who-said-what and
takes on client + DPO custody obligations. Scaffold writes `strip`; changing it to `enrich` is
a deliberate data-custody decision, not a setup default — surface it, don't flip it unasked.

## Survey first, then scaffold

Two scripts, and the order matters — **survey is read-only; scaffold is the only writer.**

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/setup-mesh/scripts/survey_mesh.py" <hub-root>
python3 "${CLAUDE_PLUGIN_ROOT}/skills/setup-mesh/scripts/scaffold_domain.py" <hub-root> [<domain> ...]   # --dry-run to preview
```

The survey sorts the root and every domain into **READY** / **PARTIAL** / **BLOCKED**, and
splits what's missing into the only two categories that matter:

| | What it is | Who fixes it |
|---|---|---|
| **scaffold creates** | containers — directories, an empty index | the script, unattended |
| **needs a human** | claims — what a file is about, when to load it, where work queues | the team |

**`scaffold_domain.py` creates containers and never a claim.** Directories
(`staging/candidates/`, `process/workflows/`) and a stub `context-index.md` **with no
entries**. It will never create `technical/repo-overview.md`, and never add a row to the
index. The Hub root gets no `process/workflows/` — it has no team backlog by design, since
`Todo`s route to the domain that owns the work.

**It is idempotent.** A re-run changes nothing and says so. That is what makes "run it again to
add a domain" the add path — and it's why a re-run **opens no PR**: there is no diff.

**The gate:** setup writes to the Hub, which every team lives with, so it follows the one
rule — **the skill's job ends at opening a PR**, and it does not merge, chase review, or wait.
One PR, not one per domain: there is only one repo.

## What this does NOT do — read this first

**It does not generate context files.** Not `business-context.md`, not `coding-standards.md`,
none of the manifest. Setup **discovers and declares what exists**; it never authors content.

This is deliberate ([build-scope.md](../../docs/build-scope.md) decision 4). Two reasons:

- **The file list is the manifest** — per-implementation config the engagement decides, not
  something a wizard emits. Generating eighteen Layer A files would be the opposite of what
  manifest-as-config means.
- **An empty context file is worse than an absent one.** The index would list a file that
  exists and says nothing, and routing reads the index. Ingestion would confidently route a
  fact to `business-context.md — why the platform exists` and land it in a stub. **An absent
  file is an honest gap the skill reports; an empty file is a lie the skill believes.**

If a domain genuinely needs its context files written, that's an authoring job for the people
who know the answers. Setup can tell you *which are missing*. It cannot know what they say.

**It does not configure transcript sources.** Where transcripts come from varies per person
and per transcript — one company runs Granola and Otter and Zoom at once. That's not
setup config, and a saved default would be a hint the skill has to second-guess. Ingestion infers
the source from the actual input at stage 1 and confirms it. No config file.

## Job 1 — The index

### If `context-index.md` exists

Read it and check it against reality:

- **Listed but missing** — the index names a file that isn't there. Ingestion will route to it
  and the write will land in a vacuum. **Report it.**
- **Present but unlisted** — a context file exists that the index doesn't name. Ingestion
  can't route to it, because routing reads the index only. **Offer to add it** — ask what it's
  about and when to load it; don't invent those.
- **No workflows section** — go to job 2.

### If there is no `context-index.md`

Walk the human through declaring one. **Find what's there, then ask about each file** — the
index needs two things per entry that only a human knows:

- **What it's about** — one line.
- **When to load it** — the progressive-disclosure condition. This is the part routing
  actually reads, and the part a wizard cannot guess.

Look for the usual shapes (`technical/`, `product/`, `process/`, an existing OST) and propose
what you find. **Propose, then confirm** — never assume `technical/system-behavior.md` is
about what the default manifest says it's about. It's their domain.

Write `context-index.md` following [templates/context-index.md](templates/context-index.md).

## Job 2 — The workflow config (where to-dos go)

**This is the job with no path today.** Without it, every action item ingestion finds is
unroutable: a `Todo` may only be `routed-to` a `Workflow`, and a domain with no declared
workflow has no legal target. Run 1 of ingestion produced two `Todo`s and could place
neither — at *high* confidence, because the agent knew exactly what it wanted and found
nothing there.

Ask one question:

> **Where does this team's work get queued?** (Jira project, Linear team, GitHub issues, …)

Then write `process/workflows/backlog.md` from
[templates/workflow.md](templates/workflow.md), with `system` and `external_ref` pointing at
the real thing, and declare it in the index's Workflows section.

**The workflow file is a pointer, not a container.** The backlog lives in Jira; this file
names it and says where. A `Todo` routed here is **identified and attributed, not filed** —
filing is a human act in the real system. See
[file-taxonomy.md](../../docs/file-taxonomy.md#workflows--where-a-routable-process-lives-added-2026-07-16).

**Never write a list of to-dos into the mesh.** That makes it a shadow issue tracker with a
second source of truth, rotting from the day it's written. If someone asks for that, the
answer is no — the mesh's job is to know *where* work goes, not to *be* where work goes.

**If the team genuinely has no tracker**, a workflow with no `external_ref` is legal but it is
a smell: it means the mesh is about to become one. Say so, and ask again.

### Other workflows

`backlog` is the one ingestion needs. A domain may declare others (`triage`, `refinement`) —
same shape, same pointer rule. Cross-team processes belong in the **Hub root's** index
instead; the index that lists a workflow declares who owns it.

## Verify

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/setup-mesh/scripts/check_setup.py" <hub-root>        # the root, or one domain, in detail
python3 "${CLAUDE_PLUGIN_ROOT}/skills/setup-mesh/scripts/survey_mesh.py" <hub-root>        # the whole Hub, triaged
python3 "${CLAUDE_PLUGIN_ROOT}/skills/setup-mesh/scripts/check_references.py" <hub-root>   # every edge target resolves
```

`check_references.py` walks every edge in the Hub and checks its target exists — paths, node
IDs, artifact IDs, domain names. **The exception it exists for:** a `rendered-on` edge points at
a `Board` in Miro or Claude Design, addressed by an ID rather than a path. A validator that
assumes "target = path" flags every sidecar as dangling, and one that's then silenced stops
catching real breaks.

It's a **positive rule, not a mute**, and it's enforced both ways: a `rendered-on` target must
be an off-filesystem board reference and must **not** be a path (a file target would make the
board canonical, which `board-sidecars.md` forbids), and no other edge type may target a
board. Whether the board *exists* is deliberately not checked — that's the vendor's API, and
asking would couple the mesh to a vendor.

Exit 0 = ingestion can run. Exit 1 = it can't, or would misroute.

**Blocked** means genuinely broken: no index, or the index lists files that don't exist
(facts would route into a vacuum), or a workflow that's a checkbox list rather than a pointer.

**A missing workflow is a note, not a blocker** — `Knowledge` and `DomainFact` route fine
without one; only `Todo`s can't. That's a real consequence worth stating, but it isn't
broken: the **Hub root** has no team backlog by design (to-dos route to the domain that owns
the work), and a team may genuinely have no tracker. A check that nags every domain for
differing from the most-configured one gets ignored, and then it catches nothing.

## When you're done

Say plainly:

- What was declared, and what was already there.
- **Which context files are missing** relative to the default manifest — as a *list for the
  humans*, not a to-do for the skill. Ingestion will report gaps honestly when it hits them.
- Whether a `Todo` can now route.
