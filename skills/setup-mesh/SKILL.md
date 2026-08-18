---
name: setup-mesh
description: Set up the AI Hub and its domain folders to receive ingested context — survey which domains are ready, scaffold the containers they need, and find or declare each context-index. Use when preparing the Hub for ingestion, adding a domain, or when asked to set up / configure / onboard for context-mesh.
---

# Set up the Hub and its domains for ingestion

**All context lives in the AI Hub — one repo.** Context is authored in exactly one place and
never mirrored. Context about one thing lives in that thing's **domain folder under
`domains/`**.

**Two things vary, and neither is a mode to detect — just ask, or accept what you find:**

- **The Hub may be its own repo, or it may be the code repo.** A multi-repo product usually
  gives the Hub a repo of its own, and the code repos hold no context. In a monorepo the Hub
  root **is** the repo root: `context-index.md` sits beside `package.json`, and Hub-relative
  and repo-relative paths are the same thing. **Finding code in the Hub is not a
  misconfiguration** and needs no comment.
- **Domains are optional.** A Hub whose context is entirely cross-cutting — no `domains/`
  directory at all — is a **complete mesh**, not a half-built one. Never tell a team with zero
  domains that they have something left to do.

These two are **independent**. A multi-repo product will probably use domains; a monorepo
probably won't; either may do the opposite. Do not infer one from the other, and do not infer
either from what the directory contains.

Runs **once, then again to add a domain** — not per transcript. One job:

**The index** — find `context-index.md`, or declare one from what already exists.

It is **committed** — a property of the domain and its team, the same for whoever ingests.

> **This skill had a second job until v2.2**: configuring where to-dos go (the backlog
> workflow pointer). The workflow layer is deferred — the mesh holds context, and a queue is
> the work itself. See
> The design is retained privately.

**There is no separate scaffolding command.** Adding a domain is **this same skill run again**;
it is idempotent, so there is no separate "add" mode
([setup-scope.md](../../docs/setup-scope.md)). Ask which domains to include — don't discover
them, and don't maintain a membership list.

**"None" is a complete answer to that question**, and the common one for a monorepo. Take it at
face value: stand up the Hub root, create no `domains/` directory, and don't ask again or
suggest adding one later. They can run this skill again if that changes.

**Always check the Hub root.** Every run: if it has no `context-index.md`, stand it up first.

