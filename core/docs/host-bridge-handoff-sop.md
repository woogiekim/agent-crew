# Host Bridge Handoff SOP (1-pager)

Date: 2026-05-23

This SOP covers the common runtime state:

`BLOCKER: host AI bridge has not completed this handoff`

## 1) What happened?

This means `crew run` finished writing supervisor handoff state, but the host
bridge did not auto-complete the task to `completed` in this execution context.

- This is normal in non-hosted/native runtime contexts.
- The same task can be marked complete manually (`crew repair`).

## 2) Immediate operator flow (recommended)

1. Get task artifacts from the run output:

```bash
# Capture TASK_ID and TASK_DIR from run output
TASK_ID=<from_crew_run_output>
TASK_DIR=<from_crew_run_output>
```

2. Confirm blocker text:

```bash
# Inspect canonical result for the task
cat "${TASK_DIR}/result.md"
```

3. If this is intentionally manual/non-hosted execution:

```bash
# Finish task manually after writing a short summary
crew repair "${TASK_ID}" --status completed --note "<summary>"
```

## 3) Auto-complete setup

If you expect host auto-completion:

```bash
# Option A: persistent env in runtime shell profile
export AGENT_CREW_HOST_BRIDGE_COMMAND="your-host-bridge-command"
```

```bash
# Option B: one-off invocation
crew run "your task" --host-bridge-command "your-host-bridge-command"
```

Then re-check:

```bash
crew status --json --task-id "${TASK_ID}"
crew telemetry --format json --task-id "${TASK_ID}"
```

## 4) Recurring blocker diagnosis

When the same blocker repeats in normal hosted runs, collect evidence first:

```bash
# Structured infra report for recurring bridge blockers
crew report auto --summary "host bridge blocker pattern"
```

Use this to verify:

- is host bridge command valid in the current shell/runtime,
- whether host adapter actually received handoff context,
- whether runner is blocked before tool invocation.

## 5) Escalation policy

- If there is no task-impacting data loss and the run is blocked: execute
  `crew repair`.
- If this appears after code changes: re-run the task with `--host-bridge-command`
  once, then compare diagnostics before retrying normal flow.
- If blocked tasks appear with no remediation and no test data impact: pause and
  resolve bridge integration before proceeding to merge/deploy.

## 6) One-line checklist (operator memory)

- Blocker text 확인 (`result.md`)
- Task is expected to be hosted?  
  - Yes → bridge command 점검 후 재실행
  - No → `crew repair ...`
- `crew status --json`, `crew telemetry --format json`
- 반복 발생 시 `crew report auto ...` 실행
