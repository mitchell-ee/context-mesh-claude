---
name: structure-transcript
description: Turn a raw meeting transcript into a clean, labeled one before ingesting it — merge fragmented speaker turns, drop filler, and group into topic segments. Cleanup and labeling only; it never redacts, assigns a type, or routes anything. Use when handed a messy Zoom/Meet/Teams/Otter/Granola export or a chat log, or when asked to clean up, tidy, or structure a transcript before ingestion.
---

# Structure a raw transcript

An **optional pre-pass** before `ingest-conversation`. Raw transcript in, cleaner transcript
out. Its output is still a transcript, and it enters ingestion through the same stage-1 path
as any raw input.

## This skill is a wrapper. The prompt is the source of truth.

**Read [`prompts/structure-transcript.md`](../../prompts/structure-transcript.md) and follow
it.** Everything about what to produce — the output shape, the worked example, the
boundaries — lives there, and **this file deliberately does not restate any of it.**

That is the whole design. The prompt is a **vendor-neutral artifact**: plain markdown any LLM
can run, or that pastes straight into a meeting tool's template slot. It exists precisely to
remove a dependency on one vendor's templating, so it cannot itself become Claude-specific.
This skill is a convenience wrapper that makes it available as `/structure-transcript`; it
adds no rules of its own.

**If the prompt and this file ever disagree, the prompt wins.** Restating its rules here would
create a second source of truth that drifts — the exact failure this project exists to
prevent.

## How to run it

1. **Get the transcript.** A file path, a pasted blob, or an export from any tool. If none was
   given, ask for it.

2. **Read the prompt and apply it** to the transcript.

3. **Return the cleaned transcript**, and say what you did to it: roughly how much was dropped,
   and anything you were unsure about.

## The boundary that must not move

**Cleanup and labeling only. Never typing, never routing.**

This skill does not assign `Knowledge`/`DomainFact`/`Requirement`/`OpenQuestion`, does not call
anything `decided` or `undecided`, and does not know about domains, indexes, or targets. All of
that is assigned exactly once, later, by `ingest-conversation` stages 2–3.

If both did it, the two would drift and there would be two answers to the same question. So
this stops at **a better transcript**.

## It removes nothing

**No redaction, at any point.** Not names, not secrets, not asides. The transcript's content
is the content; this pass normalizes how it reads, never what it says.

There was a `strip | enrich` PII policy here through v2.3, and this skill read it. It is gone —
the prompt has the reasoning. **Retention is decided by whoever owns the repo**, and a team
that does not want transcripts in its history can `.gitignore` them.

## When you're done

Hand the cleaned transcript to `ingest-conversation`, or give it back to the human to review
first. This skill writes nothing to the mesh — it produces text, and nothing else.
