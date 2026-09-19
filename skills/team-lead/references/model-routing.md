# Model and Worker Routing

Use this reference when choosing among multiple agents, providers, models, or reasoning-effort levels.

## Objective

Minimize total cost and delay while maintaining a high probability of correct completion. Do not optimize token cost in isolation: a cheap worker that repeatedly fails can be more expensive than a stronger worker used once.

## Inputs

Consider:

- difficulty;
- ambiguity;
- novelty;
- blast radius;
- failure cost;
- amount of mechanical work;
- need for repository-wide reasoning;
- provider-specific strengths and tools;
- available context in an existing session;
- remaining quota;
- expected reset time;
- handoff/context reconstruction cost.

## Default strategy

Start with the least expensive worker/effort combination that is reasonably likely to succeed.

Escalate when evidence justifies it:

1. improve the task packet;
2. retry a transient failure;
3. raise reasoning effort;
4. choose a stronger model;
5. choose a different provider/agent;
6. reconsider the design.

Do not escalate merely because a stronger model is available.

## Role portability

Do not encode fixed mappings such as:

- Claude = Lead;
- Codex = Worker;
- Copilot = Reviewer.

Any capable agent may fill any role when its current capabilities, tools, and quota make it suitable.

## Context economics

Reusing an existing worker session may be cheaper than moving work to a provider with more quota because reassignment can require reconstructing repository and task context.

When deciding whether to wait or fail over, compare:

- expected wait;
- urgency;
- reconstruction tokens;
- risk of lost implicit context;
- remaining work size.

## Lead budget

Reserve high-quality reasoning for decisions that have multiplicative effects: architecture, decomposition, difficult diagnosis, integration strategy, and high-risk review.

Prefer lower effort for deterministic execution after those decisions have been made.
