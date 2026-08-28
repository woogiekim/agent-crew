# /review-followup — Review Feedback Follow-up Loop Coordinator

## Purpose

Coordinate the user's repeated PR/MR review follow-up workflow without turning
it into hidden automation. This command connects review reflection, planning,
prompt composition, implementation execution, and parallel review verification
into one explicit operator-guided loop.

It exists because the individual commands already have clear responsibilities:

- `mr-review-rate` reads PR/MR review items and reports reflection rates.
- `crew:agent` can analyze how to handle the remaining feedback.
- `prompt` turns the selected plan into an omission-resistant execution prompt.
- `crew:run` executes the approved implementation workflow.
- `review-synthesis` runs read-only review lenses after implementation.

`review-followup` coordinates those steps, preserves their safety boundaries,
and stops at every approval checkpoint. It does not replace the underlying
commands and it must not auto-execute mutations.

## Trigger

- Codex: `$review-followup`
- Codex: `$review-followup !123`
- Claude Code: `/review-followup`
- Claude Code: `/review-followup !123`
- Native/provider-neutral notation: `review-followup <scope>`

## Inputs

- `MR_OR_PR_ID` optional MR/PR id or URL.
- `BASE_REF` optional comparison base.
- `SCOPE` optional branch, path, repository, or review source.
- `MAX_CYCLES` optional loop budget. Default `max_cycles=3`.
- `MODE` optional:
  - `plan`: produce the next review-followup plan only.
  - `run-approved-next`: continue only when the operator explicitly selected
    the next implementation step.
  - `verify`: run or request read-only verification only.

## Non-Goals

- No lifecycle hook.
- No `PreToolUse` hook.
- No `UserPromptSubmit` hook.
- No background hidden routing.
- No automatic code edits from the reflection report alone.
- No automatic MR/PR note, description update, merge, push, deploy, or issue
  mutation.
- No proof-file busywork. Use existing task artifacts when available; do not
  create separate evidence just to satisfy the loop.

## Required Commands And Boundaries

The coordinator may ask the operator to invoke or may delegate to these
logical commands, preserving each command's own contract:

| Step | Logical command | Boundary |
|---|---|---|
| Review reflection | `mr-review-rate` | Read-only; separates `LOCAL_REFLECTION_RATE` from `MR_REFLECTION_RATE`. |
| Handling analysis | `crew:agent` | Read-only planning by default unless the selected agent definition allows mutation and the operator explicitly requested direct mutation. |
| Prompt composition | `prompt` | Non-executing prompt generation until the operator chooses a next action. |
| Implementation | `crew:run` | Mutating work only through supervisor planning, TDD, approval, and reviewer quality loop. |
| Verification review | `review-synthesis` | Read-only review lenses; provider-native lenses only through the review-lens contract. |

## Review Intent And Contract Safety

Apply `Review Intent Fidelity` and `Contract-First Feedback Fidelity` to every
review atom.

The loop must maintain or ask the implementation workflow to maintain a
`review-ledger` in `{TASK_DIR}/context/review-ledger.json` or
`{TASK_DIR}/context/review-ledger.md` when implementation work occurs.

For every meaningful review item, preserve:

- original reviewer request or faithful paraphrase;
- inferred intent;
- candidate or contract disposition: `ACCEPT`, `ACCEPT_WITH_ADAPTATION`,
  `REJECT_METHOD_ONLY`, `DEFER`, or `REJECT`;
- lifecycle disposition after implementation work: `implemented`, `deferred`,
  `rejected`, or `not-applicable`;
- implementation or non-implementation rationale;
- code evidence when verified;
- test or verification evidence when verified;
- safety labels: `contract-safe`, `parity-safe`, `scope-safe`,
  `side-effect-safe`;
- residual risk or `Unknown`.

Reflection percentages are advisory. A loop cannot claim complete review
follow-up solely from `LOCAL_REFLECTION_RATE=100%` or `MR_REFLECTION_RATE=100%`
unless review intent, contract safety, and verification evidence are aligned.

## Feedback Triage Gate

In this workflow, review feedback is a candidate input, not an implementation
command. The coordinator must preserve the reviewer's problem statement, then
decide whether the requested method is safe under the current contract,
parity, scope, and side-effect boundaries.

Disposition must be decided before any item enters an implementation prompt.
Only `ACCEPT` and `ACCEPT_WITH_ADAPTATION` items may become direct
implementation work. `REJECT_METHOD_ONLY`, `DEFER`, and `REJECT` items remain
explicit ledger entries with rationale, residual risk, owner, tracking detail,
or a safer alternative.

Use `candidate_disposition` for the triage value in synthesis and planning
reports. When an item is promoted into `review-ledger`, preserve that value as
`contract_disposition` and use `disposition` only for the lifecycle result.
For compatibility, human summaries may continue showing `IMPLEMENTED`,
`LOCAL_DONE`, `PARTIAL`, `POLICY_WAITING`, `DEFERRED`, `NOT_APPLICABLE`, and
`UNKNOWN`, but those display labels must map to the canonical lifecycle axis
before reviewer validation.

Do not convert every `review-synthesis` finding into a `crew:run` todo. A
synthesis finding must first become an atomic review item with preserved source
lens, intent, affected contract, disposition, safety labels, and evidence
limit. This keeps valid rejections and adaptations visible instead of treating
literal reviewer acceptance as the goal.

