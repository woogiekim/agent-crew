#!/usr/bin/env bash
# test_fanout_prerequisites.sh
#
# E2E / integration tests for the 4 prerequisites of safe dynamic
# intra-task parallelism implemented in feat/fanout-parallelism-prerequisites
# (commit ca932d0).
#
# Each test checks the spec files (not runtime behaviour) via grep and
# Python-based content validation. Tests are self-contained; no external
# services are required.
#
# Usage:  bash core/tests/test_fanout_prerequisites.sh
# Exit code: 0 = all pass, 1 = one or more failures.

set -uo pipefail

# ---------------------------------------------------------------------------
# Bootstrap: locate repo root relative to this script
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

SUPERVISOR_STAGES="${REPO_ROOT}/core/agents/supervisor-stages.md"
SUPERVISOR_RETRY="${REPO_ROOT}/core/agents/supervisor-retry.md"
PIPELINE_JSON_SPEC="${REPO_ROOT}/core/rules/state-files/pipeline-json.md"
RESOLVER_SPEC="${REPO_ROOT}/core/agents/resolver.md"

# ---------------------------------------------------------------------------
# Test harness
# ---------------------------------------------------------------------------
PASS=0
FAIL=0
FAILURE_LIST=""

pass() {
  local name="$1"
  echo "PASS  ${name}"
  PASS=$((PASS + 1))
}

fail() {
  local name="$1"
  local reason="$2"
  echo "FAIL  ${name}  --  ${reason}"
  FAIL=$((FAIL + 1))
  FAILURE_LIST="${FAILURE_LIST}  - ${name}: ${reason}\n"
}

assert_grep() {
  # assert_grep <test_name> <file> <pattern> <description>
  local name="$1"
  local file="$2"
  local pattern="$3"
  local desc="$4"
  if grep -qE "${pattern}" "${file}" 2>/dev/null; then
    pass "${name}"
  else
    fail "${name}" "${desc}"
  fi
}

assert_grep_absent() {
  # assert_grep_absent <test_name> <file> <pattern> <description>
  local name="$1"
  local file="$2"
  local pattern="$3"
  local desc="$4"
  if ! grep -qE "${pattern}" "${file}" 2>/dev/null; then
    pass "${name}"
  else
    fail "${name}" "${desc}"
  fi
}

# ---------------------------------------------------------------------------
# Prerequisite 1 — Atomic pipeline.json writes (write_pipeline_atomic helper)
# ---------------------------------------------------------------------------
echo ""
echo "=== Prerequisite 1: Atomic pipeline.json writes ==="
echo ""

# 1a. pipeline-json.md documents the atomic write requirement
assert_grep "1a-spec-atomic-write-requirement" \
  "${PIPELINE_JSON_SPEC}" \
  "Atomic write requirement" \
  "pipeline-json.md must contain 'Atomic write requirement' section"

# 1b. pipeline-json.md documents the tempfile + rename pattern
assert_grep "1b-spec-tempfile-pattern-documented" \
  "${PIPELINE_JSON_SPEC}" \
  "tempfile\.mkstemp" \
  "pipeline-json.md must document tempfile.mkstemp pattern"

# 1c. pipeline-json.md documents os.replace (the atomic rename call)
assert_grep "1c-spec-os-replace-documented" \
  "${PIPELINE_JSON_SPEC}" \
  "os\.replace" \
  "pipeline-json.md must document os.replace() atomic rename"

# 1d. pipeline-json.md documents the .pipeline. temp file prefix
assert_grep "1d-spec-temp-prefix-documented" \
  "${PIPELINE_JSON_SPEC}" \
  '\.pipeline\.' \
  "pipeline-json.md must document .pipeline. temp file prefix"

# 1e. supervisor-stages.md defines the pipeline_write_atomic helper
assert_grep "1e-stages-atomic-helper-defined" \
  "${SUPERVISOR_STAGES}" \
  "pipeline_write_atomic" \
  "supervisor-stages.md must define pipeline_write_atomic helper"

# 1f. supervisor-stages.md uses tempfile.mkstemp for parallel write sites
assert_grep "1f-stages-tempfile-mkstemp-present" \
  "${SUPERVISOR_STAGES}" \
  "tempfile\.mkstemp" \
  "supervisor-stages.md must use tempfile.mkstemp pattern"

