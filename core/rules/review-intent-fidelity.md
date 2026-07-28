---
name: review-intent-fidelity
description: >
  Provider-neutral rule for preserving reviewer intent during review follow-up.
  Requires comment-by-comment disposition, semantic acceptance criteria, and
  evidence-limited completion claims.
applies-to: reviewer, supervisor, backend, frontend, devops, qa-owner
---

# Review Intent Fidelity Rule

Review follow-up is complete only when the reviewer intent has been preserved,
translated into verifiable acceptance criteria, and checked against code,
tests, or explicit non-implementation rationale.

This rule extends `core/rules/evidence-grounded-reasoning.md`. Evidence still
comes first, but review follow-up adds one more constraint: the unit of work is
the reviewer's requested meaning, not the implementer's visible code change.

## Core Value

Do not claim "review addressed" merely because code changed or tests pass.
Claim completion only when each review comment has a durable disposition and
the evidence proves the intended behavior, state, value, side effect, or scope
decision requested by that comment.

For example, a review asking that an automatic approval log be written by a
specific actor is not satisfied by proving that some logging method was called.
The implemented evidence must prove the semantic values and side effects the
reviewer requested, such as actor identity, status, comment, affected entity,
and entity type.

## Review Ledger

Every review follow-up task must write a review ledger under task context:

```text
{TASK_DIR}/context/review-ledger.json
```

Markdown is allowed for human-facing work when machine parsing is unavailable:

```text
{TASK_DIR}/context/review-ledger.md
```

Each ledger item records:

- `review`: the original review comment, preserved without rewriting its
  meaning.
- `intent`: the acceptance criterion inferred from that comment.
- `disposition`: one of `implemented`, `deferred`, `rejected`, or
  `not-applicable`.
- disposition-specific evidence, described below.
- `residual_risk`: remaining uncertainty, or `none`.

## Dispositions

| Disposition | Required evidence |
|---|---|
| `implemented` | `code_evidence`, `test_evidence`, and `semantic_verification` proving the requested state, value, side effect, or behavior. |
| `deferred` | `tracking_evidence`, such as a TODO, issue, decision record, or external approval link. |
| `rejected` | `rejection_rationale` and `alternative`, grounded in technical evidence. |
| `not-applicable` | `scope_basis` proving why the comment does not apply to the current task scope. |

`implemented` evidence must not stop at call existence, object construction, or
line coverage. It must prove the reviewer's requested meaning. If the requested
meaning cannot be tested safely, record a narrow exception and residual risk
instead of claiming full implementation.

## JSON Format

```json
{
  "schema_version": 1,
  "items": [
    {
      "id": "RIF-001",
      "review": "로그 남기는 것이 맞음. 뉴스봇으로 남기면 됨",
      "intent": "자동승인 이력을 뉴스봇 ActionLog로 남긴다",
      "disposition": "implemented",
      "code_evidence": ["src/CmsArticleService.java:120"],
      "test_evidence": ["test/CmsArticleServiceNewsBotActorTest.java:42"],
      "semantic_verification": "memberSeq/status/comment/contentSeq/contentType values are asserted",
      "residual_risk": "none"
    }
  ]
}
```

## Markdown Format

```markdown
| Review | Intent | Disposition | Code Evidence | Test Evidence | Semantic Verification | Residual Risk |
|---|---|---|---|---|---|---|
| 로그 남기는 것이 맞음. 뉴스봇으로 남기면 됨 | 자동승인 이력을 뉴스봇 ActionLog로 남긴다 | implemented | src/CmsArticleService.java:120 | test/CmsArticleServiceNewsBotActorTest.java:42 | memberSeq/status/comment/contentSeq/contentType values are asserted | none |
```

## Completion Gate

When a review ledger exists, completion, repair, and reviewer closeout must
validate every item before accepting "review follow-up complete":

- Unknown, missing, or unsupported `disposition` values are blockers.
- `implemented` items without code evidence, test evidence, or semantic
  verification are blockers.
- `deferred`, `rejected`, and `not-applicable` items without their required
  rationale or tracking evidence are blockers.
- A ledger can be absent for non-review-follow-up implementation work, but a
  reviewer or supervisor must require it before declaring that review comments
  were reflected, handled, addressed, fixed, or accepted.

The closeout report may only claim the dispositions present in the ledger. If a
comment is deferred, rejected, not applicable, or still lacks evidence, the
report must say so explicitly.
