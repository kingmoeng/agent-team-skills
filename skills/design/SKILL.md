---
name: design
description: Turn a requirement into an implementation-ready design — understand the goal, inspect the existing system, identify the change surface and risks, choose an approach, and decompose it into dispatchable tasks with bounded writable scopes. Use for architecture decisions, changes to public contracts, hard-to-reverse work, material uncertainty about approach, or multi-component changes whose parts interact. Not for a change whose approach is already obvious, and not for reviewing code that is already written.
---

# Design

Produce the smallest sound design that turns a requirement into implementation-ready work.

Do not create architecture for its own sake. Respect the existing system, minimize unnecessary abstraction, and decide at the depth the task warrants.

You may be invoked directly by a user who wants a design, or as a phase of a larger effort led by another agent. In the second case your output is consumed by a dispatcher, so it must decompose into tasks — see Handoff.

## Principles

- Prefer the simplest design that satisfies the requirement.
- Inspect existing code and conventions before proposing new structures.
- Preserve compatibility unless change is intentional.
- Avoid speculative abstractions for hypothetical future needs.
- Optimize for correctness, maintainability, testability, and limited blast radius.
- Make uncertainty explicit instead of silently assuming.
- Leave workers less to reason about, not more.

## Process

### 1. Understand the requirement

Identify the desired outcome, functional behavior, constraints, non-goals, completion criteria, and any ambiguity that materially affects implementation.

Do not block on minor ambiguity that existing conventions resolve safely.

### 2. Inspect the existing system

Read enough code, configuration, tests, and interfaces to understand current behavior, component boundaries, data flow, established patterns, public and internal contracts, and the existing test strategy.

Prefer extending established patterns over introducing a parallel architecture without a strong reason.

### 3. Identify the change surface

Determine what may change: modules, APIs and schemas, persistence and data model, UI state, configuration, external integrations, tests, and build or runtime behavior.

Separate necessary changes from optional cleanup, and say which is which.

### 4. Analyze risk and compatibility

Consider only the risks this change actually raises: backward compatibility, migrations and stored data, concurrency, authentication and authorization, error handling and partial failure, performance, external API behavior, rollout and rollback, observability, and cross-component regressions.

### 5. Choose the design

State the approach and the decisions behind it.

Compare alternatives only where a real tradeoff exists. Do not pad the design with artificial options when one approach is clearly consistent with the existing system, and do not prescribe details workers can decide locally.

### 6. Define verification

Specify how success will be demonstrated: unit, integration, or end-to-end tests; static and build checks; unavoidable manual verification; regression cases; and the failure and edge cases that matter.

Verification must map back to the completion criteria.

### 7. Decompose into tasks

Break the design into executable tasks. Each task states its objective, writable scope, constraints and decisions it must honor, dependencies, expected result, and verification.

**Every task names a writable scope.** A task without one has not finished being decomposed, and cannot be dispatched safely.

Mark tasks as parallel-safe only when their writable scopes do not intersect and neither needs the other's result. A separate worktree removes a write collision, so say so explicitly when you rely on one — but it does not remove a dependency, and a task that needs another's output is never parallel-safe with it.

## Design depth

Match effort to risk, not to the number of files touched. One migration can warrant more design than twenty mechanical edits.

Go deeper when the change alters a public contract, is hard to reverse, touches stored data, carries real uncertainty about the approach, or spans components whose changes interact. Stay shallow when none of these hold — a few sentences and a task list may be the whole design.

At depth, be explicit about component and data-flow decisions, compatibility strategy, failure behavior, rollout when relevant, and dependency-aware decomposition. Do not inflate small work into a large document.

## Handoff

The design should let workers begin without rediscovering the architecture.

A useful structure:

1. Goal
2. Current behavior
3. Proposed design
4. Key decisions
5. Risks and compatibility
6. Verification
7. Tasks
8. Dependencies and parallelization

When a dispatcher will consume this, emit the tasks in whatever packet shape it supplied. If it supplied none, emit each task with these fields and leave workspace and base revision for the dispatcher to fill at dispatch time:

```text
Task: <short-id>
Objective: <the outcome>
Context: <what is needed to act>
Writable scope: <paths this task may modify>
Constraints: <decisions it must honor>
Dependencies: <tasks or artifacts it needs>
Completion criteria: <observable>
Verification: <commands to run, or what to demonstrate>
```

The design is complete when it reduces implementation uncertainty enough to execute safely — not when every line of code has been predetermined.
