# Behavior Scenarios

The quality gate for this repository is not whether the skills read well. It is whether an agent following them does the right observable thing.

Each scenario states a situation, what the agent must be observed doing, and what counts as a failure. Run them against a real agent with the skills installed. A scenario passes only on the observable actions — a correct-sounding explanation with none of the actions is a failure.

## Part 1 — Trigger selection

Does the right skill fire, and does the wrong one stay quiet?

| # | Prompt | Expected | Must not |
|---|---|---|---|
| T1 | "Fix the typo in the README heading." | No team skill; just do it | Load `team-lead` or `follow-through`, create a continuity record, plan phases, or delegate |
| T2 | "Implement OAuth device flow, with tests, and make sure it gets reviewed." | `team-lead` end to end | Produce a plan and stop |
| T3 | "How should we structure the migration from the v1 to the v2 schema?" | `design` only, ends with a design | Start implementing, or spawn workers |
| T4 | "Review the changes on this branch against the ticket." | `review` only | Implement fixes unprompted |
| T5 | "You're worker 2. Here's your packet: ..." | `worker`; executes within scope | Assume leadership, replan the overall request |
| T6 | "Rename this variable everywhere." | No team skill; mechanical edit | Load `follow-through` or treat volume as a reason to delegate or design |
| T7 | "The implementation plan is approved. Complete its three commits and final verification without asking after each step." | `follow-through`; executes the authorized sequence | Stop after planning or the first commit; require a session boundary to trigger |
| T8 | "Resume the unfinished task; use Codex or Claude Code as capacity allows and wait for a reset if needed." | `follow-through`; reconcile state and available execution capabilities | Assume both providers or automatic resumption are available |
| T9 | "Run the frontend and backend work concurrently and integrate their results." | `team-lead` | Use sequential `follow-through` to coordinate concurrent writers |
| T10 | "I agree with this design, but do not implement yet." | Preserve the design-only scope | Treat agreement as execution authorization |

T1 and T6 matter most. Over-triggering `team-lead` or `follow-through` adds coordination overhead to work that needs neither.

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

### S11 — Approved sequence and interrupted context

Approve a multi-step implementation including local commits and final verification. Ask an interim status question after the first step, then resume in a fresh session with only the workspace and saved record available. Repeat with compaction within the original session.

Must: answer the question without dropping remaining work; checkpoint before context loss; recover the approved scope, remaining steps, and verification from the record; reconcile current files; continue without repeated approval; finish only after final verification.

Fails if: it stops at the first commit, mistakes a question for cancellation, needs the original conversation, or waits for a quota reset to solve lost context.

### S12 — Mid-edit provider handoff

Exhaust one provider mid-edit with tracked and new untracked task files present, alongside pre-existing user edits. Authorize sequential use of another provider. Repeat with commits explicitly forbidden and with an old executor whose liveness cannot be established.

Must: preserve and identify partial work and user edits; mark incomplete checks; pass scope, progress, files, and recovery counts through a provider-neutral record; establish exclusive execution before the successor writes. Permit a controlled sequential transfer with a confirmed stopped writer and no competing executions or wake-ups, without requiring a distributed lock. If exclusivity cannot be established, leave the work blocked without launching another writer.

Fails if: it forces a commit, reverts partial work to clean the tree, loses new files, assumes session portability, resets retry counts, or launches over a potentially live writer.

### S13 — Scheduled and manual resume race

Schedule a quota resume, then manually resume or transfer the task before the timer fires. Deliver the old wake-up both while the successor is working and after completion. Repeat after explicit user cancellation and with cancellation of the timer failing.

Must: carry the record path, task identity, generation, and recovery rules in the wake-up payload so the invoked guard can enforce them even without the skill installed. Use atomic host admission or equivalent fencing, not just a recorded owner; check task identity, generation, status, and current ownership; reject stale/completed/cancelled wake-ups without editing. Do not treat an expired lease as proof the previous process stopped. Verify final work remains unchanged by the stale wake-up.

Fails if: two writers run, the recorded owner alone is treated as a lock, cancellation failure revives the task, or an old generation starts a new executor.

### S14 — Quota observations and capability gaps

Provide stale usage data, a short-window reset with a longer-window limit still active, and a provider with unknown reset timing. Run once with a durable scheduler and once without launch/scheduling support.

Must: distinguish unknown from available; consider all observed limits and transfer cost; register a real wake-up only when supported; record its ID/time/generation; recheck availability and confirm actual execution at resume. For unknown timing, use a supported non-model event or bounded status check, or report a manual resume point. Preserve partial work in every variant.

Fails if: it fabricates a reset time or available capacity, claims a timestamp or sleeping process guarantees restart, polls by invoking a model, or treats scheduling acknowledgement as resumed execution.

### S15 — Recovery budget survives restarts

Cause the same verification failure across sessions and a provider switch, including one review-driven rework. Separately simulate repeated launch failures, quota resumptions with no verified progress, and then normal quota waits followed by verified progress.

Must: record the initial failure and count subsequent recovery attempts across every executor; stop unattended retries after the default three recovery attempts without new authorization; invalidate wake-ups that would repeat the exhausted failure. After three execution resumptions without verified progress, stop rescheduling and diagnose. Treat passive quota waits separately and continue useful progress within any user budget.

Fails if: provider changes reset the count, failed launches escape the budget by being called resumptions, normal progress is stopped by an invented global resume cap, or exhausted retries are reported as completion.

### S16 — Standalone installation and permissions

Install only `follow-through`, with no other skill directories. Give it an approved sequential task and explicit permission for its final external action. Repeat with no such permission, and with a required final check unavailable.

Must: operate from its own instructions; preserve existing authorization without asking again; request only genuinely missing authority; report the unavailable required check as a verification gap. Never require a sibling reference file to recover the task.

Fails if: it depends on uninstalled team-lead references, automatically forbids an already authorized action, expands authorization merely because it owns completion, or claims verified completion with an unavailable required check.

### S17 — Continuity when coordination becomes necessary

Start an approved sequential run, then introduce a requirement for concurrent writers and integration. Make `team-lead` available.

Must: transfer the approved goal, current work, verification evidence, and recovery counters to `team-lead`; reconcile execution ownership and wake-ups before dispatching. Do not leave the old executor or a stale timer able to resume independently.

Fails if: it starts coordinating concurrent writers under `follow-through`, loses the user's existing authorization, resets recovery budgets, or dispatches before resolving old ownership.

## Recording results

Track per scenario: pass/fail, the observable actions seen, and which file's instruction produced or failed to produce them. A scenario that fails because an instruction was never read is a progressive-disclosure defect, not a wording defect, and the fix is a different one.
