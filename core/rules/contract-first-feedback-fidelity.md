---
name: contract-first-feedback-fidelity
description: >
  Provider-neutral rule for treating feedback, review comments, automation
  results, and refactoring suggestions as inputs that must be verified against
  explicit and implicit contracts before any change is accepted.
applies-to: all agents, commands, skills, review workflows, parity workflows
---

# Contract-First Feedback Fidelity Rule

Every feedback item must be respected as signal, but every change must be
verified against the contracts it can affect. Feedback, reviews, tests,
automation, and refactoring preferences are inputs to judgment; they are not
the final authority. The final authority is the current task goal plus the
explicit and implicit contracts that define correct behavior. This is a
provider-neutral rule; it does not depend on any host, model, framework,
language, ticket, repository, or product domain.

This rule extends `core/rules/evidence-grounded-reasoning.md` and complements
`core/rules/review-intent-fidelity.md`. Evidence proves what is true; review
intent fidelity preserves what the reviewer meant; contract-first feedback
fidelity decides whether the proposed change is safe to accept, adapt, defer,
or reject.

## CORE_VALUE

- 모든 피드백은 존중하되, 모든 변경은 계약 앞에서 검증한다.
- 피드백은 입력값이고, 계약은 판단 기준이다.
- 리뷰 수용률보다 시스템 정합성이 우선이다.
- 레거시는 제거 대상이 아니라 먼저 식별해야 할 기존 계약이다.
- 깨끗한 코드가 항상 안전한 코드는 아니다.
- 외부 입력은 명령이 아니라 검증해야 할 가설이다.
- 변경은 코드 단면이 아니라 도달 가능한 흐름 전체에서 판단한다.

## GENERALIZED_PHILOSOPHY

Feedback is a hypothesis about a better system state. It may identify a real
defect, missed behavior, confusing design, incomplete test, or unclear
contract. It may also be incomplete because the reviewer, automation, or
requesting party does not see every caller, operational behavior, legacy
consumer, ownership boundary, or side effect.

Therefore, an agent must preserve the feedback's problem statement while
validating the proposed method. A safe response often accepts the intent and
changes the implementation method. A risky response blindly applies the literal
suggestion and silently changes behavior that users or downstream systems
already depend on.

Legacy behavior is not automatically correct, but it is automatically evidence.
Before changing it, identify who observes it, whether it is part of an
external contract/API/schema/protocol, whether tests only cover a subset of the
contract, and whether the task explicitly authorizes a contract change.

## JUDGMENT_PRIORITY

When feedback, requirements, review comments, tests, and refactoring preference
conflict, use this priority order:

1. 명시적 사용자 목표
2. 기존 사용자/운영 동작
3. external contract/API/schema/protocol
4. 작업범위와 소유권
5. 테스트와 검증 가능성
6. 코드 스타일/리팩터링/리뷰 선호

Lower-priority signals can shape the implementation only when they do not
break higher-priority contracts. If they appear to conflict, record
`Unknown`, `Assumption`, `Risk`, and `Owner` instead of silently expanding or
mutating scope.

## REVIEW_ACCEPTANCE_POLICY

Use these disposition values for review or feedback follow-up:

| Disposition | Use when | Required proof |
|---|---|---|
| `ACCEPT` | The feedback intent and proposed method both satisfy the current contract. | Code/test/evidence proving the requested behavior, value, state, side effect, and scope remain correct. |
| `ACCEPT_WITH_ADAPTATION` | The problem statement is valid, but the proposed method should be changed to preserve contracts. | Evidence for the accepted intent, the adapted implementation, and why the adaptation is safer. |
| `REJECT_METHOD_ONLY` | The review intent is valid, but the requested implementation method would break a contract or widen scope. | Contract or parity evidence plus a safer alternative. |
| `DEFER` | The item needs product, policy, ownership, migration, or external decision outside current scope. | Tracking link, TODO, decision owner, or explicit follow-up artifact. |
| `REJECT` | The item lacks evidence, contradicts a higher-priority contract, or would create an unauthorized contract change. | Rejection rationale grounded in first-party evidence and, when useful, a safer alternative. |