**The root index carries the mesh vocabulary version.** Its Identity section has a
`**Mesh vocabulary:**` line naming the schema version this mesh's content is written in.
Setup reads it to tell whether the mesh predates a convention change — see
[Migrations](#migrations). A missing marker means *unknown*, not *current*.

## Survey first, then scaffold

Three scripts, and the order matters — **both surveys are read-only; scaffold is the only
writer.**

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/setup-mesh/scripts/survey_repo.py" <repo-root>        # what context ALREADY exists
python3 "${CLAUDE_PLUGIN_ROOT}/skills/setup-mesh/scripts/survey_mesh.py" <hub-root>         # is the mesh set up correctly
python3 "${CLAUDE_PLUGIN_ROOT}/skills/setup-mesh/scripts/scaffold_domain.py" <hub-root> [<domain> ...]   # --dry-run to preview
```

**`survey_repo.py` runs first, and answers the question that comes before the mesh exists.**
`survey_mesh.py` reads the indexes and checks what they declare — useless before there is an
index, which is exactly when setup runs. `survey_repo.py` instead walks the repo and reports:

- **What is already there**, sorted into the three kinds of home — proposed **singletons**,
  proposed **collections** (a folder of same-typed files), and **known structures** the plugin
  already understands and that need no declaration.
- **What appears to be missing**, as a short list of the *highest-level* file covering each
  gap.

**Everything it prints is a proposal, never a decision.** It cannot know what a file is about
or when to load it, and those are the two things an index row needs. Walk the human through
its output; don't apply it.

**It recommends the highest-level artifact, and so should you.** A repo with no architecture
documentation needs `technical/architecture.md` — *not* a six-file split into
target-architecture, integration-map, API standards, and NFRs. Splitting is a later move, made
when one real file grows too big to load for a single task. **Never open with the split
version**: that is how a setup flow produces eighteen files nobody fills in.

**Match what the repo already does, not the default manifest.** If they keep architecture at
`docs/architecture/overview.md`, that gap is closed — the script suppresses the recommendation
on a name match, and you should too. Proposing `technical/architecture.md` beside their
existing file creates a second home for one kind of context, which is the thing the mesh
exists to prevent. Their layout wins; the default manifest is a starting set, not a target.

**It proposes; it never detects domains.** Grouping files by the directory they sit in is not
a claim that any directory is a domain. A domain is a directory under `domains/`, and nothing
else is one.

The survey sorts the root and every domain into **READY** / **PARTIAL** / **BLOCKED**, and
splits what's missing into the only two categories that matter:

| | What it is | Who fixes it |
|---|---|---|
| **scaffold creates** | containers — directories, an empty index | the script, unattended |
| **needs a human** | claims — what a file is about, when to load it | the team |

**`scaffold_domain.py` creates containers and never a claim.** Directories
(`staging/candidates/`) and a stub `context-index.md` **with no entries**. It will never
create `technical/repo-overview.md`, and never add a row to the index.

**A domain is created at `domains/<name>/`, and a domain is nothing else.** There is no
detection heuristic: anything under `domains/` is a domain, anything outside it isn't,
whatever it is named or contains. (Before v2.2 domains sat at the Hub root and had to be
detected, which reported a `docs/product/` research folder as a domain while missing the real
one.)

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

> **This is a rule about *this skill*, not a ban on generated context.** The reason setup
> doesn't author is that **it has no source to author from** — no interview, no transcript,
> nothing but a directory listing. A tool that *does* have a source (a PM answering an
> interview, an ingested conversation) may absolutely write context files. The invariant both
> cases share is narrower and is the real rule:
>
> **Never index a file that says nothing.** A file its source did not populate should be
> neither created nor listed. An absent file is an honest gap; an empty listed one is a lie.
>
> So a setup flow that pairs this skill with an authoring tool is correct and expected —
> the authoring tool writes what it learned, this skill declares the structure around it.

**It does not configure transcript sources.** Where transcripts come from varies per person
and per transcript — one company runs Granola and Otter and Zoom at once. That's not
setup config, and a saved default would be a hint the skill has to second-guess. Ingestion infers
the source from the actual input at stage 1 and confirms it. No config file.

## The index

### If `context-index.md` exists

Read it and check it against reality:

- **Listed but missing** — a **pending home**, not an error. The row declares *where this kind
  of context goes*; it never claimed the home was occupied. Promotion creates the file when it
  has content for it, patterned on the file's siblings, and updates the row in the same PR.
  **Report it as a note, never as a blocker** — but name the paths, because a typo'd row looks
  identical and nothing downstream catches one.
- **Present but unlisted** — a context file exists that the index doesn't name. Ingestion
  can't route to it, because routing reads the index only. **Offer to add it** — ask what it's
  about and when to load it; don't invent those.
- **Lists nothing at all** — a real state worth naming. Routing reads the index and only the
  index, so an index with no rows can receive nothing. Usually the rows are there but aren't
  **markdown links** (backticked or plain-text paths parse to nothing), so check the format
  before concluding the mesh is empty.

### If there is no `context-index.md`

**Run `survey_repo.py` first**, then walk the human through what it found. The index needs two
things per entry that only a human knows:

- **What it's about** — one line.
- **When to load it** — the progressive-disclosure condition. This is the part routing
  actually reads, and the part a wizard cannot guess.

**Propose, then confirm** — never assume `technical/system-behavior.md` is about what the
default manifest says it's about. It's their domain.

Two judgments the script hands you rather than making:

- **Is a proposed collection really one kind of context?** Several markdown files in one folder
  is what a collection looks like on disk, and also what two unrelated documents look like. A
  collection row claims they are the same kind, so ask.
- **Is a proposed singleton context at all?** Working notes, scratch files, and meeting
  detritus all end in `.md`. Anything not worth routing to should simply not be listed —
  leaving it out is free, and listing it makes routing consider it forever.

Write `context-index.md` following [templates/context-index.md](templates/context-index.md).

### Two format rules the index must follow

Both exist because breaking them is silent — the index looks right and the tooling reads
something different.

**1. A context-file row's path must be a markdown link.** `[technical/system-behavior.md](technical/system-behavior.md)`,
not `` `technical/system-behavior.md` ``. The checker extracts paths with a link regex, so a
backticked or plain-text row is invisible: it does not get checked, and routing cannot see the
file. An index written entirely in backticks parses to **zero** files while looking complete.

**2. A file named under "Not in this mesh" must NOT be a markdown link.** That section names
files that *should not exist*, so linking one makes it read as a context file that is listed
and missing. Backtick them, one bullet each, with the reason:

```markdown
- `governance/data-handling.md` — the platform team owns this; not duplicated here
- `product/personas/` — personas are cross-cutting; see the Hub root
```

**3. A collection row's path is a LINK ending in `/`.** A collection is a folder of same-typed
files that nothing traverses — ADRs are the usual case — and it gets **one row for the folder**,
in its own `## Collections` table:

```markdown
## Collections

| Collection | Members | About | Load when |
|---|---|---|---|
| [decisions/](decisions/) | `NNN-{slug}.md` | Architecture decision records | deciding something with precedent |
```

- **The trailing slash is what tells a collection from a file**, for a human and for the
  checker both. The context-file regex requires a literal `.md`, so a collection needs the
  slash to be seen at all.
- **Linked, not backticked** — the opposite of rule 2, and for the same underlying reason: a
  link means "this is a real home." A collection **is** one; a deliberate gap is not.
- **`Members` is the naming pattern** — one of `{slug}.md`, `{date}-{slug}.md`, or
  `NNN-{slug}.md`. It is used only to *name* a new member; nothing reads meaning back out of
  an existing filename.
- **A missing directory is an error; an empty one is a note.** Nothing creates the folder for
  you, but an empty declared collection is a normal state — the row says where this kind of
  context goes, not that any exists yet.

**Four states share filename-shaped syntax and mean different things.** Keep them apart:

| State | Where it goes | Means |
|---|---|---|
| **Deliberate gap** | *Not in this mesh*, backticked | This file should never exist here |
| **Pending home** | a context-table row, linked | Declared home; not written yet. **Normal** — promotion fills it |
| **Broken link** | a context-table row, linked | Was real, now missing — a genuine error |
| **Collection** | a *Collections* row, linked, trailing `/` | A folder of same-typed files; one row covers every member |

**The last two are still indistinguishable, and now neither blocks.** That is a deliberate
trade: treating a pending home as broken was the worse error, because it made setup withhold
READY over work that simply had not happened yet. The consequence is that a **typo in a row's
path is not caught by anything** — promotion will create a file at the misspelling. The count
in the verdict is the prompt to read the paths yourself.

## Migrations

The plugin cannot run code when it is updated — there is no install hook — so migration is
**lazy**: the Hub root index's `**Mesh vocabulary:**` line makes the gap visible the next
time this skill runs, and this skill applies the fix.

**The marker prompts; it never selects.** Every migration decides for itself whether it
applies by inspecting content, so a mesh with **no** marker (scaffolded before the marker
existed, or hand-authored) still migrates correctly. Treat a missing marker as *unknown*,
never as *current*.

**Run every migration in
`${CLAUDE_PLUGIN_ROOT}/skills/setup-mesh/migrations/`, in version order — including ones
at or below the mesh's marker.** Do not filter by version. That is what the guards are for,
and it is what makes a **retroactively added** migration work: one written after meshes
already reached that version would never be selected by a newer-than filter.

**The migrations ship with the plugin**, at
`${CLAUDE_PLUGIN_ROOT}/skills/setup-mesh/migrations/`, never in the user's Hub. **A bare
relative path like `migrations/` is ambiguous** — resolved against the Hub it finds nothing,
which is not evidence of a packaging problem. Re-resolve `${CLAUDE_PLUGIN_ROOT}` before
concluding anything.

| Migration | Applies when | Does |
|---|---|---|
| [0.3.0-domains-under-domains.md](migrations/0.3.0-domains-under-domains.md) | a root-level dir holds a `context-index.md` | **reports only** — the human moves it |
| [0.3.0-defer-workflow-layer.md](migrations/0.3.0-defer-workflow-layer.md) | a `## Workflows` section, or a row into `process/workflows/` | removes those index rows; reports what is now unreferenced |
| [0.6.0-remove-pii-policy.md](migrations/0.6.0-remove-pii-policy.md) | the Hub root index has a `**PII policy:**` line | removes that line; reports that ingestion no longer redacts |
| [0.11.0-open-questions-into-targets.md](migrations/0.11.0-open-questions-into-targets.md) | a `staging/open-questions.md` exists | **reports only** — the human moves each question into the file it is about |

**The one rule every migration honors** ([migrations/README.md](migrations/README.md)):

> **A migration only ever edits an index, or reports. It never moves, deletes, or rewrites
> content in the mesh.**

The plugin only ever *adds* to the mesh. Content is the team's — often the only copy, and
worth more than the tooling. A migration that wants to move a file **reports instead**.

For each migration: **preview, show, ask, then apply.** Never migrate without approval. If
they decline one, honor it, skip it, and **do not stamp the marker** — the mesh is still
mid-migration.

### Stamping

**Do not stamp because the migrations ran. Stamp because the content is correct.**

After migrations, re-run the verification below. Update the root index's
`**Mesh vocabulary:**` line to the plugin's vocabulary **only if** every check passes and no
migration with real work to do was declined. A stamped mesh that is still stale is worse than
an unstamped one: nothing prompts, and the staleness is invisible.

If a check fails, leave the marker alone and say why. The gap staying visible is the intended
behavior, not a defect to work around.

## Verify

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/setup-mesh/scripts/check_setup.py" <hub-root>        # the root, or one domain, in detail
python3 "${CLAUDE_PLUGIN_ROOT}/skills/setup-mesh/scripts/survey_mesh.py" <hub-root>        # the whole Hub, triaged
python3 "${CLAUDE_PLUGIN_ROOT}/skills/setup-mesh/scripts/survey_mesh.py" <hub-root> --manifest   # every tracked file, grouped
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

**Blocked** means genuinely broken: **no index at all.** Routing reads the index and only the
index, so without one the container is invisible.

**A listed-but-missing file does not block** (changed 2026-08-06). It is a pending home, and
promotion creates it.

**An index that lists nothing is a note, not a blocker.** `scaffold_domain.py` deliberately
writes an empty index (a container, never a claim), so calling its own output broken would
make the two scripts contradict each other. But the verdict says so out loud rather than
reporting a bare READY: *"READY to run — but nothing to route to."* A plain "what it lists is
real" is vacuously true of an empty list, and that phrasing is exactly how this went
unreported before.

## When you're done

**Always end by showing the manifest** — `survey_mesh.py <hub-root> --manifest`. It lists
every file the indexes track, grouped by the Hub root and each domain, marking each `ok`,
`pending` (declared but not yet written — promotion will create it), or `unlisted` (present
but invisible to routing).

Show it in full rather than summarizing. The triage output says what is *broken*; the
manifest is how a human checks what is **right** — a file tracked under the wrong domain, or
one they expected and cannot find, is not an error any script can detect, and it is exactly
what a person reading the list will spot. Invite them to correct anything that looks wrong.

Then say plainly:

- What was declared, and what was already there.
- **Which kinds of context appear to be missing** — from `survey_repo.py`, as a short list of
  *the highest-level file that would cover each gap*, and as a *list for the humans*, not a
  to-do for the skill. Ingestion will report gaps honestly when it hits them.
  **Do not expand one recommendation into several.** If architecture is missing, say
  `technical/architecture.md` — one file. Naming the eventual split invites a team to create
  six empty files, and an empty indexed file is worse than an absent one.
  **Say plainly that these are optional.** A repo without design principles is not a broken
  repo; it is a repo without design principles.
- **Which listed files are pending homes** — declared but not yet written. Say the paths out
  loud, and say that promotion will create them. **This is the only place a typo'd row gets
  looked at**, so it is a list to read, not a count to skim.
- Whether the index actually lists anything yet — a scaffolded stub is set up but cannot
  receive a fact until someone fills it in.
- **Any context routing cannot see** — a root-level directory holding an index, reported by
  the survey. Say what it is, and that nothing was moved. Never call it a domain: an index
  outside `domains/` is a fact about visibility, not a diagnosis of what the directory is.
- **Whether the marker was stamped**, and if not, what still has to be true first.

**Say nothing about a mesh having no domains.** The survey's header line reports the count and
that is enough. Adding "you could add domains later" to a finished root-only setup reads as a
correction, and there is nothing to correct — the survey deliberately stays silent here, so
don't reintroduce the nag in the summary.
