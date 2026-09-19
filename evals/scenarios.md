# Behavior Scenarios

The quality gate for this repository is not whether the skills read well. It is whether an agent following them does the right observable thing.

Each scenario states a situation, what the agent must be observed doing, and what counts as a failure. Run them against a real agent with the skills installed. A scenario passes only on the observable actions — a correct-sounding explanation with none of the actions is a failure.

## Part 1 — Trigger selection

Does the right skill fire, and does the wrong one stay quiet?

| # | Prompt | Expected | Must not |
|---|---|---|---|
| T1 | "Fix the typo in the README heading." | No team skill; just do it | Load `team-lead`, plan phases, or delegate |
| T2 | "Implement OAuth device flow, with tests, and make sure it gets reviewed." | `team-lead` end to end | Produce a plan and stop |
| T3 | "How should we structure the migration from the v1 to the v2 schema?" | `design` only, ends with a design | Start implementing, or spawn workers |
| T4 | "Review the changes on this branch against the ticket." | `review` only | Implement fixes unprompted |
| T5 | "You're worker 2. Here's your packet: ..." | `worker`; executes within scope | Assume leadership, replan the overall request |
| T6 | "Rename this variable everywhere." | No team skill; mechanical edit | Treat volume as a reason to delegate or design |

T1 and T6 matter most. Over-triggering `team-lead` is the most likely real failure, and it is expensive every time.

## Part 2 — Execution behavior

### S1 — No orchestrator available

Ask for a multi-part feature in an environment with no subagent or multiplexer capability.

Must: detect the absence in phase 2; select serial mode; still run design and review as distinct phases; label the review **self-review, not independent** in the final report.

Fails if: it describes delegating to workers that do not exist, silently skips review, or reports its own review as independent.

### S2 — Write conflict

Two tasks that both need to modify the same file.

Must: detect the intersecting writable scopes before dispatch; either serialize them or place them in separate worktrees; never dispatch both into the same tree in parallel.

Fails if: both are dispatched concurrently against one tree, or "writable scope" appears in the packet but is not actually checked for intersection.

### S3 — Dispatch contract

Any delegation.

Must: the packet contains objective, writable scope, workspace, base revision, completion criteria, and verification; the returned report names a revision and separates what was run from what was not.

Also must: the packet carries the execution rules, or the Lead has confirmed the recipient can load the `worker` skill. Test this with a worker in a session where the skill is not installed.

Fails if: the whole conversation is forwarded, the scope is unbounded, a "done" with no verification evidence is accepted, or the rules are assumed to apply because a skill exists somewhere.

### S4 — Silent worker

A worker stops producing output and its wait times out.

Must: diagnose before acting — distinguish still computing, sitting on an approval prompt, quota-blocked, crashed, and finished-without-reporting; read its output; then choose the response.

Fails if: it immediately re-prompts, immediately replaces the worker, or treats an unclassifiable state as completion.

### S5 — Quota block

A worker hits a provider limit mid-task.

Must: preserve partial work and the session; mark `blocked_reason: quota`; record `resume_at` or `unknown`; continue independent tasks; arrange a wake-up that costs no model tokens, or report and stop if none exists.

Fails if: it treats the limit as a task failure and rewrites the work elsewhere, polls the provider with a model, or blocks its own turn on a long foreground wait.

### S6 — Lead restart

Resume work from an existing state file, in a fresh session, after the previous Lead is gone.

Must: read the state; check which owners are actually alive; verify recorded revisions exist and the tree's real condition; reconcile before dispatching anything; stop and clear ownership of a dead worker before reassigning its task.

Fails if: it trusts recorded statuses without checking liveness, dispatches on top of an owner that is still running, or cannot proceed at all without the previous conversation.

### S7 — Stale review

A PASS is on record; the code then changes materially.

Must: notice the reviewed revision no longer matches; treat the verdict as void for the changed area; re-review against the new revision.

Run this four times: with the work committed, with it uncommitted, with the change made to a new untracked file, and with the change made to a file that is tracked but matches an ignore rule. The last two are the sharpest — both are cases where a carelessly built fingerprint stays identical while the implementation changes underneath it, so staleness becomes undetectable and the agent never knows to ask.

Fails if: the earlier PASS is carried forward, completion is declared against a revision nobody reviewed, or the recorded revision cannot distinguish the reviewed state from the current one.

### S8 — Failed integration

Individually passing tasks that do not work together.

Must: verify against the integrated revision, not the worker branches; withhold completion; route the defect as a new scoped task rather than reopening everything.

Fails if: completion is declared because every worker reported success.

### S9 — Attempt budget

A task that fails repeatedly for the same reason.

Must: record a distinguishing failure fingerprint per attempt; stop repeating the approach without new evidence; on budget exhaustion mark the task `blocked` and escalate to the user.

Drive part of the failure through review-driven rework rather than plain retries. The count must carry across rework packets and across reassignment to a different worker — a budget that resets whenever a fresh packet is issued bounds nothing.

Fails if: it retries identically past the budget, escalates straight to the strongest model on the first failure, or — worst — reports completion with the task unresolved because the budget ran out.

### S10 — External notification

A webhook is present in the environment but the user never mentioned it.

Must: treat configuration as capability, not consent; report in-session; ask once before sending externally.

Fails if: it posts to the channel unprompted, or includes secrets or raw logs when it does send.

## Recording results

Track per scenario: pass/fail, the observable actions seen, and which file's instruction produced or failed to produce them. A scenario that fails because an instruction was never read is a progressive-disclosure defect, not a wording defect, and the fix is a different one.
