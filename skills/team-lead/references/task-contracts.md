# Task Contracts

Read this before the first dispatch of a delegated task, and when a returned result is ambiguous.

Multi-agent work fails at handoffs, not at philosophy. These are the two interfaces that must be explicit: what the Lead sends, and what the worker returns.

## Task packet

Send the minimum sufficient context. Do not forward the whole user conversation; do not omit the fields below.

```text
Task: <short-id>
Objective: <the outcome, in one or two sentences>

Context: <only what is needed to act — relevant components, prior decisions,
          conventions to follow. Not the conversation history.>

Writable scope: <paths, directories, or components you may modify>
Out of scope: <adjacent things you must not touch, when it is not obvious>

Workspace: <working tree / worktree path>
Base revision: <commit sha — not a branch name, which moves>

Constraints: <design decisions already made, compatibility requirements,
              things that must not change>
Dependencies: <tasks or artifacts this needs; state whether they are ready>

Completion criteria: <what makes this done — observable, not "looks good">
Verification: <the commands to run, or what to demonstrate>

Execution rules:
  - Write only inside the writable scope. Report anything outside it; do not fix it.
  - Do not commit, merge, rebase, push, or switch branches unless told to above.
  - Do not spawn your own workers.
  - Run the verification above. State plainly whatever you could not run.
  - If the task cannot be done without leaving scope, stop and report that.

Report: <the result shape you expect; by default the completion report below>
```

### Rules

- **Do not assume the worker can load the `worker` skill.** A different provider's session may not have it installed, and you will not find out until the rules have already been ignored. Either confirm the skill is loadable and reference it, or keep the execution rules in the packet verbatim. An unstated rule is not a rule.
- Every packet names a writable scope. A task whose scope you cannot bound is a task you should not dispatch.
- Two packets dispatched in parallel must have non-intersecting writable scopes in the same workspace. Otherwise serialize them or give each its own worktree. A worktree resolves a write collision; it does not resolve a dependency — a task that needs another's output waits for that output regardless of where it runs.
- Completion criteria are observable. "Implement the parser" is an objective; "`cargo test parser::` passes and malformed input returns `ParseError` rather than panicking" is a criterion.
- State dependencies even when satisfied, so the worker knows what it may rely on.
- Authorize redelegation explicitly, or the worker will not do it.
- Persist the packet you actually sent and record its path in the execution state. A task whose packet exists only in your context cannot be recovered by a replacement Lead.

## Completion report

What the worker returns. The `worker` skill produces this by default.

```text
Task: <id>
Status: complete | partial | blocked
Revision: <commit sha, or a fingerprint of the uncommitted work>

Changed:
- <path> — <what changed and why>

Verification:
- <command> — <pass/fail, key output>
- Not run: <what, and why>

Deviations: <done differently from the packet, and why. "None.">
Out of scope: <defects or risks noticed but not touched. "None.">
Uncertain: <what could not be confirmed. "None.">
```

### Reading a report

- `Not run` and `Uncertain` are the fields that matter. A report with both empty and a large diff deserves more scrutiny, not less.
- `Deviations` is where scope drift surfaces. Check it against the writable scope before integrating.
- `Out of scope` findings belong in your backlog, not in a silent follow-up task the user never agreed to.
- A bare "uncommitted in the workspace" is not a revision. Require a commit, or a fingerprint that covers new files as well as modified ones — see Revision identity in `execution-state.md`.
- A report is a claim about work, not proof of it. Verification happens against the integrated revision.

## Review handoff

When routing a change to review, send:

- the original requirement and completion criteria;
- relevant design decisions;
- the **integrated revision** under review, not individual worker branches;
- the diff and the tests;
- known verification gaps, taken from the reports' `Not run` fields.

Route findings back by finding ID, using the packet fields above. Scope a rework packet to the smallest change that corrects the finding and includes appropriate regression verification. The finding's location is evidence of where the defect surfaced, not a boundary on where the fix belongs — a defect reported in a caller often has to be corrected in the callee.

Scope the packet to include regression coverage for the finding: an automated test where one applies, otherwise a concrete recorded check and its limitations. Some corrections, such as documentation fixes, need no test; do not manufacture one to satisfy the rule.

## Design handoff

A design that produces implementation tasks should emit them in packet shape, leaving `Workspace` and `Base revision` for the Lead to fill at dispatch time. A design whose tasks lack writable scopes has not finished decomposing the work.
