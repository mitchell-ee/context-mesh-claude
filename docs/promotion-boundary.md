# context-mesh — promotion, and where the skills' job ends

Status: design note. Written 2026-07-21; **rewritten the same day by the
[single-Hub collapse](vocabulary.md#v20-2026-07-21--the-single-hub-collapse) (vocabulary v2.0).**

The original version of this doc existed to tell apart **two different things both called
"promotion."** One of them no longer exists. What remains is the primary flow, and this doc
now covers it plus the one rule that governs every write to the Hub.

---

## The one rule that governs everything below

**The skills' job ends at opening a PR.** Anything that changes the Hub — whether a human typed
it or a skill assembled it — lands as a PR, and from that point **standard change control takes
over**: review, approve, request changes, merge, revert. The skills never publish directly,
never decide *whether* a change is worth a human's attention, and never manage anything
downstream of the PR.

This single rule deletes a surprising amount of previously-specced machinery (a staleness gate,
a "material change" classifier, silent auto-publish). Those all existed to let *some* changes
skip the human. Nothing skips the human. So there is nothing to classify.

**The collapse strengthens this rule rather than weakening it.** The PR gate was previously
justified partly by *audience* — setup and promotion wrote to repos the person running them
might not own. That argument is gone, but a better one replaces it: the Hub is now the **single
shared repo every team writes to**, so contention on the same files goes *up*, not down. A PR is
more load-bearing here than it was across many repos, not less.

---

## Promotion: staging → canonical

**What moves:** durable facts and prose — `Knowledge`, `DomainFact`. "The retry limit is 3."
"The CFO is a persona." Singletons, path-referenced.

**What happens:** ingestion reads a transcript and drops proposed facts into `staging/`. A human
reviews the batch, confirms/rejects. Each confirmed fact is **merged into a section of an
existing canonical document**, in a branch, which becomes a PR. After that fact is accepted,
**the document is its home** — edited there under normal change control from then on, with no
ongoing tie back to where it came from (except the candidate's `derives-from` audit trail,
which stays in staging).

**Human moments — two, different in kind:**

1. **Ingestion checkpoint** — "did the robot read the transcript correctly? are these the right
   candidates?" Reviews the *robot's reading*. **No PR** — staging is a private holding pen;
   each run writes new, unique-ID files, so runs never collide. (The 2026-07-20 decision:
   staging is a direct write.)
2. **Promotion** — "should these staged facts become canonical?" This is the change-control
   decision, and **this is where the PR is born.**

**Batching → one PR per batch.** A review batch is grouped by target document, so three
candidates targeting `system-behavior.md` become one edit and one review rather than three
conflicting passes. Because everything now lives in one repo, a batch spanning several domains
is still **one PR** — the previous fan-out into one-PR-per-repo is gone, along with the
independent-fates caveat that came with it.

> **What the collapse simplified here.** Batching used to key on `(repo, target)`, never the
> bare `target` — because a `target` was *repo-relative* and `technical/system-behavior.md`
> exists in most repos, so keying on it alone silently merged one service's facts into
> another's document. That was **cross-repo fact corruption under a confident review**, and it
> is now structurally impossible: targets are Hub-relative and unique. The batch key is just
> `target`.

**Status:** built (`skills/ingest-conversation/`, `skills/promote-candidate/`).

---

## What used to be "Pipeline 2," and why it is gone

A second flow — **leaf → Hub sharing** — used to copy a team's discovery artifacts into the Hub
as read-only snapshots so other teams could see them.

It existed for **exactly one reason: read-access boundaries.** In a ~100-repo org, no team can
read all hundred repos, so referencing an artifact in place produced a dead link for anyone
without access, and the Hub was *the one repo everyone can read*.

**That reason no longer holds.** All Hub content — domain-specific included — is readable by
everyone. Referencing an artifact in place now always works: it is always current, needs no
snapshot, no allow-list entry, and no PR. This is precisely the `uniform` access mode the design
already defined as a **no-op**, and the built skill already refused to run in it.

**Deleted with it:** `skills/promote-to-hub/`, `hub/promoted/`, `promotion-allowlist.md`, the
`Access model:` declaration, the `promoted-from` edge, and the partitioned-vs-uniform
per-engagement question.

**One naming consequence worth stating:** "promotion" is now unambiguous. It means
staging → canonical, and nothing else.

---

## The canonical CI mirror is also gone

Adjacent to the above, the mirror copied each leaf's *canonical context* into `hub/<repo>/` on
merge to main, stamped `mirrored-from: <repo>@<sha>`. It was the one deliberate exception to the
PR rule (a generated copy has nothing to review, so it pushed directly).

With one repo there is nothing to copy: the file a developer edits **is** the canonical file.
`mirror_to_hub.py` and `mirror-workflow.yml` are deleted, and with them the project's last
**UNVERIFIED** component — the CI trigger that could never be tested here for want of a remote
and a second repo.

---

## Open, deliberately

- **Retention policy for archived transcripts** — a client + DPO call, deliberately open,
  unaffected by the collapse.
- **How domain ownership is declared.** Repo boundaries used to make "authored in exactly one
  place" structurally true. It is still true by construction in one repo, but *which team owns
  which domain* is now a declaration (`owned-by`, CODEOWNERS) rather than a filesystem fact.

## Resolved by the collapse

- ~~The seeding client's access model (partitioned vs. uniform)~~ — moot; all Hub content is
  readable by everyone.
- ~~Whether the allow-list lives at the Hub root or per-repo~~ — there is no allow-list.
