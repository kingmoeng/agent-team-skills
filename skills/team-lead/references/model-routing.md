# Model and Worker Routing

Read this before choosing among providers, models, or reasoning-effort levels — not on every dispatch.

## Objective

Minimize total cost and delay while keeping a high probability of correct completion.

Do not optimize token cost in isolation. A cheap worker that fails three times, plus the review cycles it triggers, costs more than a capable worker used once. The unit to minimize is the cost of reaching a verified result.

## Discover what you can actually select

Routing advice is worthless if you cannot name a real model or set a real effort level. Before routing, establish for each agent you can dispatch to:

- which models it accepts, and the exact identifiers;
- whether reasoning effort is separately selectable, and how;
- how to pass both at spawn time.

Find this from the agent's own CLI help, its configuration file, or its model-listing command — not from memory, which goes stale as providers rename and retire models. Record what you learned in the execution state so you do not re-derive it per task.

An illustration, not a dependency: a CLI may take a model flag and a config override at spawn (`--model <id>`, `-c model_reasoning_effort=medium`), and expose the current defaults in a user config file. Other agents differ. Check.

## Inputs to the decision

Difficulty, ambiguity, novelty, blast radius, failure cost, how mechanical the work is, whether it needs repository-wide reasoning, provider-specific strengths and tool access, context already present in an existing session, remaining quota and expected reset, and handoff reconstruction cost.

## Default tiers

Start with the least expensive combination reasonably likely to succeed:

| Work | Starting point |
|---|---|
| mechanical or fully specified | economical model, low effort |
| ordinary implementation | economical capable model, low to medium effort |
| routine debugging | medium effort |
| hard debugging, ambiguous integration | stronger model and/or high effort |
| architecture, decomposition, high-impact decisions | capable model, usually high effort |
| review | capability matched to the risk being reviewed, not to the diff size |

These are starting points, not commitments. The escalation ladder is what handles a bad guess.

## Escalation ladder

Escalate only on evidence, in this order:

1. improve the task packet — most failures are underspecification, not insufficient intelligence;
2. retry a transient failure;
3. raise reasoning effort;
4. choose a stronger model;
5. choose a different provider or agent;
6. reconsider the design.

Each step costs more than the one before it. Skipping to step 4 on the first failure is the common and expensive mistake. So is repeating step 2 indefinitely — see the attempt budget in `execution-state.md`.

Do not escalate merely because a stronger model is available.

## Role portability

Do not encode fixed mappings such as Claude = Lead, Codex = Worker, Copilot = Reviewer.

Any capable agent may fill any role when its capabilities, tools, and remaining quota make it suitable. What matters for review is that the reviewer is not the implementer — not which provider it is.

## Context economics

Reusing an existing session can be cheaper than moving work to a provider with more quota, because reassignment means reconstructing repository and task context, and risks losing implicit understanding that was never written down.

When deciding whether to wait or reassign, compare the expected wait against reconstruction tokens, the risk of lost context, and how much work remains. A task that is nearly done is usually worth waiting for.

## Lead budget

Reserve your own high-quality reasoning for decisions with multiplicative effects: architecture, decomposition, difficult diagnosis, integration strategy, and high-risk review.

Once those decisions are made, execution is deterministic work and should be routed accordingly. A Lead spending premium reasoning on relaying status is a Lead that will be out of quota when a real decision arrives.