## Loop Flow

### Phase 1 — Intake And Reflection

1. Resolve the MR/PR/scope from explicit input. If the command cannot identify
   the review source, ask with ordinary numbered choices.
2. Run or request the `mr-review-rate` pass for PR/MR review items.
3. Split feedback into atomic review items.
4. Report `LOCAL_REFLECTION_RATE` and `MR_REFLECTION_RATE` separately.
5. Stop if all review atoms are reflected and verified, unless the operator
   asks for synthesis verification.

### Phase 2 — Plan Remaining Work

For remaining or partially reflected items:

1. Use `crew:agent` analysis to decide how each item should be handled.
2. Prefer `ACCEPT_WITH_ADAPTATION` or `REJECT_METHOD_ONLY` when the review
   problem is valid but the literal method would break contract, parity, scope,
   or side-effect safety.
3. Send only `ACCEPT` and `ACCEPT_WITH_ADAPTATION` items to implementation.
4. Keep deferred and rejected items explicit. Do not hide them to improve the
   numerical rate.
5. Produce the next implementation plan in a form suitable for `prompt`.

### Phase 3 — Prompt And Approval Checkpoint

1. Use `prompt` composition rules to produce an execution prompt that includes:
   review atoms, intent, accepted `candidate_disposition` /
   `contract_disposition`, lifecycle disposition expectations, contracts, side
   effects, required tests, verification, forbidden actions, and completion
   criteria.
2. Present an approval checkpoint before mutation.
3. The coordinator must not auto-execute `crew:run`.
4. The operator must choose the next action using ordinary numbered choices.

Example choices:

```text
다음에 무엇을 할까요?

1. 남은 리뷰 항목 반영을 `crew:run`으로 실행
2. 실행 프롬프트만 보여주고 대기
3. `review-synthesis`로 검증부터 수행
4. 반영률 보고서만 유지하고 종료
```

### Phase 4 — Implementation

When the operator selects implementation:

1. Execute via `crew:run` with the generated prompt.
2. Preserve the original feedback and review-ledger requirements in the task.
3. Require focused verification before completion.
4. Return to Phase 1 for a new reflection measurement after implementation.

### Phase 5 — Synthesis Verification

After implementation reflection reaches 100%, or when the operator asks for
independent verification:

1. Run or request `review-synthesis` for the same scope.
2. Include provider-native review only when it is exposed as a read-only,
   non-mutating review lens.
3. Preserve every finding's source lens.
4. If actionable findings remain, return to Phase 2 with those findings as
   feedback atoms.
5. If no actionable findings remain, close the loop.

## Loop Limits

- Default `max_cycles=3`.
- If the loop reaches `max_cycles`, stop with `STATUS: blocked` and report the
  remaining review atoms, failed verification, or conflicting evidence.
- The operator may explicitly start a new command invocation with a larger
  budget, but the command must not continue silently.

## Mutation Safety

The coordinator:

- must not auto-execute mutating commands;
- must not auto-post MR/PR notes;
- must not auto-update MR/PR descriptions;
- must not push;
- must not merge;
- must not deploy;
- must not commit unless the operator explicitly invokes a separate approved
  commit workflow.

Every mutation boundary is an approval checkpoint. Broad approval, implicit
approval, stale approval, and self-approval are invalid.

## Output Contract

The default output is human-readable Korean on this PC, with command tokens and
status values preserved.

Minimum report:

```text
리뷰 반영 루프 상태입니다.

대상: <MR/PR/scope or Unknown>
cycle: <n>/<max_cycles>
로컬 반영률: <done>/<total> = <percent or Unknown>
MR/PR 전체 반영률: <done>/<total> = <percent or Unknown>
검증 리뷰 상태: <not-run|running|findings|clean|Unknown>

남은 항목:
1. <review item>
   candidate_disposition: <ACCEPT|ACCEPT_WITH_ADAPTATION|REJECT_METHOD_ONLY|DEFER|REJECT|Unknown>
   lifecycle_disposition: <implemented|deferred|rejected|not-applicable|Unknown>
   gap: <...>
   next: <...>
   safety: contract-safe=<yes|no|unknown>, parity-safe=<yes|no|unknown>,
           scope-safe=<yes|no|unknown>, side-effect-safe=<yes|no|unknown>

다음에 무엇을 할까요?

1. 남은 리뷰 항목 반영을 `crew:run`으로 실행
2. 실행 프롬프트만 보여주고 대기
3. `review-synthesis`로 검증부터 수행
4. 반영률 보고서만 유지하고 종료
```

Use ordinary numbered choices such as `1.` and `2.`. Do not use circled digit
characters or mechanical approval labels in the default output.

## Completion Criteria

The loop is complete only when:

- all review atoms have a disposition;
- all implemented items have code and verification evidence or explicit
  residual risk;
- `LOCAL_REFLECTION_RATE` and `MR_REFLECTION_RATE` are reported separately;
- remote state gaps are not collapsed into local completion;
- `review-synthesis` has no actionable findings, or findings are explicitly
  deferred/rejected/not-applicable with evidence;
- no unapproved remote write, push, merge, deploy, or external mutation was
  performed.
