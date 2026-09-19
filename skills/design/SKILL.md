---
name: design
description: Design implementation approaches for software changes by understanding requirements, inspecting the existing system, identifying the change surface and risks, and producing implementation-ready tasks. Use for architecture decisions, multi-component changes, significant technical uncertainty, compatibility-sensitive work, or tasks that benefit from structured design before implementation.
---

# Design

Produce the smallest sound design that turns a requirement into implementation-ready work.

Do not create architecture for its own sake. Respect the existing system, minimize unnecessary abstraction, and make decisions at the depth warranted by the task.

## Principles

- Prefer the simplest design that satisfies the requirement.
- Inspect existing code and conventions before proposing new structures.
- Preserve compatibility unless change is intentional.
- Avoid speculative abstractions for hypothetical future needs.
- Optimize for correctness, maintainability, testability, and limited blast radius.
- Make uncertainty explicit instead of silently assuming.
- Produce a design that workers can execute with less reasoning and ambiguity.

## Process

### 1. Understand the requirement

Identify:

- desired user/business outcome;
- functional behavior;
- constraints;
- non-goals;
- completion criteria;
- unresolved ambiguities that materially affect implementation.

Do not block on minor ambiguity that can be resolved safely from existing conventions.

### 2. Inspect the existing system

Read enough relevant code, documentation, configuration, tests, and interfaces to understand:

- current behavior;
- component boundaries;
- data flow;
- established patterns;
- public/internal contracts;
- existing test strategy.

Prefer extending established patterns over introducing a parallel architecture without a strong reason.

### 3. Identify the change surface

Determine which areas may change:

- modules/packages;
- APIs and schemas;
- persistence/data model;
- frontend/UI state;
- configuration;
- external integrations;
- tests;
- build/deployment/runtime behavior.

Separate necessary changes from optional cleanup.

### 4. Analyze risk and compatibility

Consider only relevant risks, including:

- backward compatibility;
- migrations and stored data;
- concurrency;
- authentication/security;
- error handling and partial failure;
- performance;
- external API behavior;
- rollout/rollback;
- observability;
- cross-component regressions.

### 5. Choose the design

State the proposed approach and the important decisions behind it.

Compare alternatives only when there is a real tradeoff. Do not pad the design with artificial options when one approach is clearly consistent with the existing system.

Avoid prescribing insignificant implementation details that workers can decide locally.

### 6. Define verification

Specify how success will be demonstrated:

- unit/integration/end-to-end tests;
- static/build checks;
- manual verification where unavoidable;
- regression cases;
- failure/edge cases that matter.

Verification should map back to the original completion criteria.

### 7. Produce implementation tasks

Break the design into executable tasks. Each task should identify:

- objective;
- scope;
- relevant components;
- important constraints/decisions;
- dependencies;
- expected result;
- verification.

Mark tasks that can safely run in parallel.

## Design depth

Match design effort to the problem.

### Small

A few sentences or a short task list may be enough.

### Medium

Document the change surface, key decisions, risks, verification, and task breakdown.

### Large/high-risk

Provide explicit component/data-flow decisions, compatibility strategy, failure behavior, rollout considerations when relevant, and dependency-aware task decomposition.

Do not inflate small work into a large design document.

## Handoff

The final design should let implementation workers begin without rediscovering the architecture.

A useful output structure is:

1. Goal
2. Current behavior
3. Proposed design
4. Key decisions
5. Risks and compatibility
6. Verification
7. Implementation tasks
8. Dependencies and parallelization

The design is complete when it reduces implementation uncertainty enough to execute safely, not when every line of code has been predetermined.
