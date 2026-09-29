# Native Crew Latency Design

## Problem

Native Codex `crew:run` always enters the full supervisor graph. A cohesive
implementation can therefore spend most of its time in planning and checklist
agents, then run a `test-writer` and implementer concurrently in the same
working tree. That allows duplicate builds, overlapping tests, and test changes
after the implementer's last Green result.

The existing inline execution profile applies only after
`HOST_BRIDGE: current_session_required`. Classifying the raw task text earlier
is unsafe because a ticket identifier alone does not reveal repository scope,
risk, or independent work units.

## Decision

Resolve a native execution profile from the validated `pipeline.json`, after
requirements and scope are known:

- `inline_readonly`: the pipeline mutation scope is `read_only`.
- `single_agent_tdd`: one cohesive implementation stage contains exactly one
  implementer and no independent fan-out units.
- `full_crew`: multiple implementation stages, multiple implementers,
  independent fan-out units, or another shape that needs orchestration.

Use an explicit `tdd_mode` for implementation stages:

- `inline`: the implementer owns focused Red, production changes, Green,
  refactor review, and the final focused rerun.
- `sequential_pair`: `test-writer` produces and runs Red first; only after it
  completes does the implementer change production code and own the final
  Green and refactor rerun.
- `isolated_parallel`: parallel mutation is allowed only for explicitly
  isolated work units or worktrees.

Legacy `tdd_parallel: true` remains readable, but normalizes to
`sequential_pair`; it no longer authorizes simultaneous writes in one worktree.
New pipelines use `tdd_mode`.

Every child lifecycle records a progress fingerprint and an unchanged-wait
counter. Two consecutive wait observations with the same fingerprint return
`interrupt_and_inspect`. Any progress resets the counter. This is enforced by
the provider-neutral lifecycle helper instead of relying on prompt wording.

## Quality invariants

- TDD remains mandatory for every implementation stage.
- A reviewer still follows every implementation stage.
- Final Green evidence must be newer than the last production or test change.
- Two mutating agents never run concurrently in the same worktree.
- Raw task text never selects the native optimized profile before scope is
  resolved.
- Existing legacy pipeline files remain readable.

## Scope

This change updates the provider-neutral pipeline validation helpers, stage
lifecycle helper, supervisor dispatch contract, state-file documentation, and
focused tests. It does not change remote state, deploy anything, or rewrite
unrelated orchestration features.
