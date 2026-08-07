# Completion Report Format

Return to parent within 3 lines when the agent-specific return contract does not
define another compact structured shape. Do not re-quote file contents or add
prose.
When the stage produced analysis, judgment, review, or planning artifacts, the
artifact referenced by `{ARTIFACT_FIELD}` must already satisfy
`core/rules/evidence-grounded-reasoning.md`: cited first-party evidence and an
explicit evidence-to-inference-to-conclusion flow are required before this
completion report may be returned.
When the stage claims review comments were reflected, handled, addressed,
fixed, accepted, or completed, it must also satisfy
`core/rules/review-intent-fidelity.md`: the completion report may only claim
the dispositions recorded in `{TASK_DIR}/context/review-ledger.json` or
`{TASK_DIR}/context/review-ledger.md`.
When the stage claims feedback-driven changes are complete, it must also
satisfy `core/rules/contract-first-feedback-fidelity.md`: accepted items may
only be reported as complete within the proven `contract-safe`, `parity-safe`,
`scope-safe`, and `side-effect-safe` evidence.
When the stage claims reachable behavior, side effects, parity, root cause, or
unused code status, it must also state the caller graph evidence level:
completed BFS inventory plus any needed selective DFS deep dive, partial graph,
`No references found`, not applicable, or unknown. A completion report must not
upgrade partial graph evidence into a stronger semantic claim.

```text
STATUS: completed
{ARTIFACT_FIELD}: {value}
{METRICS_FIELD}: {value}
```

- When this generic shape applies, `STATUS` must be the first field and must be
  `completed`.
- For analysis, judgment, review, or planning output, every
  artifact field required by the agent contract must reference a task-local
  regular file that already exists. A one-line summary cannot replace this
  artifact path.
- A one-line summary is allowed only for operational status with no reusable
  semantic content. It must not be accepted as semantic stage completion.
- Implementation agents keep their agent-specific `FILES`, `VERIFIED`, and
  related return shapes; this generic three-line example does not replace them.
- Review follow-up completion must reference a review ledger or explicitly state
  that no review comments were in scope. A summary of code changes or passing
  tests cannot replace the review-original-to-disposition ledger.
- When this generic shape applies, include one metrics field (a count, hash, or
  identifier) and no additional lines, prose, or explanations beyond the three
  fields. Agent-specific compact contracts keep their documented field count.
