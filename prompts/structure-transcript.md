# Structure a raw transcript

A vendor-neutral prompt that turns a raw conversation transcript into a **clean, labeled
transcript** — the kind of pre-structured input a good Granola template would have produced,
but for *any* recording from *any* tool.

## What this is, and why it exists

Some meeting tools (Granola, for one) let a user attach a template that pre-structures a
recording as it is captured — speaker turns cleaned up, topics grouped, noise dropped. That
structure makes everything downstream easier. But it is a dependency on someone having written
a good template *inside that one tool*, and a raw Zoom / Meet / Teams / Slack export has no
such structure at all.

This prompt does that structuring as a **mesh artifact** instead, so it works on any raw
transcript regardless of where the recording came from. It inverts the dependency: someone
*could* paste this prompt into Granola as a template, but nothing requires Granola — any LLM
can run it against any transcript.

**It is plain markdown on purpose.** No scripts, no vendor packaging, no assumption about which
model runs it. Paste it into an LLM chat, wire it into a pipeline, or drop it into a meeting
tool's template slot. A vendor-specific wrapper may come later; it will wrap this prompt, not
replace it.

## The one boundary that must not move

**This prompt cleans and labels. It never assigns meaning.**

It does **not**:

- assign any node type (Knowledge, DomainFact, Requirement, OpenQuestion, …),
- decide what is `decided` vs. `undecided`,
- touch domains, indexes, routing, or the vocabulary,
- output typed chunks or anything a downstream tool would parse as structured data.

All of that — the actual *meaning* — is assigned exactly once, later, by the ingestion process
(`ingest-conversation`, stages 2–3). That is the single source of truth for "a good typed
chunk." If this prompt also typed things, the two would drift and you would have two answers to
the same question. So it stops at **a better transcript**: readable markdown, still a
transcript, just clean and grouped.

Think of the output as a *tidied recording*, not a first draft of the mesh.

## Input

Any raw transcript:

- a meeting transcript or auto-generated captions (Zoom, Meet, Teams, Otter, …),
- a Granola or other note export,
- a Slack thread or chat log,
- pasted text from anywhere.

Speaker labels may be messy, missing, or wrong. Filler, false starts, crosstalk, and
pleasantries are expected. That is what this pass is for.

## Output

**A clean, labeled markdown transcript.** Not JSON, not a schema, not chunks. The shape:

1. A short **participants** line if the speakers are identifiable, naming them as the
   transcript does.
2. The body grouped into **topically-labeled segments**. Each segment is a `##` heading naming
   the topic in a few words, followed by the cleaned speaker turns for that stretch of
   conversation.
3. Within a segment, keep it as speaker turns — `**Name:** what they said`, cleaned up. Merge a
   speaker's fragmented consecutive lines into one turn. Drop filler words, abandoned tangents,
   restatements, and pure pleasantries. Preserve meaning and who said what; do not summarize
   away the substance.

Keep it a transcript a human can read top to bottom. Resist the urge to invent a rigid format —
the next stage consumes this the same way it consumes any raw transcript, so a readable
labeled transcript is exactly right and a bespoke schema is exactly wrong.

Order segments in the order the conversation reached them. Do not reorder to look tidy; the flow
is itself context.

## Do not redact anything

**Keep speaker names exactly as the transcript gives them.** Do not replace them with role
labels, do not anonymize, do not substitute. Who said what is content, and downstream stages
rely on it.

This prompt had a `strip | enrich` PII policy through v2.3, and stripping identity was the
default. It is gone. Cleaning a transcript and redacting one are different jobs, and only the
first belongs here: **you are normalizing the text, not policing it.** If a transcript's
speakers need resolving or disambiguating — the same person appearing as "Sarah", "Sarah K."
and "SK" — that is a *correctness* improvement, and a legitimate future extension of this
prompt; replacing them all with `Speaker 1` is not.

Retention is decided by whoever owns the repo the transcript lands in, not by this prompt.

## Worked example

**Raw in:**

```
[00:03] Sarah Chen: yeah so um, hey — before we start, did you catch the game last night?
[00:03] Mike: haha no I missed it. ok so
[00:04] Mike: the thing is, the, the refund flow. right now when a refund
[00:04] Mike: when a refund fails we just, we retry it like three times and give up
[00:05] Sarah Chen: right and the customer never hears anything
[00:05] Sarah Chen: which is the actual problem. the API key is sk_live_9f2a... by the way, rotate that
[00:06] Mike: oh yeah. anyway. so I think we need a dead-letter queue or something
[00:06] Sarah Chen: maybe. not sure a DLQ is the right call yet
```

**Clean labeled out:**

```
**Participants:** Sarah Chen, Mike

## Refund failure handling

**Mike:** Right now when a refund fails, we retry it three times and then give up.

**Sarah Chen:** And the customer never hears anything — which is the actual problem.
The API key is sk_live_9f2a... by the way, rotate that.

**Mike:** I think we need a dead-letter queue, or something like it.

**Sarah Chen:** Maybe — I'm not sure a DLQ is the right call yet.
```

What happened: the pleasantry about the game was dropped, and each speaker's fragmented lines
were merged into single turns. **Names were kept as spoken**, and so was the aside about the
API key — this prompt removes nothing, and an aside that reads as noise here may be the one
durable fact in the meeting (someone needs to rotate that key). The disagreement about the DLQ
was **kept as spoken** too — it is not this prompt's job to decide whether it is settled. That
call belongs to ingestion.

The judgment being exercised is *"is this the same utterance, said more cleanly?"* — never
*"should this have been said?"*

## What this does NOT do

- **No types.** It never labels a turn as Knowledge / Requirement / DomainFact / etc.
- **No decided/undecided call.** It keeps disagreements and open threads as spoken.
- **No routing.** It knows nothing about domains, indexes, or where anything will live.
- **No vocabulary.** It never touches the mesh schema.
- **No redaction.** It removes nothing — not names, not secrets, not asides. It normalizes
  wording; it never decides what should have been said.
- **No bespoke output format.** The result is a readable labeled transcript, nothing a
  downstream tool has to special-case.

Its whole job is to hand the ingestion process a cleaner transcript than it would otherwise
get — and then get out of the way.