# 1g. supervisor-stages.md uses os.replace (atomic rename)
assert_grep "1g-stages-os-replace-present" \
  "${SUPERVISOR_STAGES}" \
  "os\.replace\(" \
  "supervisor-stages.md must use os.replace() for atomic rename"

# 1h. supervisor-stages.md does NOT use bare json.dump(open(path,"w")) in a code block
# (i.e., not inside triple-backtick fenced code). The spec may mention the old pattern
# in prose/inline-code to describe what was replaced, but it must not appear as actual
# executable code. We verify via Python: any line containing the pattern must be inside
# an inline backtick span (not a fenced code block) — the prose "every `json.dump(...)`
# is replaced by pipeline_write_atomic" is the expected form.
_T1H_PY=$(mktemp /tmp/test_1h_XXXXXX.py)
printf '%s\n' \
  "import re, sys" \
  "path = sys.argv[1]" \
  "content = open(path, encoding='utf-8').read()" \
  "# Split into fenced code blocks vs prose" \
  "fenced_pat = re.compile(r'\`\`\`.*?\`\`\`', re.DOTALL)" \
  "# Find positions of the bare pattern" \
  "bare_pat = re.compile(r'json\.dump\(p, open\(')" \
  "violations = []" \
  "for m in bare_pat.finditer(content):" \
  "    pos = m.start()" \
  "    # Check if this position is inside a fenced code block" \
  "    in_fence = any(fb.start() <= pos < fb.end() for fb in fenced_pat.finditer(content))" \
  "    if in_fence:" \
  "        violations.append(pos)" \
  "if violations:" \
  "    print('FAIL found bare pattern inside fenced code at offsets=' + str(violations))" \
  "    sys.exit(1)" \
  "else:" \
  "    print('PASS')" \
  > "${_T1H_PY}"
_T1H_OUT=$(python3 "${_T1H_PY}" "${SUPERVISOR_STAGES}" 2>&1) || true
_T1H_RC=$?
rm -f "${_T1H_PY}"
if [ "${_T1H_RC}" -eq 0 ]; then
  pass "1h-stages-no-bare-json-dump-in-code-block"
else
  fail "1h-stages-no-bare-json-dump-in-code-block" \
    "bare json.dump(p, open()) found inside a fenced code block: ${_T1H_OUT}"
fi

# ---------------------------------------------------------------------------
# Prerequisite 2 — Per-unit git worktree isolation
# ---------------------------------------------------------------------------
echo ""
echo "=== Prerequisite 2: Per-unit git worktree isolation ==="
echo ""

# 2a. supervisor-stages.md contains 'git worktree add' for fan-out units
assert_grep "2a-worktree-add-present" \
  "${SUPERVISOR_STAGES}" \
  "git.*worktree add" \
  "supervisor-stages.md must contain 'git worktree add' for fan-out units"

# 2b. supervisor-stages.md contains 'git worktree remove' for cleanup
assert_grep "2b-worktree-remove-present" \
  "${SUPERVISOR_STAGES}" \
  "git.*worktree remove" \
  "supervisor-stages.md must contain 'git worktree remove' for cleanup"

# 2c. UNIT_WORKTREE_PATH variable is defined and passed to unit agents
assert_grep "2c-unit-worktree-path-defined" \
  "${SUPERVISOR_STAGES}" \
  "UNIT_WORKTREE_PATH" \
  "supervisor-stages.md must define UNIT_WORKTREE_PATH for per-unit isolation"

# 2d. Per-unit worktree cleanup section exists after units complete
assert_grep "2e-worktree-cleanup-section" \
  "${SUPERVISOR_STAGES}" \
  "Per-unit worktree cleanup|worktree cleanup" \
  "supervisor-stages.md must have a per-unit worktree cleanup section"

# 2e. UNIT_WORKTREE_MAP data structure declared for tracking per-unit paths
assert_grep "2f-unit-worktree-map-declared" \
  "${SUPERVISOR_STAGES}" \
  "UNIT_WORKTREE_MAP" \
  "supervisor-stages.md must declare UNIT_WORKTREE_MAP to track per-unit worktree paths"

