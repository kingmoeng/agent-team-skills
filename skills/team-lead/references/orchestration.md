# Orchestration

Read this in phase 2, before planning any delegation.

The core skills depend on a small set of lifecycle operations, not on any particular tool. This reference defines those operations, how to discover which of them you actually have, and one worked mapping.

## Capability discovery

Probe once, at the start. Do not re-probe on every management cycle.

Check, in order:

1. **Native subagents** — does the host expose a tool that spawns an agent in-process? If so you can dispatch without touching the terminal.
2. **External orchestrator** — is there a multiplexer that hosts agents in separate sessions? Detect it from its environment marker and its CLI being on `PATH` (for Herdr: `test "${HERDR_ENV:-}" = 1` and `command -v herdr`).
3. **Neither** — you are in serial mode.

Also note which of these the host already provides, so you do not rebuild them:

- a diff/code review capability;
- a scheduler or timer that runs without model tokens;
- git worktree support for isolating workspaces.

Record the selected mode and everything you found missing in the execution state. The limitations you record are what an honest final report is built from.

## Lifecycle operations

| Operation | Meaning |
|---|---|
| `spawn` | create a worker and confirm it is ready for input |
| `dispatch` | deliver a task packet and confirm submission |
| `wait` | block on a state change without polling a model |
| `read` | retrieve a worker's output or final report |
| `interrupt` | stop a worker's current turn without killing it |
| `stop` | terminate a worker and revoke its ownership |

If an operation is unavailable, the workflow that depends on it is unavailable. Say so rather than simulating it — for example, without `wait` you cannot monitor cheaply, so prefer fewer, larger tasks.

## Mode: native subagents

Dispatch the packet as the subagent's prompt. Cheapest option when available.

Caveat that matters: in-process subagents usually share **your** working tree. They isolate context, not files. Non-intersecting writable scopes are still mandatory.

## Mode: external agents (Herdr example)

This mapping is an example of binding the operations above to a real tool, not a dependency of the skill.

```bash
# discover
test "${HERDR_ENV:-}" = 1 && herdr agent list

# create a location, then spawn
herdr pane split --current --direction down --cwd "$PWD" --no-focus   # -> .result.pane.pane_id
herdr agent start backend --kind codex --pane <pane-id> -- <agent-args>

# dispatch and wait
herdr agent prompt backend "<task packet>" --wait --timeout 600000

# inspect
herdr agent get backend
herdr agent read backend --source recent-unwrapped --lines 200

# interrupt / wait for a specific state
herdr agent send-keys backend esc
herdr agent wait backend --until blocked --timeout 600000
```

Caveats:

- Panes isolate **terminals, not working directories**. Two agents in two panes with the same `--cwd` will overwrite each other. Use a worktree per parallel task, or non-intersecting writable scopes.
- `blocked` means the agent is sitting on an approval or question prompt. Inspect it and ask the user before answering on their behalf.
- `unknown` means the tool cannot classify the agent. It is not evidence of completion.
- A `timeout` on dispatch does not prove the packet was never delivered. Read the worker before resending.
- Do not close panes, tabs, or workspaces you did not create.

## Mode: serial

No orchestration. You execute every phase yourself.

This is a legitimate mode, not a degraded one — but it changes what you may claim:

- Run design and review as **distinct phases** with explicit inputs, not as a single pass of reasoning.
- A review you perform of your own implementation is **self-review**. Re-reading your work does not create independence; only a reviewer that did not write the change can. Record the result as self-review in the state and say so in the final report.
- If the host provides a diff review capability, use it. A separate tool examining the diff is weaker than an independent agent but stronger than your own second look, and it costs nothing to run.
- Prefer smaller, sequentially verified increments, since you have no second opinion to catch a wrong direction early.

## Reusing host capabilities

Where the host already provides a capability, use it as an input rather than reimplementing it:

- a diff review tool feeds the `review` skill's evidence; it does not replace requirement-compliance review;
- a host scheduler satisfies the quota wake-up requirement;
- host worktree support satisfies workspace isolation.

Describe these by capability, not by product name, so the skill survives the tool being different tomorrow.
