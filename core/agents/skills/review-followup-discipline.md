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

Record each comment's intent, disposition, evidence, and pending decisions.

## References

- `core/agents/skills/code-review.md`
- `core/rules/review-intent-fidelity.md`
- `core/rules/completion-report.md`
- Michael Fagan, "Design and Code Inspections to Reduce Errors in Program Development" (1976)
- Google Engineering Practices, Code Review Developer Guide

## When to Apply

- Address or rate review feedback, prepare or post an MR note, update a review summary, or explain policy waits.
- Triage behavior, contract, test, audit, documentation, or operational concerns.
- Track mixed outcomes, including deferred, inapplicable, policy-blocked, and unknown items.

## Disposition Model

Use two disposition axes per review item:

- `candidate_disposition` / `contract_disposition` records the contract-first
  triage decision: `ACCEPT`, `ACCEPT_WITH_ADAPTATION`, `REJECT_METHOD_ONLY`,
  `DEFER`, or `REJECT`.
- `disposition` records lifecycle status for human closeout and reviewer gates.

Existing user-facing lifecycle labels remain valid:

- `IMPLEMENTED`: focused checks verify the code, docs, test, or config change.
- `LOCAL_DONE`: evidence is for local work before any remote note, push, MR update, or CI mutation.
- `PARTIAL`: some reviewer intent is covered. State the remaining gap.
- `POLICY_WAITING`: implementation awaits a business, operational, or product decision.
- `NOT_APPLICABLE`: evidence places the comment outside the scope.
- `UNKNOWN`: insufficient evidence. Withhold the completion claim.

Reviewer validation maps `IMPLEMENTED` and `LOCAL_DONE` to the canonical
ledger lifecycle `implemented`; `PARTIAL`, `POLICY_WAITING`, `DEFERRED`, and
`UNKNOWN` to `deferred`; and `NOT_APPLICABLE` to `not-applicable`. These labels
must not replace the contract triage axis.

List policy waits separately. Claim remote MR, issue, or CI status only
after executing the corresponding external mutation or query.

## Contract And Test Evidence

For each reflected item, record evidence for `contract-safe`, `parity-safe`,
`scope-safe`, and `side-effect-safe`. For any unproven label, keep the item
`PARTIAL`, `UNKNOWN`, or `POLICY_WAITING`.

Record caller graph status before claiming any item that may affect behavior,
persistence, events, logs, network calls, generated output, UI state, or other
side effects is reflected. Use BFS inventory for the reachable surface and
selective DFS for risk-bearing paths. With a partial graph or bounded
`No references found` result, keep the related safety label unknown.

State what focused verification proves. Say the test proves the original behavior contract
only when it checks the behavior, value, state, or side effect raised in the
review. Where tests only freeze the implementation shape, add evidence about
the original concern before claiming it is covered.

Use negative interaction assertions as evidence only when the absent call
carried no side-effect contract. If it changed persistence, logs, events,
network state, files, UI state, or other observable behavior, prove that
the effect is preserved, replaced, or explicitly removed.

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
