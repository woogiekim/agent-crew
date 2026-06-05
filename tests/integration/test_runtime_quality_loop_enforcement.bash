#!/usr/bin/env bash
# E2E: runtime completion paths fail closed for mutating tasks unless the
# host bridge leaves pipeline-level TDD/review/rework/re-review evidence.

set -u
source "$(dirname "$0")/../shell/_lib.bash"
set +e

CREW="${REPO_ROOT}/core/bin/crew"
CHECKER="${REPO_ROOT}/core/scripts/quality-loop-check.py"
TMP_HOME=$(make_tmp)
TMP_PROJECT=$(make_tmp)

it "fake-host cannot complete mutating implementation without quality loop"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" run \
  --fake-host-result completed \
  "Implement runtime quality loop enforcement" 2>&1)
rc=$?
assert_exit 3 "${rc}"

it "fake-host mutating completion reports quality-loop blocker"
assert_contains "${out}" "BLOCKER: missing_quality_loop_pipeline"

FAKE_BLOCKED_TASK_DIR=$(printf '%s\n' "${out}" | awk -F': ' '/^TASK_DIR:/ {print $2; exit}')

it "fake-host quality block records runtime quality check evidence"
assert_file_exists "${FAKE_BLOCKED_TASK_DIR}/context/quality-loop-runtime-check.json"

it "fake-host can complete explicit read-only validation without quality loop"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" run \
  --fake-host-result completed \
  "Test generic fake-host read-only hosted validation" 2>&1)
rc=$?
assert_exit 0 "${rc}"
assert_contains "${out}" "STATUS: completed"
assert_not_contains "${out}" "missing_quality_loop_pipeline"

it "fake-host can complete read-only validation with non-mutating constraints"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" run \
  --fake-host-result completed \
  "Hosted Codex E2E validation: complete this existing agent-crew handoff as a read-only workflow, verify repository status only, do not edit files, do not commit, do not push, and record completion evidence without crew repair." 2>&1)
rc=$?
assert_exit 0 "${rc}"
assert_contains "${out}" "STATUS: completed"
assert_not_contains "${out}" "missing_quality_loop_pipeline"

it "zero-exit host bridge cannot complete mutating task without quality loop"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" \
  AGENT_CREW_HOST_BRIDGE_COMMAND=true \
  bash "${CREW}" run "Implement auto bridge quality loop enforcement" 2>&1)
rc=$?
assert_exit 3 "${rc}"

it "zero-exit host bridge reports quality-blocked status"
assert_contains "${out}" "HOST_BRIDGE: quality_blocked"

BLOCKED_TASK_DIR=$(printf '%s\n' "${out}" | awk -F': ' '/^TASK_DIR:/ {print $2; exit}')

it "quality-blocked task records runtime quality check evidence"
assert_file_exists "${BLOCKED_TASK_DIR}/context/quality-loop-runtime-check.json"

BRIDGE_SCRIPT="$(make_tmp)/quality_bridge.py"
cat > "${BRIDGE_SCRIPT}" <<'PY'
import json
import os
from pathlib import Path

task_dir = Path(os.environ["AGENT_CREW_TASK_DIR"])
task_id = os.environ["AGENT_CREW_TASK_ID"]
session_id = task_id.rsplit("-", 1)[0]
context = task_dir / "context"
context.mkdir(parents=True, exist_ok=True)

(context / "tdd_log.md").write_text(
    "TDD: RED -> GREEN -> REFACTOR. 6 tests passed.\n",
    encoding="utf-8",
)
(context / "review.md").write_text(
    "REVIEW: APPROVED QUALITY_METRICS: context/quality-metrics.json after remediation.\n",
    encoding="utf-8",
)
(context / "quality-metrics.json").write_text(json.dumps({
    "schema_version": 1,
    "hallucination_detected": False,
    "rollback_performed": False,
    "human_intervention_required": False,
    "factuality_review": "passed",
    "evidence_paths": ["context/review.md"],
}) + "\n", encoding="utf-8")

(task_dir / "pipeline.json").write_text(json.dumps({
    "schema_version": 1,
    "task": "Implement auto bridge quality loop enforcement",
    "stages": [
        {"agents": ["backend"], "tdd_parallel": True},
        "reviewer"
    ],
    "completed_stages": 2,
    "stage_agent_status": {
        "1": {"test-writer": "completed", "backend": "completed"},
        "2": {"reviewer": "completed"}
    }
}, indent=2) + "\n", encoding="utf-8")

rows = [
    ("STAGE_DONE", 1, "test-writer", 1, "TDD RED GREEN, 3 tests passed"),
    ("STAGE_DONE", 1, "backend", 1, "backend - N/A"),
    ("STAGE_DONE", 2, "reviewer", 1, "REVIEW: NEEDS_CHANGES"),
    ("STAGE_DONE", 1, "test-writer", 2, "TDD REFACTOR, 6 tests passed"),
    ("STAGE_DONE", 1, "backend", 2, "backend remediation - N/A"),
    ("STAGE_DONE", 2, "reviewer", 2, "REVIEW: APPROVED QUALITY_METRICS: context/quality-metrics.json"),
]
with (task_dir / "progress.buffer.jsonl").open("w", encoding="utf-8") as handle:
    for idx, (event, stage, agent, attempt, detail) in enumerate(rows):
        handle.write(json.dumps({
            "ts": f"2026-05-22T00:00:0{idx}Z",
            "trace_id": f"{session_id}.{task_id}.{stage}.{attempt}",
            "task_id": task_id,
            "session_id": session_id,
            "event": event,
            "stage": stage,
            "agent": agent,
            "attempt": attempt,
            "status": "completed",
            "detail": detail,
            "files": ["tests/test_quality_loop_bridge.py"] if agent == "test-writer" else []
        }) + "\n")

(task_dir / "result.md").write_text(
    "# Implement auto bridge quality loop enforcement\n\n"
    "STATUS: completed\n"
    f"TASK_ID: {task_id}\n"
    "MEASUREMENTS: 6 tests passed, 1 retry, 1 reviewer re-approval\n"
    "EVIDENCE: context/tdd_log.md\n"
    "EVIDENCE: context/review.md\n"
    "UNCERTAINTY: Synthetic host bridge fixture stands in for the host prompt runtime.\n",
    encoding="utf-8",
)
PY

it "host bridge can complete mutating task after writing quality loop trace"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" \
  AGENT_CREW_HOST_BRIDGE_COMMAND="python3 ${BRIDGE_SCRIPT}" \
  bash "${CREW}" run "Implement auto bridge quality loop enforcement" 2>&1)
rc=$?
assert_exit 0 "${rc}"

TASK_DIR=$(printf '%s\n' "${out}" | awk -F': ' '/^TASK_DIR:/ {print $2; exit}')

it "accepted host bridge records auto-completion"
assert_contains "${out}" "HOST_BRIDGE: auto_completed"

it "accepted host bridge preserves quality-loop result"
assert_contains "$(cat "${TASK_DIR}/result.md")" "HOST_BRIDGE: auto_completed"

it "quality-loop checker accepts rework cycle from host bridge"
out=$(python3 "${CHECKER}" --task-dir "${TASK_DIR}" --require-rework-cycle --format json 2>&1)
rc=$?
assert_exit 0 "${rc}"

end_report
