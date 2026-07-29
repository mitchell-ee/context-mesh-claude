# context-mesh — what setup builds

Status: design note. Written 2026-07-21; **rewritten the same day by the
[single-Hub collapse](vocabulary.md#v20-2026-07-21--the-single-hub-collapse).**

The original version scoped setup as "run over a set of ~100 repos." **There is one repo.**
Setup now stands up the Hub and carves it into domain folders. This document records what
survived that change and what it deleted.

---

## What setup is

**One command whose behavior is determined by what it finds on disk.** Not an init mode and an
add mode.

1. **Check the Hub, and stand it up if absent** — its directory structure and its root
   `context-index.md`.
2. **Prompt for which domains to set up.** No org query, no discovery, no membership file as
   input. A human names them. Adding a domain later means **running setup again** — the same
   command, not a separate path.
3. **Per named domain,** create the directory skeleton and a domain `context-index.md`.
4. **Report the aggregate** — which domains are ready, which need a human decision (no index
   entries, no workflow declared).

**Idempotence is the load-bearing property.** It is what makes "run it again to add a domain"
safe rather than a second code path. A run naming five domains where four are already
configured does exactly the work of a run naming the one new domain.

---

## The line from decision 4 survives: container vs. claim

[build-scope.md](build-scope.md) decision 4: setup **does not generate context files**, because
generating them means generating the *manifest* (per-implementation config), and an **empty
context file is worse than an absent one** — the index would list a file that exists and says
nothing, and *routing reads the index*, so ingestion would land a fact in a stub with
confidence.

**Setup creates directories and the index file. It never creates a context file listed in that
index.**

- An empty `staging/candidates/` **is not a lie** — nothing routes *to* a directory, and its
  emptiness is accurate.
- An index with zero entries **is not a lie** — it says "this domain has no context yet," which
  is true, and is exactly the honest gap decision 4 wants reported.
- `business-context.md` existing and saying nothing **is** the lie, because routing reads the
  index and would confidently land a fact in a stub.

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
