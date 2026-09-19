# Quota Management

Read this on any quota or rate-limit signal, and when remaining quota materially affects who gets a task.

## Principles

- Quota exhaustion is a resource state, not a task failure.
- Waiting must not consume model tokens.
- A wait is only safe if something will reliably wake the work up.
- Preserve sessions and partial work before anything else.
- Fail over only when its cost is justified.

## On a quota signal

1. Capture any unfinished result that would otherwise be lost.
2. Preserve the worker's session identifier and current state.
3. Set the task `blocked` with `blocked_reason: quota` (`references/execution-state.md`).
4. Determine the reset time with the cheapest non-model mechanism available — the provider's own error message, a usage CLI, or a status API.
5. Record `resume_at`, and arrange a wake-up (below).
6. Continue independent tasks meanwhile.
7. After reset, resume the existing worker when practical, and verify it actually resumed rather than assuming it did.

Do not poll a provider's quota by invoking a model. A status check that costs tokens defeats the purpose of waiting.

## Unknown reset time

Providers do not always tell you. When `resume_at` cannot be determined:

- do not guess a time and silently sleep against it;
- record `resume_at: unknown`;
- continue all independent work to completion;
- if the blocked task is on the critical path, surface it to the user with what you know, and let them decide between waiting, failing over, and narrowing scope.

An unknown reset that blocks everything is a user decision, not something to spin on.

## Wake-up mechanisms

Choose by capability, in descending order of reliability:

1. **Orchestrator timer or scheduler** — the tool resumes the work without a model in the loop.
2. **Host scheduling primitive** — a cron-like or delayed-run facility that re-invokes you at `resume_at`.
3. **Detached background process** — a process that sleeps and then signals or writes a marker the next cycle will observe.
4. **None available** — report `resume_at` and the preserved state to the user and stop. Stopping with a clear resume point is a legitimate outcome.

Do not block your own turn on a long foreground wait. Some harnesses forbid it outright, and where they do not, it burns a live session doing nothing and leaves the work unresumable if the session ends. A short bounded wait for a reset that is seconds away is fine; an hour is not.

Backgrounding a process is not by itself a wake-up. Unless something observes it, the work will still be sitting there when the reset passes.

## Failover decision

Move the task to another worker or provider when:

- the reset delay violates the user's timeline;
- the blocked worker holds little valuable context;
- another worker can continue from a small handoff;
- the blocked provider has repeated availability problems.

Prefer waiting when:

- the reset is soon;
- the worker holds expensive context;
- the task is already far along;
- reassignment would duplicate substantial analysis.

Weigh expected wait against context reconstruction cost. A cheap provider that has to re-derive the whole repository is not cheap.

Failover is a reassignment: stop the blocked worker and clear its ownership before dispatching elsewhere, or two agents will eventually write the same files.

## Usage checks

Check quota when routing substantial work and quota is likely to matter, when a provider reports a limit, when choosing between waiting and failover, and when a recorded reset time arrives.

Not on every management cycle. Resource monitoring is a supporting signal, not the workflow.
