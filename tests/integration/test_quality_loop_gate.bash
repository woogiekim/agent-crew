#!/usr/bin/env bash
# E2E: manual fallback completion requires quality-loop evidence for mutating tasks.

set -u
source "$(dirname "$0")/../shell/_lib.bash"
set +e

CREW="${REPO_ROOT}/core/bin/crew"
REPORT_CHECK="${REPO_ROOT}/core/scripts/report-quality-check.py"
TMP_HOME=$(make_tmp)
TMP_PROJECT=$(make_tmp)

it "mutating crew run creates blocked handoff state"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" run "Implement quality loop integration behavior" 2>&1)
rc=$?
assert_exit 3 "${rc}"

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
cat > "${TASK_DIR}/context/review.md" <<'EOF'
REVIEW: APPROVED after remediation.
EOF

it "mutating repair succeeds with TDD and reviewer evidence"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" repair --status completed --note "quality loop completed" "${TASK_ID}" 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "repair result records quality loop pass"
result=$(cat "${TASK_DIR}/result.md")
assert_contains "${result}" "QUALITY_LOOP: passed"

it "repair result records TDD evidence"
assert_contains "${result}" "TDD_EVIDENCE: context/tdd_log.md"

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
assert_exit 3 "${rc}"

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
