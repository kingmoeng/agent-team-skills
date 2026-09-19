# Progress Reporting

Read this before the first external notification, or when deciding what is worth reporting at all.

## Goal

Keep the user informed without turning worker logs into noise.

## Authorization

**A configured endpoint is not permission to use it.**

Before sending anything to an external channel, confirm the user has authorized that destination for this work, and what may be said there. Configuration establishes capability; only the user establishes consent. When in doubt, report in the session and ask once whether to also send externally.

Never include secrets, credentials, private source code, or large raw logs. Treat webhook URLs and tokens as secrets — including in error messages you might echo back.

## What to report

Send an update for meaningful events:

- the execution plan is established;
- a major milestone completes;
- a major blocker, failure, or delay appears;
- a user decision is required;
- review finds significant rework;
- the work is verified complete.

Do not report every worker message, command, retry, or status check. Do not send an update whose content is "still working".

A useful update answers three questions: what changed, what is happening now, and is user action needed.

## Deduplication

Record the event IDs you have already sent in the execution state.

A Lead that restarts, or two Leads briefly overlapping, will otherwise re-announce milestones that already went out — which trains the user to ignore the channel. Before sending, check whether that event was already delivered.

Consolidate milestones that land close together into one message rather than firing several.

## Delivery

Send directly using an available HTTP, script, or tool capability. Do not spawn a reporting subagent to relay status.

Bound delivery attempts. A failing webhook must never block implementation or consume the attempt budget of real work — retry a small number of times, record the failure, and continue.

Reporting is optional. The absence of a channel must not change the Lead's core behavior.

## Format

Keep updates short.

```text
Status: Backend implementation complete; frontend integration is in progress.
Important: API response shape changed as planned and tests pass.
Action needed: None.
```

For a problem:

```text
Status: Backend task is blocked by provider quota.
Important: Worker context is preserved; reset expected at 17:33.
Action needed: None. Independent frontend work is continuing.
```
