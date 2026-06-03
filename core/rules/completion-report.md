# Completion Report Format

Return to parent within 3 lines. Do not re-quote file contents or add prose.
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

- `STATUS` must be the first field and must be `completed`
- Include one artifact field (a file path or one-line summary)
- Include one metrics field (a count, hash, or identifier)
- No additional lines, prose, or explanations beyond these three
