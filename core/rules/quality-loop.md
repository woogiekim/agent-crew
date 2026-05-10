---
name: quality-loop
description: >
  Apply to all implementation stages.
  Enforces a validate → fix → re-validate loop until the stage output meets
  the acceptance criteria defined in the PRD, or until the retry limit is reached.
applies-to: backend, frontend, designer, devops, reviewer, task-runner
---

# Quality Loop Rule

Every implementation stage must iterate until its output is verified correct.
Completing once and moving on is not acceptable.

## Loop Protocol

For each stage, repeat the following until **all acceptance criteria pass** or
the retry limit is reached:

- **Validation failure** (criteria checked, output incorrect): retry up to **3 times**.
- **Agent crash** (no STATUS returned at all): retry up to **5 times** before BLOCKED.

```
1. Implement (or review) the assigned work.
2. Verify against acceptance criteria (see below).
3. If any criterion fails → fix the issue, then return to step 2.
   (Validation failure retry counter increments here.)
4. If all criteria pass → report completion.
5. If the stage returns no STATUS → treat as crash, increment crash retry counter,
   and re-invoke the stage from step 1.
6. If the validation retry limit (3) is reached without passing →
   attempt BLOCKED Recovery (see below) before reporting BLOCKED.
7. If the crash retry limit (5) is reached → report BLOCKED with details.
```

## Acceptance Criteria

Treat all of the following as required before a stage is considered complete:

- All items listed in the PRD for this stage are present in the output.
- No obvious regressions introduced (run existing tests / checks if available).
- Expected artifact files exist at their specified paths.
- No TODO, placeholder, or stub left in implementation output.

## Reporting

Include the iteration count in the stage completion report:

```text
STATUS: completed | BLOCKED
ITERATIONS: {n}
ARTIFACTS: {paths}
ISSUES_RESOLVED: {brief list, or "none"}
```

If `BLOCKED`, include:
```text
BLOCKER: {what failed after all retry attempts}
```

## BLOCKED Recovery

Before reporting BLOCKED to the orchestrator, the agent must attempt one
decomposition pass:

1. Break the failing requirement into the **smallest possible sub-task** that
   can be verified independently.
2. Implement and verify that sub-task only.
3. If the sub-task passes → continue with the remaining work, resetting the
   validation retry counter.
4. If the sub-task still fails → report BLOCKED with full detail, including
   what was attempted during decomposition.

This decomposition attempt does **not** count toward the validation retry limit.
It is a single additional recovery pass performed only after the primary retry
limit is exhausted.

## Task-Runner Enforcement

The task-runner must pass the path to this rule to every stage agent:

```text
QUALITY_RULE_PATH: ~/.agent-crew/rules/quality-loop.md

Read and apply the quality loop rule before reporting stage completion.
```

After each stage returns, the task-runner checks:

- If `STATUS: completed` → continue to next stage.
- If no STATUS returned → treat as crash. Re-invoke the stage (up to 5 crash
  retries). After all crash retries are exhausted, report BLOCKED.
- If `STATUS: BLOCKED` → halt the pipeline and report the blocker to the
  orchestrator.