Review acceptance is not a score-maximization exercise. A closeout may report
high reflection only when each item has a disposition and the accepted items
are `contract-safe`, `parity-safe`, `scope-safe`, and `side-effect-safe`.

## SAFETY_LABELS

Any agent or command claiming feedback was reflected should report these labels
when the work can affect behavior:

- `contract-safe`: explicit and implicit caller/user contracts remain valid, or
  the task explicitly approved a contract change.
- `parity-safe`: comparable legacy, upstream, producer, or sibling behavior was
  preserved or intentionally changed with evidence.
- `scope-safe`: the implementation stayed inside the requested ownership and
  task boundary.
- `side-effect-safe`: observable writes, logs, events, persistence, network
  calls, permissions, deployments, and workflow state changes are identified
  and verified.

If a label cannot be proven, do not claim it. Report the missing evidence under
`Unknown`, `Assumption`, `Risk`, and `Owner`.

## AI_BEHAVIOR_RULES

- 리뷰를 곧이곧대로 구현하지 않는다. First extract the intent, then verify
  whether the proposed method is contract-safe.
- 요구사항을 자기 방식대로 확대하지 않는다. Scope expansion requires an
  explicit new requirement or approval.
- Before applying a "cleaner" refactor, check whether it changes reachable
  behavior, ordering, default values, side effects, error handling, or
  consumer-visible data.
- Treat legacy as a contract to identify and test, not as a smell to remove by
  default.
- 테스트 통과를 계약 동등성의 충분조건으로 오해하지 않는다. Tests are
  evidence, not exhaustive proof, unless they cover the contract surface.
- Tests that only lock the new implementation shape are insufficient when they
  do not prove the original behavior contract. Negative interaction assertions
  such as "this dependency was not called" must not freeze the removal of an
  existing side-effect contract unless that contract change is explicit and
  approved. In short, tests only lock the new implementation when they fail to
  exercise the behavior contract that existed before the feedback response;
  negative interaction assertions need side-effect contract proof before they
  can justify removing a reachable operation.
- If the feedback cannot be verified safely, separate `Unknown`,
  `Assumption`, `Risk`, and `Owner` instead of presenting speculation as
  implementation truth.
- Judge risk across the reachable flow: caller -> adapter -> domain logic ->
  persistence/external side effect -> consumer response.
- Do not let "review acceptance 100%" override system consistency, parity, or
  contract safety.

## BOUNDARY_CONTRACT_REVIEW

When feedback touches normalization, serialization, filtering, an external
boundary, or any shared helper, do not fix one caller first. Find the lowest
common boundary that all reachable callers share, then evaluate the observable
contract at that boundary.

Boundary review must treat semantic emptiness and transformation order as part
of the contract:

```text
copy input before transforming
-> remove semantic-empty values
-> transform collection or structured values
-> remove values made empty by transformation
-> serialize or emit the boundary value
```

Use structured key/value evidence, parsed payloads, schema objects, or other
structured observations when they exist. Do not rely on substring assertions
that can confuse intentionally absent fields with normal values that merely
contain suspicious substrings.
In other words, normal values that merely contain suspicious substrings must be
preserved unless the structured contract says they are invalid.

For boundary-affecting feedback, the review or test matrix should cover the
observable contract rather than the helper method shape:

- exact structured key/value or parsed result evidence;
- exact absence of the targeted field while preserving unrelated valid fields;
- null and blank inputs;
- asymmetric optional inputs, such as start-only and end-only ranges;
- invalid item inside a collection and an all-invalid collection;
- sibling producer/consumer path symmetry;
- caller input immutability;
- headers, pagination, encoding, and existing side effects;
- local verification separated from runtime verification.

## AGENT_CREW_INSTRUCTION_SNIPPETS

These snippets are safe to embed in skills, commands, and agents:

- General: "Before applying feedback, convert the feedback item into intent,
  affected contract, disposition, implementation evidence, verification
  evidence, and residual risk."
