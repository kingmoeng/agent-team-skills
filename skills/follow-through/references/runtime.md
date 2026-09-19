# Optional local execution

Read this when using the bundled scripts, rather than a host's own execution and scheduling facilities. They require Python 3.9+ and a POSIX host. Scheduled cold-start resumption uses macOS launchd; other hosts can run the same foreground command through their own scheduler.

The runner is for a concrete, authorized task. Installing this skill never starts work or schedules a task. All writers managed by this runner use one lock per canonical workspace. Independently opened Codex/Claude sessions do **not** participate: stop those writers before transferring a workspace to the runner. Do not claim that a cooperative lock fences unrelated interactive sessions.

## Prepare and run

Resolve `scripts/runtime.py` relative to this installed skill, and use an absolute path in durable automation. Write the approved goal, scope, plan, completion criteria, and verification into a task file. Preserve existing authorization, and explicitly include any authorized commit/push/deployment steps. The runtime's state and locks are controller-owned; do not ask the executor to edit them.

```bash
python3 /absolute/path/follow-through/scripts/runtime.py init \
  --state /path/to/workspace/.agent-team/run.json \
  --workspace /path/to/workspace \
  --task-file /path/to/workspace/.agent-team/task.md \
  --providers codex claude \
  --claude-usage /Users/you/.local/state/agent-team/claude-usage.json

python3 /absolute/path/follow-through/scripts/runtime.py run \
  --state /path/to/workspace/.agent-team/run.json
```

Use only providers the user authorized. The existing CLI login and configuration are reused; the runner does not buy capacity or silently fall back to an API key. No approval/sandbox bypass flags are added. Codex uses `workspace-write`; Claude allows edits using `acceptEdits` and retains configured tool rules. Denied tool use is reported as blocked. Approve or configure any additional required operations through the provider's normal permission system, not by bypassing it.

The executor receives the task, skill, saved completed steps, and a structured result contract. Report `complete` only after every required step and check, with evidence. Report a verified increment as `continue`, missing decisions/permissions as `blocked`, and an observed limit as `quota`. Use stable completed-step IDs so repeated summaries do not count as new progress. Evidence is agent-reported; the runner validates its structure, not the semantic correctness of the implementation or tests.

## Usage observations and provider choice

Codex's adapter initializes `codex app-server` and calls `account/rateLimits/read` without starting a model turn. It reads both applicable limit windows. Authentication failures or absent fields mean unknown, not spare capacity.

Claude usage comes from its documented status-line JSON. The optional wrapper caches only quota windows and observation time; it forwards the original JSON unchanged to the previous status-line command and preserves its output. It does not scrape credentials, logs, or private endpoints. Data is available only when the installed Claude version/account supplies it and a status-line update has occurred; non-interactive runs may not emit these updates. Stale observations are not current capacity, and a passed reset is only a reason to recheck.

To opt in after installation, run the following with your actual paths. Existing settings and the previous command are backed up; reinstalling the same wrapper does not nest wrappers. If the user changed the status line later, inspect the conflict instead of overwriting it.

```bash
python3 /absolute/path/follow-through/scripts/providers.py install-claude-statusline \
  --settings /Users/you/.claude/settings.json \
  --cache /Users/you/.local/state/agent-team/claude-usage.json \
  --previous /Users/you/.local/state/agent-team/claude-statusline-previous.json
```

To roll back the wrapper, restore only the `statusLine` value from the recorded previous-command JSON (remove it if the original was absent), preserving other current settings. The byte-exact settings backup is for recovery, not for overwriting unrelated later changes.

Provider availability and current-session context guide sequential selection. A provider with unknown usage can be tried once for real work; repeated limit errors are not a polling strategy. If no usable provider or reliable reset time is known, save a manual resume point. Existing sessions are resumed by exact ID, never `--last`.

## Schedule, inspect, and cancel

On a known quota wait, the runner can register a per-task LaunchAgent. `run --no-schedule` instead records the wait for manual resumption. Scheduling is also available explicitly:

```bash
python3 /absolute/path/follow-through/scripts/runtime.py schedule \
  --state /path/to/workspace/.agent-team/run.json --at 2026-09-20T03:00:00Z
python3 /absolute/path/follow-through/scripts/runtime.py status \
  --state /path/to/workspace/.agent-team/run.json
python3 /absolute/path/follow-through/scripts/runtime.py cancel \
  --state /path/to/workspace/.agent-team/run.json
```

The launchd job carries absolute interpreter/script/state paths, the task generation, and the runtime PATH. Its host process waits without model calls and checks the due time and cancellation before launching. It selects the GUI user domain when available, otherwise the background user domain. Stored LaunchAgents restart on a normal login; a headless host may need to bootstrap the persisted plist again after reboot. The Mac must be running and the user's launchd session available. Sleep delays execution until wake. Completion/cancellation invalidates the generation and removes the task's persisted launch file; stale invocations cannot edit the workspace. Registration and actual executor start are recorded separately.

Cancel through this CLI while a managed executor is active; the owning runner stops its isolated child process group and reaps the child before releasing the workspace lock. Controller locks live under `~/.local/state/agent-team/locks`, outside repositories so a workspace cleanup cannot replace their inodes. Do not delete those lock files. If the runner crashes but its child survives, the inherited lock prevents a new managed writer; inspect and stop the surviving session before recovery. Never kill a process merely because a stale record contains its PID. Helpers in the managed process group are stopped when the CLI finishes; independently detached services remain outside the runner's lifecycle.

After resolving a blocked task's missing decision, permission, or launch failure, explicitly use `run --state ... --retry-blocked`. This retains its progress and recovery counters. Timers cannot retry blocked tasks on their own. A cancelled task remains cancelled; create a new explicitly authorized task to restart it.

Treat the runner state, task file, and any referenced artifacts as local task data. Keep them out of published commits unless explicitly intended. Logs may contain task content. Quota and process failures preserve partial work; neither clean the tree nor create an unauthorized commit for recovery.
