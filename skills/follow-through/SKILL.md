---
name: follow-through
description: Carry an authorized multi-step task through verified completion with one active executor, preserving progress across commits, interruptions, sessions, and provider limits. Use when the user wants an approved plan carried out without prompting for every next step, or wants unfinished work resumed or handed off sequentially. Not for a single obvious edit, a delegated worker packet, planning or review alone, or coordinating concurrent agents.
---

# Follow Through — 완수

Own the unfinished work until the agreed outcome is verified. A plan, a commit, or a provider switch is a milestone, not completion.

## Establish continuity

Identify the outcome, completion criteria, authorized scope, remaining steps, and required verification. Reuse an existing approved plan; do not ask the user to authorize its ordinary next steps again. Agreement with a design alone is not authorization to implement it.

Preserve the user's chosen providers, spending limits, and permission boundaries. Permission to finish does not itself authorize new paid capacity, external messages, publishing, or deployment; existing authorization for those actions remains valid. Commit when the agreed workflow calls for it, not merely to enable a handoff.

For work that needs delegation, concurrent writers, or coordinated integration, use `team-lead` when available and transfer the goal and progress record. Design and review can be separate phases without changing ownership. This skill does not require another skill to be installed.

## Keep a recoverable record

Before a multi-step run, keep one small task-specific record, for example `.agent-team/follow-through/<task-id>.yaml`. Reuse an equivalent host record if it survives session loss and can be read by the next executor. Record:

- the goal, completion criteria, approved scope and plan, and applicable permissions;
- completed and remaining steps, the next action, and status (`working`, `waiting`, `blocked`, `complete`, or `cancelled`);
- workspace, branch, base/current commit, and a manifest or snapshot of relevant uncommitted changes, including new files; distinguish pre-existing user edits;
- verification evidence and the exact revision or content snapshot it covers, including changed tracked files, new files, and ignored deliverables; distinguish self-review from independent review;
- current provider and session, execution owner, and any host-enforced ownership token;
- blocker or limit, observed usage/reset data with observation time, and any wake-up ID, time, and generation;
- failure fingerprints, recovery attempts, and execution resumptions without verified progress, plus any user-specified time, spending, or retry budget.

Keep long evidence in referenced artifacts. Save at meaningful step boundaries, before a planned handoff or wait, and after verification; do not wait until quota or context is exhausted. Exclude secrets from the record.

At each planned step boundary, reread the record rather than relying on remembered progress. On resuming, handoff, or after context compaction, reconcile it with live sessions, current files, commits, and outstanding reservations before editing. A stale record does not override newer user instructions or changes. Recheck evidence if the work it covered has changed.

## Continue through steps

Perform the next authorized step, verify the increment as appropriate, update progress, and continue. Do not end the run just because one commit or one planned step is done. Answer interim questions and incorporate corrections while retaining unfinished work unless the user cancels or replaces it.

Adjust implementation details within the agreed scope and record meaningful deviations. If a necessary decision changes that scope or requires new authority, complete independent authorized work and request only the missing decision.

Preserve partial edits on interruption. Prefer a verified step boundary for voluntary handoff, but recover from interruptions mid-edit too. Never discard, revert, or force-commit partial work just to obtain a clean handoff. Mark incomplete work and failed or unrun checks explicitly.

## Distinguish context from quota

Context pressure calls for checkpointing and context compaction or a fresh session, not waiting for a quota reset. A replacement executor must be able to act from the record and workspace without the previous conversation.

Account usage limits call for waiting or switching providers. Read usage and reset information from available non-model status facilities or the limit response. Record missing values as unknown; neither assume spare capacity nor invent a reset time. Consider every applicable limit window and the freshness of observations, not just one usage percentage.

Select among authorized providers using task suitability, usable capacity, expected reset delay, and the cost of rebuilding context. Keep the current executor when switching would cost more than it saves. Prefer switching at step boundaries; do not alternate providers on small usage fluctuations. Cross-provider handoff uses the shared work record and actual files, not assumptions that session formats are interchangeable.

