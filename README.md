# Agent Team Skills

Reusable, tool-agnostic skills for coordinating AI software development teams.

The repository defines roles and decision policies, not a dependency on a particular orchestrator, model provider, or coding agent. The same skills can be installed for Claude Code, Codex, GitHub Copilot, and other compatible agents so roles can move between providers as quota and task needs change.

## Skills

- **team-lead** — owns a development request from planning through delegation, recovery, review, and verified completion.
- **follow-through (완수)** — carries an authorized multi-step task through verified completion with one active executor, preserving progress across commits, interruptions, quota waits, and sequential provider handoffs.
- **design** — turns requirements and existing-system context into an implementation-ready design, decomposed into tasks with bounded writable scopes.
- **worker** — executes a single delegated task inside an assigned scope and returns a verifiable result.
- **review** — independently reviews completed work for correctness, regressions, requirement compliance, and meaningful risk, and issues a verdict bound to the revision reviewed.

## Principles

- **Role is dynamic; capability is portable.** Claude, Codex, Copilot, or another agent may be Lead, Worker, Designer, or Reviewer.
- **Delegate execution; retain ownership.** A Lead delegates work but remains responsible for the outcome.
- **Use the minimum intelligence necessary.** Match provider, model, and reasoning effort to task difficulty and risk.
- **Independent review.** Meaningful changes should be reviewed by an agent that did not implement them.
- **Progressive disclosure.** Core skill files stay focused; detailed policies live in references and are read only when relevant.
- **Tool agnostic.** Herdr, Orca, AUM, webhooks, and similar tools are optional capabilities, not role dependencies.

## Installation

Using the Agent Skills CLI, install the skills for the agents you actually use. For example:

```bash
npx skills add kingmoeng/agent-team-skills --list
npx skills add kingmoeng/agent-team-skills -g -a claude-code -a codex -a github-copilot --skill '*'
```

Agent identifiers supported by your installed CLI version may differ; use its list/help command when necessary.

## Usage

Skills are intended to be selected automatically from their descriptions. You normally should not need to name them explicitly.

Examples:

```text
Implement this feature, including tests, and make sure the finished result is reviewed.

Investigate the transcription gaps, decide on an approach, implement the fix, and verify it.

Review the changes against the original requirement and identify anything that must be fixed.
```

For important work where you want deterministic role selection, explicitly ask the agent to act as the team lead, designer, or reviewer.

Use `follow-through` for a plan one executor can finish sequentially, including work that spans several commits or sessions:

```text
Carry out the approved plan through final verification without asking at every step.
Use Codex or Claude Code as capacity allows; preserve progress and resume after a usage reset if needed.
```

Use `team-lead` when execution needs delegation, parallel work, or coordinated integration. A quota wait or several commits alone does not require a team.

`follow-through` includes an optional [local runner](skills/follow-through/references/runtime.md) for Codex and Claude Code, with macOS launchd resumption and a lock for managed writers. Its policy remains usable without that runner. Sequential handoff requires the outgoing executor to stop writing; independently opened interactive agents are outside the runner's lock and must be stopped before handoff. Usage observations guide routing when available; missing information remains unknown. Without a needed capability, preserve progress and report the manual resume point rather than claiming an automatic restart. Installing the skill does not schedule any task.

## Tooling

A Team Lead may use whatever orchestration and observability capabilities are available in its environment. Examples include an agent orchestrator for spawning workers, a low-cost CLI for quota/usage inspection, and a Discord webhook for progress notifications. These are optional integrations. The core skills must remain useful when none of them are available.

## Evaluation

`evals/scenarios.md` defines the quality gate: trigger-selection cases plus execution scenarios (write conflicts, silent workers, quota blocks, Lead restart, stale review, failed integration) scored on observable agent behavior rather than on whether the skills read well.

The optional runner has executable regression tests:

```bash
python3 -m unittest discover -s tests -v
```

## License

MIT.
