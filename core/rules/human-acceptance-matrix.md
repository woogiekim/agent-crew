# Human Acceptance Matrix

User-facing behavior sometimes needs human-observable acceptance evidence in
addition to automated tests. This rule is optional and activated when
`pipeline.json` sets:

```json
{ "requires_human_acceptance": true }
```

When active, QA or the verifier writes one of:

- `{TASK_DIR}/context/human-acceptance-matrix.md`
- `{TASK_DIR}/context/human-acceptance-matrix.json`

## Required Matrix Columns

| Field | Meaning |
|---|---|
| Requirement | PRD acceptance criterion, user journey, or visible behavior. |
| Manual acceptance step | Concrete action a human or browser verifier performs. |
| Expected result | Observable pass condition. |
| Round result | `passed`, `failed`, `blocked`, or `not_applicable`. |
| Evidence | Screenshot, command output, log path, browser trace, or note. |
| Automation follow-up | Whether the manual check should become an automated regression. |

## Completion Gate

The runtime quality-loop gate rejects a completed mutating task with
`missing_human_acceptance_matrix` when `requires_human_acceptance` is true and
neither matrix artifact exists.

Manual acceptance does not replace TDD, review, coverage, or security checks.
It records UX and workflow judgments that cannot be fully proven by unit tests.
