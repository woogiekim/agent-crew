#!/usr/bin/env bash
# E2E: manual fallback completion requires quality-loop evidence for mutating tasks.

set -u
source "$(dirname "$0")/../shell/_lib.bash"
set +e

CREW="${REPO_ROOT}/core/bin/crew"
REPORT_CHECK="${REPO_ROOT}/core/scripts/report-quality-check.py"
TMP_HOME=$(make_tmp)
TMP_PROJECT=$(make_tmp)

it "mutating crew run creates internal handoff state"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" run "Implement quality loop integration behavior" 2>&1)
rc=$?
assert_exit 0 "${rc}"

TASK_DIR=$(printf '%s\n' "${out}" | awk -F': ' '/^TASK_DIR:/ {print $2; exit}')
TASK_ID=$(basename "${TASK_DIR}")

it "mutating repair without TDD/reviewer evidence is blocked"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" repair --status completed --note "manual completion" "${TASK_ID}" 2>&1)
rc=$?
assert_exit 1 "${rc}"

it "blocked repair explains missing quality-loop evidence"
assert_contains "${out}" "BLOCKER: missing_quality_loop_evidence"

mkdir -p "${TASK_DIR}/context"
cat > "${TASK_DIR}/context/tdd_log.md" <<'EOF'
TDD: RED -> GREEN. 3 tests passed.
EOF
cat > "${TASK_DIR}/context/tdd-red.md" <<'EOF'
TDD-RED: focused test failed as expected before implementation.
EOF
cat > "${TASK_DIR}/context/tdd-refactor.md" <<'EOF'
TDD-REFACTOR: refactor review complete; post-refactor tests passed.
EOF
cat > "${TASK_DIR}/context/review.md" <<'EOF'
REVIEW: APPROVED QUALITY_METRICS: context/quality-metrics.json after remediation.
EOF
cat > "${TASK_DIR}/context/quality-metrics.json" <<'EOF'
{"schema_version":1,"hallucination_detected":false,"rollback_performed":false,"human_intervention_required":false,"factuality_review":"passed","evidence_paths":["context/review.md"]}
EOF

it "mutating repair is still blocked when only evidence files exist"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" repair --status completed --note "evidence only" "${TASK_ID}" 2>&1)
rc=$?
assert_exit 1 "${rc}"

it "evidence-only repair explains missing pipeline quality loop"
assert_contains "${out}" "BLOCKER: missing_quality_loop_pipeline"

cat > "${TASK_DIR}/pipeline.json" <<'EOF'
{
  "schema_version": 1,
  "task": "Implement quality loop integration behavior",
  "stages": [
    {"agents": ["backend"], "tdd_parallel": true},
    "reviewer"
  ],
  "completed_stages": 2
}
EOF
cat > "${TASK_DIR}/progress.buffer.jsonl" <<'EOF'
{"ts":"2026-05-22T00:00:00Z","trace_id":"20260522-000000.20260522-000000-0.1.1","task_id":"20260522-000000-0","session_id":"20260522-000000","event":"STAGE_DONE","stage":1,"agent":"test-writer","attempt":1,"status":"completed","detail":"TDD RED GREEN, 3 tests passed","files":[]}
{"ts":"2026-05-22T00:00:01Z","trace_id":"20260522-000000.20260522-000000-0.1.1","task_id":"20260522-000000-0","session_id":"20260522-000000","event":"STAGE_DONE","stage":1,"agent":"backend","attempt":1,"status":"completed","detail":"backend - N/A","files":[]}
{"ts":"2026-05-22T00:00:02Z","trace_id":"20260522-000000.20260522-000000-0.2.1","task_id":"20260522-000000-0","session_id":"20260522-000000","event":"STAGE_DONE","stage":2,"agent":"reviewer","attempt":1,"status":"completed","detail":"REVIEW: NEEDS_CHANGES","files":[]}
{"ts":"2026-05-22T00:00:03Z","trace_id":"20260522-000000.20260522-000000-0.1.2","task_id":"20260522-000000-0","session_id":"20260522-000000","event":"STAGE_DONE","stage":1,"agent":"test-writer","attempt":2,"status":"completed","detail":"TDD REFACTOR, 4 tests passed","files":[]}
{"ts":"2026-05-22T00:00:04Z","trace_id":"20260522-000000.20260522-000000-0.1.2","task_id":"20260522-000000-0","session_id":"20260522-000000","event":"STAGE_DONE","stage":1,"agent":"backend","attempt":2,"status":"completed","detail":"backend remediation - N/A","files":[]}
{"ts":"2026-05-22T00:00:05Z","trace_id":"20260522-000000.20260522-000000-0.2.2","task_id":"20260522-000000-0","session_id":"20260522-000000","event":"STAGE_DONE","stage":2,"agent":"reviewer","attempt":2,"status":"completed","detail":"REVIEW: APPROVED QUALITY_METRICS: context/quality-metrics.json","files":[]}
EOF

it "mutating repair succeeds with TDD and reviewer evidence"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" repair --status completed --note "quality loop completed" "${TASK_ID}" 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "repair result records quality loop pass"
result=$(cat "${TASK_DIR}/result.md")
assert_contains "${result}" "QUALITY_LOOP: passed"

it "repair result records pipeline quality loop pass"
assert_contains "${result}" "PIPELINE_QUALITY_LOOP: passed"

it "repair result records TDD evidence"
assert_contains "${result}" "TDD_EVIDENCE: context/tdd_log.md"

it "repair result records TDD red-phase evidence"
assert_contains "${result}" "TDD_RED_EVIDENCE: context/tdd-red.md"

it "repair result records TDD refactor-phase evidence"
assert_contains "${result}" "TDD_REFACTOR_EVIDENCE: context/tdd-refactor.md"

it "repair result records reviewer evidence"
assert_contains "${result}" "REVIEW_EVIDENCE: context/review.md"

it "report quality check accepts completed implementation with quality-loop evidence"
out=$(python3 "${REPORT_CHECK}" --report "${TASK_DIR}/result.md" --task-dir "${TASK_DIR}" --format json 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "quality check reports TDD evidence path"
assert_contains "${out}" '"context/tdd_log.md"'

it "quality check reports reviewer evidence path"
assert_contains "${out}" '"context/review.md"'

it "explicit quality bypass is recorded for mutating manual completion"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" run "Implement emergency bypass behavior" 2>&1)
rc=$?
assert_exit 0 "${rc}"

BYPASS_TASK_DIR=$(printf '%s\n' "${out}" | awk -F': ' '/^TASK_DIR:/ {print $2; exit}')
BYPASS_TASK_ID=$(basename "${BYPASS_TASK_DIR}")
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" repair \
  --status completed \
  --note "manual bypass completion" \
  --quality-bypass-reason "reviewer unavailable during emergency validation" \
  "${BYPASS_TASK_ID}" 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "bypass result is explicit"
bypass_result=$(cat "${BYPASS_TASK_DIR}/result.md")
assert_contains "${bypass_result}" "QUALITY_LOOP: bypassed"

it "bypass reason is written"
assert_contains "${bypass_result}" "QUALITY_BYPASS_REASON: reviewer unavailable during emergency validation"

end_report
