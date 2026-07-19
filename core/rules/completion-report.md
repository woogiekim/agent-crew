# Completion Report Format

Return to parent within 3 lines when the agent-specific return contract does not
define another compact structured shape. Do not re-quote file contents or add
prose.
When the stage produced analysis, judgment, review, or planning artifacts, the
artifact referenced by `{ARTIFACT_FIELD}` must already satisfy
`core/rules/evidence-grounded-reasoning.md`: cited first-party evidence and an
explicit evidence-to-inference-to-conclusion flow are required before this
completion report may be returned.

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
- When this generic shape applies, include one metrics field (a count, hash, or
  identifier) and no additional lines, prose, or explanations beyond the three
  fields. Agent-specific compact contracts keep their documented field count.