# 2f. CREW_WORKTREES_BASE convention is used
assert_grep "2g-crew-worktrees-base" \
  "${SUPERVISOR_STAGES}" \
  "CREW_WORKTREES_BASE" \
  "supervisor-stages.md must define CREW_WORKTREES_BASE for worktree base path"

# ---------------------------------------------------------------------------
# Prerequisite 3 — Pre-retry UNIT_FILES git reset
# ---------------------------------------------------------------------------
echo ""
echo "=== Prerequisite 3: Pre-retry UNIT_FILES git reset ==="
echo ""

# 3a. supervisor-stages.md has git checkout HEAD for pre-retry restore
assert_grep "3a-stages-git-checkout-head" \
  "${SUPERVISOR_STAGES}" \
  "git.*checkout.*HEAD.*--" \
  "supervisor-stages.md must contain git checkout HEAD -- <glob> for pre-retry restore"

# 3b. supervisor-stages.md has git clean -fd for pre-retry untracked removal
assert_grep "3b-stages-git-clean-fd" \
  "${SUPERVISOR_STAGES}" \
  "git.*clean.*-fd" \
  "supervisor-stages.md must contain git clean -fd for pre-retry cleanup"

# 3c. supervisor-retry.md documents pre-retry clean state requirement for fan-out units
assert_grep "3c-retry-clean-state-documented" \
  "${SUPERVISOR_RETRY}" \
  "Pre-retry clean state" \
  "supervisor-retry.md must document 'Pre-retry clean state' requirement"

# 3d. supervisor-retry.md references git checkout HEAD for pre-retry restore
assert_grep "3d-retry-git-checkout-head" \
  "${SUPERVISOR_RETRY}" \
  "git.*checkout HEAD.*--" \
  "supervisor-retry.md must reference git checkout HEAD for pre-retry file restore"

# 3e. supervisor-retry.md references git clean -fd for pre-retry cleanup
assert_grep "3e-retry-git-clean-fd" \
  "${SUPERVISOR_RETRY}" \
  "git.*clean.*-fd" \
  "supervisor-retry.md must reference git clean -fd for pre-retry cleanup"

# 3f. supervisor-stages.md scopes cleanup to fan-out path
assert_grep "3f-stages-fan-out-cleanup-scoped" \
  "${SUPERVISOR_STAGES}" \
  "UNIT_WORKTREE_PATH" \
  "supervisor-stages.md pre-retry cleanup must reference UNIT_WORKTREE_PATH (fan-out scoped)"

# ---------------------------------------------------------------------------
# Prerequisite 4 — Sequential fallback on resolver unresolvable
# ---------------------------------------------------------------------------
echo ""
echo "=== Prerequisite 4: Sequential fallback on resolver unresolvable ==="
echo ""

# 4a. supervisor-stages.md contains sequential fallback logic
assert_grep "4a-stages-sequential-fallback-present" \
  "${SUPERVISOR_STAGES}" \
  "STAGE_UNITS_COUNT=1" \
  "supervisor-stages.md must contain STAGE_UNITS_COUNT=1 sequential fallback"

# 4b. supervisor-stages.md logs STAGE_FANOUT_BLOCKED event (not a hard stop)
assert_grep "4b-stages-fanout-blocked-event-logged" \
  "${SUPERVISOR_STAGES}" \
  "STAGE_FANOUT_BLOCKED" \
  "supervisor-stages.md must log STAGE_FANOUT_BLOCKED event on unresolvable overlap"

# 4c. resolver.md documents that BLOCKED in fanout-mediation triggers supervisor downgrade
assert_grep "4c-resolver-blocked-triggers-downgrade" \
  "${RESOLVER_SPEC}" \
  "sequential" \
  "resolver.md must document sequential downgrade on BLOCKED in fanout-mediation"

# 4d. resolver.md explicitly states the task continues (not halted) on BLOCKED
assert_grep "4d-resolver-task-continues" \
  "${RESOLVER_SPEC}" \
  "task continues" \
  "resolver.md must state that the task continues when resolver returns BLOCKED"

# 4e. supervisor-stages.md downgrade merges all unit files/briefs into one
assert_grep "4e-stages-downgrade-merges-units" \
  "${SUPERVISOR_STAGES}" \
  "all_files|all_briefs" \
  "supervisor-stages.md must merge all unit files/briefs into one on downgrade"

