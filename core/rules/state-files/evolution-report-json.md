# context/evolution-report.json - Post-Task Evolution Report

`context/evolution-report.json` is the report-only sidecar produced after a
task closes out. It records reusable-work signals for later human or
registry-reviewed analysis. It does **not** create, register, select, or mutate
any agent-crew asset.

## File Location

```text
${STATE_DIR}/tasks/${TASK_ID}/context/evolution-report.json
${STATE_DIR}/tasks/${TASK_ID}/context/evolution-report.md
```

The JSON file is the machine-readable source of truth. The markdown file is a
human-readable rendering for `crew:run` and `crew:status --collect` summaries.

## Producer

`core/scripts/evolution-analyzer.py` writes both artifacts when invoked with:

```bash
python3 "${AGENT_CREW_HOME}/scripts/evolution-analyzer.py" \
  --state-dir "${STATE_DIR}" \
  --task-dir "${TASK_DIR}" \
  --json-output "${TASK_DIR}/context/evolution-report.json" \
  --markdown-output "${TASK_DIR}/context/evolution-report.md"
```

Supervisor Phase 3 invokes the analyzer after the AAR debrief. Failure is
non-blocking: a task that already completed must not become blocked because the
learning report could not be written.

## Schema

JSON Schema: `${AGENT_CREW_HOME}/schemas/evolution-report.schema.json`.

The first implementation supports only:

```json
{
  "generation_mode": "report_only",
  "guardrails": {
    "asset_writes": "disabled",
    "generator_invoked": false,
    "verification_bypass": false
  }
}
```

`asset_candidates` is intentionally empty in report-only mode. Single-task
signals that look reusable are recorded under `observed_patterns` and, when
useful, `rejected_candidates` with `rejection_reason:
insufficient_repeated_evidence`.

## Consumer Contract

Consumers MUST tolerate absence. Older task directories and disabled
installations have no evolution report.

When present, consumers may display the report in summaries or use it as
evidence for future proposal analysis. Consumers MUST NOT treat it as proof
that an asset was generated. Generated assets require a later approval-gated
proposal/registry workflow with its own schema and validation.
