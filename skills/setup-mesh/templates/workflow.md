---
type: Workflow
name: backlog                 # backlog | triage | refinement | …
system: jira                  # jira | linear | github | …  (omit only if truly mesh-native)
external_ref: https://<org>.atlassian.net/jira/software/projects/<KEY>
owned-by: <team>            # the authoring owner is a team (vocabulary v2.0), not a domain
---

# <domain> — backlog

Where work for this team is queued.

**The backlog itself lives in <system>** (`external_ref`). This file is **not a copy of it**
and must never become one. It exists so that:

- the graph has a legal `routed-to` target for a `Todo`, and
- an agent that finds an action item knows where it belongs.

## What routing here means

A `Todo` routed to this workflow has been **identified and attributed** — what was said, who
raised it, which conversation it came from — **not filed**. Filing is a human act in
<system>.

The mesh's job is to know *where work goes*, not to *be* where work goes. If this file ever
grows a list of checkboxes, that is the mesh turning into a second, rotting issue tracker.

## Intake

<How action items reach this backlog: refinement, incidents, conversation ingestion. An
ingested `Todo` arrives with its `derives-from` provenance intact — which is more than a
hand-typed ticket usually carries.>
