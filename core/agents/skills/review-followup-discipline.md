---
name: review-followup-discipline
description: Turn review comments into atomic dispositions with evidence, policy waits, and local-vs-remote status separated.
loaded_by: backend,frontend,devops,documenter,analyst,planner,reviewer
axis: review-followup
profile_type: review-policy
detection: review OR comment OR feedback OR reflected OR addressed OR note OR disposition OR policy waiting OR 리뷰 OR 코멘트 OR 피드백 OR 반영 OR 처리 OR 정책대기
---

# Skill: review-followup-discipline

## Purpose

Handle review feedback as traceable work, not as a generic "done" summary.
Each comment needs an intent, disposition, evidence, and remaining decision
state so reviewers can see what changed and what is intentionally waiting.

## References

- `core/agents/skills/code-review.md`
- `core/rules/review-intent-fidelity.md`
- `core/rules/completion-report.md`
- Michael Fagan, "Design and Code Inspections to Reduce Errors in Program Development" (1976)
- Google Engineering Practices, Code Review Developer Guide

## When to Apply

- A task asks to reflect review comments, rate review follow-up, leave an MR
  note, update a review summary, or explain policy-waiting items.
- Reviewer comments include behavioral, contract, test, audit, documentation,
  or operational concerns.
- Some feedback is implemented while another part is deferred, not applicable,
  blocked by policy, or unknown.

## Disposition Model

Use two disposition axes per review item:

- `candidate_disposition` / `contract_disposition` records the contract-first
  triage decision: `ACCEPT`, `ACCEPT_WITH_ADAPTATION`, `REJECT_METHOD_ONLY`,
  `DEFER`, or `REJECT`.
- `disposition` records lifecycle status for human closeout and reviewer gates.

Existing user-facing lifecycle labels remain valid:

- `IMPLEMENTED`: code, docs, tests, or config changed and focused verification
  supports the claim.
- `LOCAL_DONE`: local evidence exists, but no remote note, push, MR update, or
  CI mutation was performed.
- `PARTIAL`: some reviewer intent is covered, with explicit remaining gap.
- `POLICY_WAITING`: implementation is intentionally held pending a business,
  operational, or product decision.
- `NOT_APPLICABLE`: evidence shows the comment does not apply to this scope.
- `UNKNOWN`: evidence is insufficient; do not claim completion.

Reviewer validation maps `IMPLEMENTED` and `LOCAL_DONE` to the canonical
ledger lifecycle `implemented`; `PARTIAL`, `POLICY_WAITING`, `DEFERRED`, and
`UNKNOWN` to `deferred`; and `NOT_APPLICABLE` to `not-applicable`. These labels
must not replace the contract triage axis.

Do not merge policy waits into implementation summaries. Do not claim remote
MR, issue, or CI status unless the external mutation or query actually ran.

## Contract And Test Evidence

For every item reported as reflected, record whether the accepted response is
`contract-safe`, `parity-safe`, `scope-safe`, and `side-effect-safe`. If any
label cannot be proven, keep the item as `PARTIAL`, `UNKNOWN`, or
`POLICY_WAITING` instead of summarizing it as complete.

For any review item that can affect behavior, persistence, events, logs,
network calls, generated output, UI state, or another external side effect,
include caller graph status before claiming the item is reflected. Use BFS
inventory to identify the reachable surface and selective DFS deep dive for the
risk-bearing path. If the graph is partial or the search only proves
`No references found` inside a bounded scope, keep the related safety label
unknown rather than upgrading the item to complete.

Focused verification must explain what contract it proves. The test proves the
original behavior contract only when it checks the behavior, value, state, or
side effect that the review item was concerned about. In reviewer-facing
summaries, say that the test proves the original behavior contract only when
that claim is supported by evidence. Tests that only freeze the implementation
shape introduced by the patch are not enough; tests only freeze the
implementation shape when they assert the patch mechanics but not the
reviewer's behavior, value, state, or side-effect concern.

Be especially careful with negative interaction assertions. A check that a
dependency was not called can be useful only when the removed call was not part
of an existing side-effect contract. If the call previously updated persistence,
logs, events, network state, files, UI state, or other observable behavior, the
follow-up must prove that the side effect is intentionally preserved, replaced,
or explicitly removed.

Rule of thumb: tests only freeze the implementation shape when they assert
patch mechanics without proving the reviewer's behavior, value, state, or
side-effect concern.

## Note Shape

Prefer this order for review follow-up notes:

1. Reflected changes grouped by reviewer intent.
2. Verification evidence with command/result scope.
3. Items intentionally excluded from scope.
4. Policy or owner decisions still waiting.
5. Related commit or local diff reference, if present.

## Checklist

- [ ] Every review comment has one disposition.
- [ ] Evidence names the changed path, test, command, or contract.
- [ ] Reflected items include contract-safe, parity-safe, scope-safe, and
      side-effect-safe evidence or an explicit unknown/residual risk.
- [ ] Behavior-affecting review items include caller graph status from BFS
      inventory and any needed selective DFS deep dive, or an explicit unknown.
- [ ] Tests prove the original behavior contract, not merely the new
      implementation shape.
- [ ] Negative interaction assertions do not hide a removed side-effect
      contract.
- [ ] Policy waits are separated from completed work.
- [ ] Local status is not presented as remote MR or issue mutation.
- [ ] Final note avoids unverifiable claims and raw log dumps.
