# Execution State

Read this before the first dispatch, and again when resuming work you did not start.

**The Lead may restart; the work state must survive.** A replacement Lead has none of your conversation. Everything it needs to continue safely has to be written down.

## When to write

- a checkpoint before the first dispatch;
- on every task state transition;
- when ownership moves, a revision is produced, or review reaches a verdict.

Not on every tool call. The state is a recovery artifact, not a log.

## Where

Default to a small directory in the repository working area, such as `.agent-team/`, holding `state.yaml` plus the artifacts it points at. Keep the state file machine-readable and small enough to read in full; put anything long in a file beside it and record the path.

## What must exist at each checkpoint

The state is only useful if a stranger can act on it. Before the first dispatch, the requirement and any design must already be persisted as files — not held in your context. At every later checkpoint, each task must point at the packet that was actually sent, and every verdict must point at the report that produced it.

A task with an owner but no packet path is unrecoverable: the next Lead can find the worker but cannot tell what it was asked to do.

## Schema

```yaml
goal: <the user's request in one line>
mode: native | external | serial
limitations:
  - review is self-review; no independent reviewer available
requirement: .agent-team/requirement.md    # full requirement + completion criteria
design: .agent-team/design.md              # or null
integration:
  owner: lead
  workspace: /path/to/main/worktree
  integrated_revision: null

tasks:
  backend-api:
    status: working            # see states below
    owner: worker-1            # session/pane/agent id, or "lead"
    packet: .agent-team/packets/backend-api.md   # what was actually dispatched
    criteria: <one-line acceptance criterion, or a path>
    workspace: /path/to/wt-backend
    base_revision: a1b2c3d
    writable_scope:
      - src/api/
    depends_on: []
    attempt_count: 1
    attempt_limit: 3
    last_failure: null         # short fingerprint, not a transcript
    result_revision: null      # immutable — see Revision identity
    evidence: []               # paths to reports, logs, diffs
    blocked_reason: null
    resume_at: null
    next_action: await result

review:
  status: pending              # pending | in_progress | pass | changes_required | insufficient_evidence
  revision: null               # the revision actually reviewed
  report: null                 # path to the review output
  independent: false
  open_findings: []            # ids only; detail lives in the review report
```

Record IDs and paths, not prose. If a field would need a paragraph, write the artifact to a file and record its path.

## Revision identity

A recorded revision must be immutable, or staleness cannot be detected.

Prefer a commit sha on a task branch. A branch name and a label like `uncommitted in <workspace>` both keep pointing at whatever the tree becomes next, so a verdict bound to one of them silently survives the change that should have invalidated it.

When committing is not possible, record a fingerprint that changes when **any** of the work changes. A snapshot of tracked modifications is not enough: work that lives entirely in new files would not appear in it, and the fingerprint would stay identical while the implementation changed underneath it.

Build the fingerprint in a throwaway index, which produces a real immutable tree object covering modifications, additions and deletions without touching the working tree or the real index:

```bash
idx=$(mktemp -u)
GIT_INDEX_FILE=$idx git -C <workspace> read-tree HEAD                       # seed: see below
GIT_INDEX_FILE=$idx git -C <workspace> add -A -- . ':(exclude).agent-team'
GIT_INDEX_FILE=$idx git -C <workspace> add -Af -- <ignored deliverables>    # only if any exist
GIT_INDEX_FILE=$idx git -C <workspace> write-tree
rm -f "$idx"
```

Seeding from `HEAD` is not optional. Ignore rules apply to files that are absent from the index, so an index that starts empty silently drops every tracked-but-ignored file — and a change to one of those then leaves the fingerprint identical. Seeding puts them in the index first, where ignore rules no longer reach them.

Exclude the coordination artifacts themselves; the state file changes constantly and is not part of what is under review.

Anything still outside the fingerprint is outside the verdict. If part of the deliverable is ignored and cannot be force-added, do not record a revision as if it covered the work: state the gap, and have the reviewer return INSUFFICIENT EVIDENCE rather than a PASS that silently excludes the changing part.

Recompute before integration, before review, before declaring completion, and when resuming. A changed fingerprint voids any verdict bound to the old one.

## Task states

```text
pending -> dispatched -> working -> returned -> review -> verified
                      \-> blocked -> (dispatched | abandoned)
                                review -> rework -> dispatched
```

- `blocked` carries a `blocked_reason`: `needs_input`, `quota`, `dependency`, `conflict`, `failed`.
- `returned` means a worker produced a report. It is not `verified`.
- `verified` requires verification against the integrated revision, not the worker's branch.
- `abandoned` is terminal and must record why.

Silence is not a state. If a worker has not transitioned and you do not know why, diagnose before you act: still computing, waiting on an approval prompt, quota-blocked, crashed, or finished without reporting. Each has a different correct response.

## Ownership

One owner per writable scope at a time. The owner is the only agent permitted to write those paths.

Before reassigning a task:

1. stop the previous owner and confirm it has stopped;
2. clear `owner` in the state;
3. capture whatever partial work exists, and record its revision or path;
4. only then dispatch to a new owner.

A replaced worker that wakes up and keeps writing will corrupt the result, and the corruption will look like a mysterious integration failure. This ordering is what prevents it.

## Attempts

`attempt_limit` is the budget, default three. `attempt_count` is what has been spent.

Increment `attempt_count` on every dispatch of the task after the first, including retries, reassignment to a different worker, and review-driven rework. The count belongs to the task, not to the packet or the worker — otherwise issuing a fresh packet resets the budget and the loop the budget exists to stop runs forever.

Raise `attempt_limit` only as a deliberate, recorded decision, never as a side effect of rewriting the task.

`last_failure` is a short fingerprint — the failing command and the distinguishing error, not a transcript — so you can tell a repeat from something new. Do not retry an approach without new evidence.

When the budget is exhausted, the task becomes `blocked` and escalates to the user. Exhausting a budget bounds effort; it never authorizes completing the request with the task unresolved.

## Resuming

When you take over work already in progress, reconcile before you act. The state file records intent; the machine records reality.

1. Read the state, and the requirement and packets it points at.
2. Check which recorded owners are actually alive. A dead owner's task is not `working`.
3. Check the repository: do the recorded revisions exist, is the tree dirty, are there unmerged worktrees?
4. Reconcile differences into the state before dispatching anything new.
5. Recompute the integrated revision. If `review.revision` no longer matches it, the review is stale and its verdict does not carry over.

Trust the state's goal and decisions. Verify its liveness and revisions.