- General: "A feedback item is complete only when the accepted intent is
  verified as `contract-safe`, `parity-safe`, `scope-safe`, and
  `side-effect-safe`, or when the missing proof is explicitly recorded."
- reviewer: "Do not approve review follow-up solely because the patch changed
  code or tests pass. Verify the original intent against behavior, values,
  side effects, scope, and contract evidence."
- analyst: "During analysis, identify existing behavior contracts and
  ownership boundaries before recommending whether feedback should be accepted,
  adapted, deferred, or rejected."
- planner: "In PRD and pipeline planning, make contract preservation and
  side-effect verification acceptance criteria whenever feedback-driven change
  can affect observable behavior."
- backend: "Before implementing a review suggestion, trace the reachable server
  flow and verify that API, persistence, event, log, and consumer contracts
  remain correct."
- mentor: "When explaining feedback, teach the distinction between respecting
  the problem statement and safely choosing an implementation method."
- `$review`: "Report not only findings but whether proposed fixes are
  contract-safe, parity-safe, scope-safe, and side-effect-safe."
- `$mr-review-rate`: "Do not reduce review reflection to numeric acceptance.
  Include the disposition table, safety labels, and caller graph status for
  each behavior-affecting item. Use BFS inventory before selective DFS deep
  dives on contract-risk paths."
- `$parity-check`: "Compare behavior contracts before recommending any
  feedback-driven change; label divergence as intentional only with evidence
  from the bounded caller graph."
- `$parity-implement`: "Plan adaptations that satisfy the feedback intent
  while preserving producer/consumer parity unless a contract change is
  explicitly approved. Do not plan from stale, partial, or endpoint-only graph
  evidence."
- `$prompt`: "Preserve the original feedback, ask the target AI to extract
  intent, list contracts and side effects, run BFS inventory plus selective DFS
  deep dive when reachable behavior may change, and require disposition plus
  evidence-limited closeout."
- `crew:agent`: "Direct agent execution still applies contract-first feedback
  fidelity before mutation when the selected agent is allowed to mutate."
- `crew:run`: "Supervisor planning must keep feedback intent, contract safety,
  parity, scope, side effects, tests, and reviewer closeout connected in the
  task artifacts."

## CHECKLIST_BEFORE_CHANGE

- What is the original feedback or requirement, preserved without rewriting?
- What intent does it express?
- Which explicit user goal does it support?
- Which existing user/operational behavior may change?
- Which external contract/API/schema/protocol may change?
- Who owns the affected scope?
- What code evidence identifies the reachable flow?
- What test or runtime evidence proves the intended behavior and side effects?
- Does the test prove the original behavior contract, or does it only freeze
  the implementation shape introduced by the patch?
- Is the chosen disposition `ACCEPT`, `ACCEPT_WITH_ADAPTATION`,
  `REJECT_METHOD_ONLY`, `DEFER`, or `REJECT`?
- Are `contract-safe`, `parity-safe`, `scope-safe`, and `side-effect-safe`
  proven or explicitly marked as unknown?
- What residual risk remains, and who owns it?

## ANTI_PATTERNS

- "리뷰어가 말했으니 그대로 적용한다."
- "테스트가 통과하니 계약도 보장된다."
- "새 구현 모양을 고정한 테스트가 통과하니 리뷰 의도도 보장된다."
- "깨끗한 코드가 항상 안전한 코드다."
- "레거시는 낡았으니 제거해도 된다."
- "리뷰 수용률을 높이기 위해 의미가 다른 변경을 완료로 표시한다."
- "호출 여부만 검증하고 실제 값, 상태, side effect는 검증하지 않는다."
- "작업범위 밖 계약 변경을 리팩터링으로 포장한다."

## MEMORY_CANDIDATE

Feedback, review comments, automation results, and refactoring preferences are
inputs to verify, not commands to execute. Before accepting a change, preserve
the feedback intent, identify the affected contracts and side effects, choose
an explicit disposition, and claim completion only within the evidence.