## Discover execution capabilities

For the bundled local Codex/Claude Code runner and macOS scheduled resumption, read [references/runtime.md](references/runtime.md) before use. It is optional; other hosts may supply equivalent capabilities. Starting through the runner is required for its managed-workspace lock to apply.

Use available host facilities rather than inventing commands. Establish whether the environment can:

- inspect usage/reset data and identify live sessions;
- launch or resume the selected provider with the recorded workspace, permissions, and task/session identity;
- register and cancel a durable wake-up without consuming model tokens while waiting;
- enforce a single writer across manual resumes, scheduled resumes, and provider handoffs.

A sleeping process or a timestamp in a file is not a wake-up unless something actually invokes the executor. A reservation is not proof of resumed execution. Record confirmed capabilities and limitations; the core policy works without the optional local runner.

## Transfer execution ownership

**Establish one writer before transferring execution.** For a controlled sequential handoff, the outgoing executor may checkpoint, stop writing, confirm that no competing execution or live wake-up remains, record the transfer, and launch one successor; it must not resume writing afterward. This does not require a scheduler or distributed lock. A field in YAML, cancellation request, or expired lease alone cannot exclude another process that may still write.

When automatic and manual starts can race, require confirmed quiescence plus atomic host admission, or equivalent host-enforced fencing that rejects stale writers. Invalidate outgoing wake-ups before admission. On unexpected loss, establish the same exclusion before recovery. If it cannot be established, preserve the work and report the conflict; do not launch a competing writer. A session may be preserved for context without retaining permission to execute.

## Schedule and confirm resumption

For a quota wait, record the applicable observed reset time and register an actual wake-up if supported. Store its ID and generation. If the reset time is unknown, use a supported non-model availability event or bounded status recheck; otherwise report the unknown timing. If scheduling or resumption is unavailable, leave an explicit manual resume point and state that automatic continuation is not scheduled.

Put the record path, task identity, expected generation, and these recovery rules in the wake-up command or payload; do not assume the resumed agent will load this skill. The invoked guard must check generation, status, current ownership, and user cancellation before admitting writes, using the host exclusion mechanism where starts can race. Reject stale or completed/cancelled wake-ups without editing, preferably before invoking a model. Invalidate the old generation on handoff, completion, or cancellation, even if cancelling a timer fails.

At the reset time, recheck availability where possible and reconcile the workspace before resuming the exact session or starting a successor. If a request still hits the limit, update the observed reset information and wait again; do not busy-loop. Confirm the executor actually started. A scheduling acknowledgement alone is insufficient.

## Bound recovery, not progress

Do not repeat a failed approach without new evidence. Default to at most three recovery attempts for the same unresolved implementation, verification, or launch problem; record the initial failure separately and count every subsequent attempt. Carry this count across sessions, providers, and review rework. On exhaustion, mark the work blocked, invalidate unattended retries, and report the evidence and remaining work.

A normal quota wait is not an implementation failure, and verified progress is not grounds to stop. Honor user-specified deadlines or budgets; do not silently raise them. Repeated failed launches are recovery attempts even when labelled as resumptions. A user pause or cancellation prevents scheduled work from restarting it.

Track progress across quota windows: after three execution resumptions without verified progress, stop unattended rescheduling, diagnose the repeated blockage, and report it. Passive availability checks are not execution resumptions. This bounds stalled runs without imposing an arbitrary lifespan on authorized work that is progressing.

## Finish against evidence

Reconcile all remaining steps with the original completion criteria and run the required final verification against the current work. Obtain review when required; identify self-review honestly. Unresolved required work or an unavailable required check is a gap to report, not verified completion.

Persist completion and invalidate outstanding wake-ups before the final report. Report the result, verification, and material limitations. If waiting or blocked, report the saved progress, remaining work, and whether an actual automatic resume is registered, including its time when known.
