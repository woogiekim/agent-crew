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
the retry limit (3) is reached:

```
1. Implement (or review) the assigned work.
2. Verify against acceptance criteria (see below).
3. If any criterion fails → fix the issue, then return to step 2.
4. If all criteria pass → report completion.
5. If retry limit is reached without passing → report BLOCKED with details.
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
BLOCKER: {what failed after 3 attempts}
```

## Task-Runner Enforcement

The task-runner must pass the path to this rule to every stage agent:

```text
QUALITY_RULE_PATH: ~/.agent-crew/rules/quality-loop.md

Read and apply the quality loop rule before reporting stage completion.
```

After each stage returns, the task-runner checks:

- If `STATUS: completed` → continue to next stage.
- If `STATUS: BLOCKED` → halt the pipeline and report the blocker to the orchestrator.