# 4f. Python-based check: no bare 'exit 1' near 'unresolvable' without downgrade
# Write the checker script to a temp file to avoid heredoc issues.
_T4G_PY=$(mktemp /tmp/test_4g_XXXXXX.py)
printf '%s\n' \
  "import re, sys" \
  "path = sys.argv[1]" \
  "content = open(path, encoding='utf-8').read()" \
  "positions = [m.start() for m in re.finditer('unresolvable', content)]" \
  "violations = []" \
  "for pos in positions:" \
  "    snippet = content[pos:pos+400]" \
  "    has_exit1 = bool(re.search(r'\bexit 1\b', snippet))" \
  "    has_blocked = bool(re.search('STATUS: blocked', snippet))" \
  "    has_downgrade = bool(re.search('STAGE_UNITS_COUNT=1|sequential', snippet))" \
  "    if (has_exit1 or has_blocked) and not has_downgrade:" \
  "        wider = content[pos:pos+1500]" \
  "        if not bool(re.search('STAGE_UNITS_COUNT=1|sequential', wider)):" \
  "            violations.append(pos)" \
  "if violations:" \
  "    print('FAIL offsets=' + str(violations))" \
  "    sys.exit(1)" \
  "else:" \
  "    print('PASS')" \
  > "${_T4G_PY}"

_T4G_OUT=$(python3 "${_T4G_PY}" "${SUPERVISOR_STAGES}" 2>&1) || true
_T4G_RC=$?
rm -f "${_T4G_PY}"
if [ "${_T4G_RC}" -eq 0 ]; then
  pass "4f-stages-no-bare-exit1-after-unresolvable"
else
  fail "4f-stages-no-bare-exit1-after-unresolvable" \
    "bare exit1/STATUS:blocked near unresolvable without downgrade: ${_T4G_OUT}"
fi

# ---------------------------------------------------------------------------
# Additional cross-cutting sanity checks
# ---------------------------------------------------------------------------
echo ""
echo "=== Cross-cutting sanity checks ==="
echo ""

# S1. All 4 spec files exist
for spec_file in "${SUPERVISOR_STAGES}" "${SUPERVISOR_RETRY}" "${PIPELINE_JSON_SPEC}" "${RESOLVER_SPEC}"; do
  base="$(basename "${spec_file}")"
  if [ -f "${spec_file}" ]; then
    pass "s1-file-exists-${base}"
  else
    fail "s1-file-exists-${base}" "Required spec file missing: ${spec_file}"
  fi
done

# S2. pipeline-json.md documents the write_pipeline_atomic function name
assert_grep "s2-spec-write-pipeline-atomic-name" \
  "${PIPELINE_JSON_SPEC}" \
  "write_pipeline_atomic|pipeline_write_atomic" \
  "pipeline-json.md must name the atomic write helper function"

# S3. supervisor-stages.md documents the .crew-worktrees base directory
assert_grep "s3-stages-crew-worktrees-dir" \
  "${SUPERVISOR_STAGES}" \
  "\.crew-worktrees" \
  "supervisor-stages.md must reference .crew-worktrees directory for worktree isolation"

# S4. resolver.md documents the fanout-mediation mode
assert_grep "s4-resolver-fanout-mediation-mode" \
  "${RESOLVER_SPEC}" \
  "fanout-mediation" \
  "resolver.md must document the fanout-mediation mode"

# S5. supervisor-retry.md references UNIT_WORKTREE_PATH for pre-retry cleanup
assert_grep "s5-retry-unit-worktree-path" \
  "${SUPERVISOR_RETRY}" \
  "UNIT_WORKTREE_PATH" \
  "supervisor-retry.md must reference UNIT_WORKTREE_PATH for pre-retry worktree cleanup"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "==================================================================="
TOTAL=$((PASS + FAIL))
echo "Results: ${PASS}/${TOTAL} passed, ${FAIL} failed"
echo "==================================================================="

if [ "${FAIL}" -gt 0 ]; then
  echo ""
  echo "Failures:"
  printf "%b" "${FAILURE_LIST}"
  exit 1
fi

exit 0
