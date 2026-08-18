# context-mesh — what setup builds

Status: design note. Written 2026-07-21; **rewritten the same day by the
[single-Hub collapse](vocabulary.md#v20-2026-07-21--the-single-hub-collapse)**; updated
2026-08-03 for vocabulary v2.2.

The original version scoped setup as "run over a set of ~100 repos." **There is one repo.**
Setup now stands up the Hub and carves it into domain folders. This document records what
survived that change and what it deleted.

> **Two v2.2 changes (2026-08-03).** Domain folders live at **`domains/<name>/`**, so nothing
> has to detect which directories are domains. And setup's **second job is gone** — it used to
> declare the workflow that to-dos route to, which went with the workflow layer
> (deferred; the design is retained privately). Setup is the index job now.

---

## What setup is

**One command whose behavior is determined by what it finds on disk.** Not an init mode and an
add mode.

1. **Check the Hub, and stand it up if absent** — its directory structure and its root
   `context-index.md`.
2. **Prompt for which domains to set up.** No org query, no discovery, no membership file as
   input. A human names them. Adding a domain later means **running setup again** — the same
   command, not a separate path. **"None" is a complete answer** — domains are optional, and a
   mesh whose context is all cross-cutting (the usual monorepo case) gets no `domains/`
   directory and is finished. Don't ask twice, and don't suggest adding one later.
3. **Per named domain,** create the directory skeleton and a domain `context-index.md`.
4. **Migrate, if the mesh predates a convention change** — see below.
5. **Report the aggregate** — which domains are ready, which need a human decision (an index
   with no entries can receive nothing, even though it is not broken).
6. **Report the manifest** — every file the indexes track, grouped by the Hub root and each
   domain. The aggregate says what is *broken*; the manifest is how a human checks what is
   **right**. A file tracked under the wrong domain, or one they expected and cannot find, is
   not an error any script can detect, and it is exactly what a person reading a list spots.

**Idempotence is the load-bearing property.** It is what makes "run it again to add a domain"
safe rather than a second code path. A run naming five domains where four are already
configured does exactly the work of a run naming the one new domain.

---

## Migration: the plugin only ever adds

The plugin cannot run code when it is updated — there is no install hook — so migration is
**lazy**. The Hub root index carries a `**Mesh vocabulary:**` marker; setup reads it, notices
the gap, and applies the fix. **The marker prompts; it never selects.** Every migration guards
on *content shape*, so a mesh with no marker — every mesh built before the marker existed —
still migrates correctly. Setup runs the whole set, in version order, every time.

One rule governs every migration:

> **A migration only ever edits an index, or reports. It never moves, deletes, or rewrites
> content in the mesh.**

Mesh content is the team's — authored by people, often the only copy, and worth more than the
tooling. A migration that relocates a directory it misidentified, or deletes a file it
misread, destroys something the plugin did not create and cannot restore. So the two things a
migration may do are **edit the index** (the plugin's own artifact, and the routing input) and
**report**.

**This is not a limitation worked around; it is the design.** The pre-v2.2 layout put domains
at the Hub root, and the obvious migration would move them under `domains/`. It doesn't —
because deciding which root-level directory *is* a domain is exactly the heuristic v2.2
deleted after it misidentified a docs folder while missing the real domain. The migration
reports what routing cannot see, states plainly that this is **not** a claim about what the
directory is, and the human moves it. Automation lost, correctness kept.

A convention change needs a migration only when existing content becomes **wrong** — not when
it merely becomes non-mandatory. Parents becoming optional and IDs widening to `0000`–`9999`
are pure loosenings and need none.

---

## The line from decision 4 survives: container vs. claim

[build-scope.md](build-scope.md) decision 4: setup **does not generate context files**, because
generating them means generating the *manifest* (per-implementation config), and an **empty
context file is worse than an absent one** — the index would list a file that exists and says
nothing, and *routing reads the index*, so ingestion would land a fact in a stub with
confidence.

**Setup creates directories and the index file. It never creates a context file listed in that
index.**

> **Recommending a missing file is not generating one** (added 2026-08-18, with
> `survey_repo.py`). Setup now reports *"this repo appears to have no architecture
> documentation; the file that would cover it is `technical/architecture.md`"* — a sentence for
> a human, not a file on disk. The rule is unchanged and is precisely why the recommendation
> stops there: setup still has no source to author from, so it names the gap and leaves it.
>
> **Two guards keep the recommendation from becoming the failure mode it warns about.**
> Recommend the **highest-level** artifact that covers the gap, never the eventual split — a
> team told they need six architecture files creates six empty ones, and the empty indexed file
> is the thing decision 4 forbids. And recommend **nothing** where the repo already covers the
> area under its own naming: `docs/architecture/overview.md` closes that gap, and proposing the
> manifest's path beside it would create a second home for one kind of context.

- An empty `staging/candidates/` **is not a lie** — nothing routes *to* a directory, and its
  emptiness is accurate.
- An index with zero entries **is not a lie** — it says "this domain has no context yet," which
  is true, and is exactly the honest gap decision 4 wants reported.
- `business-context.md` existing and saying nothing **is** the lie, because routing reads the
  index and would confidently land a fact in a stub.

**Scoping this correctly (clarified 2026-07-30).** The rule above is about *setup*, and the
reason is that setup **has no source to author from** — it sees a directory listing, nothing
more. It is not a ban on generated context in general. A tool with a real source — a PM
answering a structured interview, an ingested conversation — may write context files, and
should. The invariant that actually generalizes is narrower:

> **Never index a file that says nothing.**

An authoring tool honors it by not emitting stubs for sections its source didn't cover, and by
registering what it *did* populate. Setup honors it by declaring structure and leaving content
alone. Pairing the two is the expected shape, not a conflict.

The distinction was always between *a container* and *a claim*. Only the claim was ever
forbidden.

---

## The gate: setup opens a PR, and stops

Setup writes to the Hub, which every team lives with, so it inherits the one rule from
[promotion-boundary.md](promotion-boundary.md) unchanged — **the skills' job ends at opening a
PR.**

- **Setup opens the PR.** Same act `promote-candidate` performs.
- **It stops there.** No merge, no chasing review, no watching.
- **One PR**, not one per domain. A PR lives in one repo and there is now only one repo, so the
  previous fan-out (and its independent-fates caveat) is gone.

**Why a PR here when ingestion dropped one.** The 2026-07-20 argument against a staging PR was
no concurrency and no added review — it gated *a private holding pen nobody reads from*. Setup
fails that test on **audience**: a domain's context index is something its team lives with, and
they are not necessarily the person who ran setup.

**Idempotence has a visible signal here.** A re-run over an already-configured mesh produces
**no PR at all**, because there is no diff.

---

## What the collapse deleted from this document

- **"Setup runs over a set of repos"** → a set of domain folders in one repo.
- **Hub-vs-leaf role detection.** There is no leaf. `scaffold_repo.py` detected hub-ness from
  the index's `Role:` line to scaffold a mixed batch correctly; there is now one Hub and N
  domains, which are structurally different things rather than two flavors of the same thing.
- **The no-roster decision** — kept, but for a simpler reason. It said the Hub must not track
  which repos are meshed, because the mirror runs *in* each repo and pushes up, so a roster
  would be a second authored copy that drifts into a lie about coverage. **There is no mirror
  now**, and the domain list lives in the root index, which is the manifest — one authored copy,
  no drift. The conclusion survives: *no second list of who's in the mesh.*
- **"Whether the CI mirror job is installed by setup"** — moot; there is no mirror job.
- **The 100-repo scale rationale** for `survey_mesh.py` ("at 100 repos nobody reads 100
  reports"). Surveying N domain folders in one repo is a much smaller job, which is why the
  survey and setup checks collapse together — see below.

## What this does not decide

- **How the domain set is named at the prompt** — an implementation detail.
- **How domain ownership is declared** (`owned-by`, CODEOWNERS). Repo boundaries used to make
  ownership structural; it is now a declaration. See
  [promotion-boundary.md](promotion-boundary.md).
