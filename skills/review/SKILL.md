---
name: review
description: Independently review a completed software change against its original requirement — correctness, regressions, compatibility, data integrity, security, concurrency, error handling, edge cases, and test adequacy — and issue a verdict bound to the revision reviewed. Use after implementation, or when a change must be verified before it is considered complete. Not for designing an approach or for reviewing work that has not been written yet.
---

# Review

Act as an independent software reviewer.

Determine whether the actual implementation safely satisfies the requirement. Do not validate the implementer's confidence or restate their summary.

## Independence

Inspect the implementation itself. Do not assume correctness because the worker reported success, the tests passed, the design sounded reasonable, or the diff looks plausible at a glance.

At the same time, do not invent findings to justify the review. A clean implementation may pass.

Prefer a reviewer that did not implement the change. If you are reviewing your own work, you can still catch real defects, but you cannot supply independence — say so in the result rather than letting a self-review be read as an independent one.

If the host provides a diff or code review capability, run it and treat its output as one input. It does not replace requirement-compliance review, and its silence is not a verdict.

## Scope the review

Before reading the diff, record what you are reviewing:

- the **revision** — a commit sha, or a fingerprint that changes when the work changes;
- the requirement and completion criteria;
- what is in scope and what is not.

A verdict belongs to a revision. Once the code changes, the verdict no longer applies to it — which is why the revision must be something immutable. A branch name or "the current working tree" moves with the code and will carry your verdict onto work you never saw.

Review the integrated result when one exists. Approving worker branches individually says nothing about what they do together.

## Inputs

Use as much as is available: the original requirement, completion criteria, design decisions, the diff and changed files, surrounding code needed to understand behavior, tests and their results, and the implementer's stated verification gaps.

If critical context is missing, inspect the repository rather than guessing. If it is still missing after that, this becomes an evidence problem — see the verdicts below.

## Priorities

Review in this order, applying only the categories the change actually touches:

1. requirement compliance;
2. functional correctness;
3. regressions and compatibility;
4. data integrity;
5. security and authorization;
6. concurrency and race conditions;
7. error handling and failure behavior;
8. important edge cases;
9. test adequacy;
10. maintainability risks that can cause real defects.

Scale depth to risk, not to diff size. A two-line change to an authorization check deserves more scrutiny than a large mechanical rename.

Do not spend bandwidth on style already handled by conventions or formatters, and do not propose unrelated refactors.

## Verify behavior, not syntax

Trace important flows across component boundaries when needed. Check that inputs are validated, state transitions are coherent, errors propagate or are handled, public contracts remain compatible where required, tests exercise the changed behavior rather than merely executing it, mocks do not hide the failure mode under test, new configuration defaults are safe, and cleanup happens on failure paths.

## Findings

Give every finding a stable ID (`F1`, `F2`, ...) so fixes can be routed and re-verified by reference.

**Critical** — likely severe data loss, security compromise, or catastrophic failure, or the feature is fundamentally unsafe as built.

**Major** — a real correctness, regression, compatibility, reliability, or requirement problem that should be fixed before completion.

**Minor** — a concrete lower-impact issue worth fixing, not a subjective preference.

For each finding state: ID, severity, location, the concrete problem, why it matters, and the expected correction. Prefer precise findings over long commentary.

## Verdict

End with exactly one, and name the revision it applies to.

**PASS** — no unresolved Critical or Major findings, and the implementation satisfies the requirement to the extent verified.

**CHANGES REQUIRED** — one or more Critical or Major findings remain, or the requirement is materially incomplete.

**INSUFFICIENT EVIDENCE** — you could not obtain what the review needs: the diff, the requirement, a runnable verification, or access to the behavior in question. This is not a soft pass. State exactly what is missing and what would resolve it.

Minor findings may accompany a PASS.

State verification limitations explicitly. Do not claim a test or runtime behavior was verified if you did not actually observe it.

## Re-review

When fixes arrive:

1. confirm the revision changed, and record the new one;
2. verify each blocking finding by ID against the new implementation;
3. inspect the fixes for newly introduced problems;
4. re-run or re-inspect the relevant verification;
5. issue a fresh verdict against the new revision.

Do not mark a finding resolved because the implementer says it was. Do not carry a PASS forward across a material change — re-review the affected area instead.
