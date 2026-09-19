# Quota Management

Use this reference when an agent/provider hits a usage limit or when quota materially affects worker selection.

## Principles

- Quota exhaustion is a resource state, not task failure.
- Waiting should consume no LLM tokens.
- Preserve useful sessions and work products.
- Avoid repeated model-mediated polling.
- Fail over only when its cost is justified.

## On quota exhaustion

1. Mark the task `quota_blocked`.
2. Preserve the worker/session identifier and current work state.
3. Capture any unfinished result that would otherwise be lost.
4. Determine the reset time with the cheapest available mechanism, preferably a local CLI or provider status API.
5. Record `resume_at`.
6. Continue independent tasks.
7. Arrange a non-LLM wake/resume mechanism if the environment supports it.
8. After reset, resume the existing worker when practical.
9. Verify that work actually resumed.

Examples of non-LLM waiting mechanisms include an orchestrator timer, scheduler, `at`, `systemd-run`, or a simple process sleep where appropriate.

## Failover decision

Consider another worker/provider when:

- the reset delay violates the user's timeline;
- the blocked worker has little valuable context;
- another worker can continue with a small handoff;
- the blocked provider has repeated availability problems.

Prefer waiting when:

- reset is soon;
- the worker holds expensive context;
- the task is already far along;
- reassignment would duplicate substantial analysis.

## Persistent state example

```yaml
goal: improve timeline UI
tasks:
  backend:
    owner: worker-1
    status: quota_blocked
    resume_at: 2026-09-19T17:33:00+09:00
  frontend:
    owner: worker-2
    status: working
  integration-test:
    status: waiting
    depends_on:
      - backend
      - frontend
review:
  status: pending
```

The exact storage format is environment-specific. Keep it simple and machine-readable when possible.

## Usage checks

Do not query quota on every management cycle. Check when:

- initially routing substantial work and quota is likely to matter;
- a provider reports a limit;
- choosing between waiting and failover;
- a scheduled reset time has arrived.

AUM or another usage CLI can be used when available, but no particular quota tool is required by this skill.
