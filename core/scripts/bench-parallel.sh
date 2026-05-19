#!/usr/bin/env bash
# bench-parallel.sh — dry-run benchmark for parallelization roadmap Phases 1-3.
#
# Validates that the dispatch contract in `core/agents/supervisor-stages.md`
# (Single Agent / Parallel Agents / TDD Parallel / Sub-Task Fan-Out) maps
# each mock pipeline.json variant to the expected agent-spawn count, and
# measures the Phase 1d prefetch shell block (from
# `core/agents/supervisor-bootstrap.md`) end-to-end.
#
# Scope:
# - NO real agent spawns. Spawn counts come from parsing the fixture
#   pipeline.json files against the same normalization logic Phase 2
#   runs at stage entry.
# - The prefetch measurement spawns a real background shell job over
#   real fixture files; this exercises the OS page cache warm + PID
#   cleanup path without invoking any LLM-bound tool.
#
# Re-run anywhere via:
#   bash core/scripts/bench-parallel.sh
#
# Exits 0 on success; non-zero only if the harness itself fails (e.g.
# missing python3, missing fixtures). Variant spawn-count mismatches
# are surfaced as failures in the summary table but do not abort the
# harness — the goal is to print the complete diagnostic.

set -u

# ---------------------------------------------------------------------------
# Resolve paths relative to the script location so the harness can be
# invoked from any working directory.
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
FIXTURES_DIR="${SCRIPT_DIR}/bench-fixtures"

if [ ! -d "${FIXTURES_DIR}" ]; then
  echo "FATAL: fixtures directory missing at ${FIXTURES_DIR}" >&2
  exit 2
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "FATAL: python3 is required for spawn-count computation" >&2
  exit 2
fi

# ---------------------------------------------------------------------------
# Helper — compute dispatch spawn count for a pipeline.json variant.
#
# Mirrors the normalization block in
# `core/agents/supervisor-stages.md` § TDD Parallel Dispatch and the
# fan-out dispatch contract in § Sub-Task Fan-Out Dispatch:
#
#   STAGE_UNITS_COUNT >= 2  → fan-out path (N implementer spawns,
#                              +1 test-writer when STAGE_TDD_PARALLEL == 1)
#   STAGE_UNITS_COUNT  < 2  AND STAGE_TDD_PARALLEL == 1
#                              → TDD parallel path (1 test-writer + 1 impl)
#   else                    → bare path (len(agents) spawns)
#
# Per-stage counts are summed; the total is the harness's "spawn count
# for the variant" (Phase 2 only — no Phase 1 / Phase 3 spawns).
# ---------------------------------------------------------------------------
compute_spawn_count() {
  local pipeline_path="$1"
  python3 - "${pipeline_path}" <<'PY'
import json, sys
path = sys.argv[1]
try:
    data = json.load(open(path))
except Exception as e:
    print(f"ERROR: cannot parse {path}: {e}", file=sys.stderr)
    sys.exit(2)

stages = data.get("stages", []) or []
total = 0
per_stage = []
for idx, stage in enumerate(stages, 1):
    if isinstance(stage, str):
        agents = [stage]; tdd = False; units = 0
    elif isinstance(stage, list):
        agents = list(stage); tdd = False; units = 0
    elif isinstance(stage, dict):
        agents = list(stage.get("agents", []) or [])
        tdd    = bool(stage.get("tdd_parallel", False))
        units  = len(stage.get("parallelizable_units", []) or [])
    else:
        agents = []; tdd = False; units = 0

    if units >= 2:
        # Fan-out path: N implementer spawns of agents[0]. +1 test-writer
        # in combined mode.
        count = units + (1 if tdd else 0)
        kind = f"fanout(units={units}, tdd={tdd})"
    elif tdd:
        # TDD parallel: 1 test-writer + 1 implementer (MVP scope keeps
        # `agents` to a single entry; if the planner emits more, only
        # the first is co-spawned with test-writer per
        # `supervisor-stages.md` § TDD Parallel Dispatch step 3).
        count = 1 + min(1, max(1, len(agents)))
        kind = f"tdd_parallel(agents={agents})"
    else:
        count = len(agents) if agents else 0
        kind = f"bare(agents={agents})"
    per_stage.append((idx, count, kind))
    total += count

print(total)
for i, c, k in per_stage:
    print(f"  stage {i}: {c} spawn(s)  [{k}]", file=sys.stderr)
PY
}

# ---------------------------------------------------------------------------
# Section 1 — dispatch dry-run for each variant.
# ---------------------------------------------------------------------------
echo "============================================================"
echo " bench-parallel.sh — parallelization roadmap dispatch report"
echo " repo root: ${REPO_ROOT}"
echo " fixtures:  ${FIXTURES_DIR}"
echo "============================================================"
echo

VARIANTS=(
  "A|baseline|mock-pipeline-baseline.json|1"
  "B|tdd_parallel|mock-pipeline-tdd.json|2"
  "C|fanout|mock-pipeline-fanout.json|3"
  "BC|tdd+fanout|mock-pipeline-tdd-fanout.json|4"
)

printf "%-4s %-14s %-40s %-10s %-10s %s\n" \
       "VAR" "MODE" "FIXTURE" "EXPECTED" "ACTUAL" "RESULT"
printf "%-4s %-14s %-40s %-10s %-10s %s\n" \
       "----" "--------------" "----------------------------------------" \
       "---------" "---------" "------"

ANY_MISMATCH=0
for entry in "${VARIANTS[@]}"; do
  IFS='|' read -r var mode fname expected <<<"${entry}"
  fixture="${FIXTURES_DIR}/${fname}"
  if [ ! -f "${fixture}" ]; then
    printf "%-4s %-14s %-40s %-10s %-10s %s\n" \
      "${var}" "${mode}" "${fname}" "${expected}" "n/a" "MISSING_FIXTURE"
    ANY_MISMATCH=1
    continue
  fi
  actual=$(compute_spawn_count "${fixture}" 2>/tmp/bench-stage-${var}.txt)
  if [ "${actual}" = "${expected}" ]; then
    result="OK"
  else
    result="MISMATCH"
    ANY_MISMATCH=1
  fi
  printf "%-4s %-14s %-40s %-10s %-10s %s\n" \
    "${var}" "${mode}" "${fname}" "${expected}" "${actual}" "${result}"
done

echo
echo "Per-stage breakdown:"
for entry in "${VARIANTS[@]}"; do
  IFS='|' read -r var mode fname expected <<<"${entry}"
  if [ -s "/tmp/bench-stage-${var}.txt" ]; then
    echo "  Variant ${var} (${mode}):"
    sed 's/^/    /' "/tmp/bench-stage-${var}.txt"
  fi
done
echo

# ---------------------------------------------------------------------------
# Section 1b — task-cardinality scenario matrix.
#
# Issue #68 needs N=1,2,4,8 coverage even before a live host benchmark exists.
# This matrix is still token-free: it combines the validated per-task fixture
# widths above with the orchestrator's task cardinality rules.
# ---------------------------------------------------------------------------
echo "Task-cardinality scenario matrix (dry-run):"
printf "%-4s %-10s %-12s %-12s %-12s %-12s\n" \
       "N" "WORKTREES" "BASELINE" "TDD" "FANOUT" "COMBINED"
printf "%-4s %-10s %-12s %-12s %-12s %-12s\n" \
       "----" "---------" "--------" "---" "------" "--------"
for n in 1 2 4 8; do
  if [ "${n}" -eq 1 ]; then
    worktrees=0
  else
    worktrees="${n}"
  fi
  printf "%-4s %-10s %-12s %-12s %-12s %-12s\n" \
    "${n}" "${worktrees}" "$((n * 1))" "$((n * 2))" "$((n * 3))" "$((n * 4))"
done
echo
echo "Columns after WORKTREES are expected Phase 2 agent-spawn widths for"
echo "each fixture mode across N independent tasks. Live wall-clock timing"
echo "is intentionally excluded from this dry-run harness."
echo

# ---------------------------------------------------------------------------
# Section 2 — Phase 1d prefetch shell block exercise.
#
# Build a throwaway TASK_DIR + mock prd.md, run the prefetch block
# verbatim from supervisor-bootstrap.md, then verify:
#   (a) elapsed wall-clock is captured;
#   (b) files-warmed count is non-zero when fixtures exist;
#   (c) PID file is created;
#   (d) cleanup leaves no orphan process and removes the PID file.
# ---------------------------------------------------------------------------
echo "============================================================"
echo " Phase 1d prefetch — wall-clock + cleanup probe"
echo "============================================================"

BENCH_TMP="$(mktemp -d -t bench-prefetch.XXXXXX)"
trap 'rm -rf "${BENCH_TMP}"' EXIT

export TASK_DIR="${BENCH_TMP}/task"
export PROJECT_ROOT="${REPO_ROOT}"
export AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
mkdir -p "${TASK_DIR}/context"

# Build a mock prd.md that lists 10 real repo files. The prefetch block
# reads **Files** bullets and warms each path. Picking files from the
# bench fixtures + a few agent / rule files guarantees they exist and
# keeps the read set small.
cat >"${TASK_DIR}/context/prd.md" <<EOF
# Mock PRD for bench-parallel.sh

### Stage 1: backend

**Work**: Mock 3-endpoint API addition for bench fixture.

**Files**:
- core/scripts/bench-fixtures/mock-plan-3-endpoints.md
- core/scripts/bench-fixtures/mock-pipeline-baseline.json
- core/scripts/bench-fixtures/mock-pipeline-tdd.json
- core/scripts/bench-fixtures/mock-pipeline-fanout.json
- core/scripts/bench-fixtures/mock-pipeline-tdd-fanout.json
- core/agents/supervisor.md
- core/agents/supervisor-bootstrap.md
- core/agents/supervisor-stages.md
- core/agents/planner.md
- core/agents/analyst.md
EOF

# Minimal pipeline.json so the prefetch's first branch (pipeline-derived
# files) is also exercised.
cat >"${TASK_DIR}/pipeline.json" <<'EOF'
{
  "schema_version": 1,
  "stages": [
    {"agents": ["backend"], "files": ["README.md", "plugin.json"]}
  ],
  "completed_stages": 0,
  "stage_agent_status": {}
}
EOF

# Required by the prefetch block — log_progress falls back to a direct
# append when the helper is not defined in the subshell.
touch "${TASK_DIR}/progress.log"

PREFETCH_PID_FILE="${TASK_DIR}/context/prefetch.pid"
PREFETCH_LOG="${TASK_DIR}/context/prefetch.log"
PREFETCH_FILES_LIST="${TASK_DIR}/context/prefetch-files.txt"

# Stage 2a — enumerate files (verbatim from supervisor-bootstrap.md, with
# the harness's TASK_DIR / PROJECT_ROOT already exported above).
python3 - <<'PY' >"${PREFETCH_FILES_LIST}" 2>/dev/null || true
import json, os, re

task_dir = os.environ.get('TASK_DIR', '')
pipeline_path = os.path.join(task_dir, 'pipeline.json')
prd_path = os.path.join(task_dir, 'context', 'prd.md')

files = []

# 1) pipeline.json
try:
    p = json.load(open(pipeline_path))
    for stage in p.get('stages', []) or []:
        if isinstance(stage, dict):
            for f in stage.get('files', []) or []:
                if isinstance(f, str):
                    files.append(f)
                elif isinstance(f, dict) and isinstance(f.get('path'), str):
                    files.append(f['path'])
except Exception:
    pass

# 2) prd.md
try:
    text = open(prd_path).read()
    in_files = False
    for line in text.splitlines():
        if re.match(r'\*\*Files\*\*', line):
            in_files = True
            continue
        if in_files:
            m = re.match(r'\s*[-*]\s+`?([^`\s(]+)', line)
            if m:
                files.append(m.group(1))
            elif line.strip() == '' or line.startswith('##') or line.startswith('**'):
                in_files = False
except Exception:
    pass

seen, out = set(), []
for f in files:
    f = f.strip().rstrip(',').strip('`"\'')
    if not f or f in seen:
        continue
    seen.add(f); out.append(f)
    if len(out) >= 200:
        break
for f in out:
    print(f)
PY

PREFETCH_FILE_COUNT=$(wc -l <"${PREFETCH_FILES_LIST}" 2>/dev/null | tr -d ' ' || echo 0)
echo "enumerated_files: ${PREFETCH_FILE_COUNT}"

# Stage 2b — launch the prefetch background job (verbatim shape from
# supervisor-bootstrap.md, minus the log_progress dependency which is
# defined at supervisor runtime).
prefetch_start_epoch=$(date +%s%N)

(
  set +e
  start_epoch=$(date +%s)

  ( cd "${PROJECT_ROOT}" 2>/dev/null && git status --porcelain >/dev/null 2>&1 ) || true
  ls -la "${PROJECT_ROOT}" >/dev/null 2>&1 || true
  ls -la "${TASK_DIR}" >/dev/null 2>&1 || true
  ls -la "${TASK_DIR}/context" >/dev/null 2>&1 || true

  warmed=0
  if [ -s "${PREFETCH_FILES_LIST}" ]; then
    while IFS= read -r rel; do
      [ -z "${rel}" ] && continue
      case "${rel}" in
        /*) abs="${rel}" ;;
        *)  abs="${PROJECT_ROOT}/${rel}" ;;
      esac
      if [ -f "${abs}" ]; then
        wc -c "${abs}" >/dev/null 2>&1 && warmed=$((warmed + 1)) || true
      fi
    done <"${PREFETCH_FILES_LIST}"
  fi

  ls -la "${AGENT_CREW_HOME}/system/agents" >/dev/null 2>&1 || true

  end_epoch=$(date +%s)
  elapsed=$((end_epoch - start_epoch))

  echo "$(date -u +%Y-%m-%dT%H:%M:%S) | PHASE_1D_PREFETCH_DONE | files=${warmed} elapsed=${elapsed}s" \
    >> "${TASK_DIR}/progress.log" 2>/dev/null || true
  rm -f "${PREFETCH_PID_FILE}" 2>/dev/null || true
) >"${PREFETCH_LOG}" 2>&1 &
PREFETCH_PID=$!
disown "${PREFETCH_PID}" 2>/dev/null || true
echo "${PREFETCH_PID}" > "${PREFETCH_PID_FILE}" 2>/dev/null || true

echo "prefetch_pid: ${PREFETCH_PID}"
echo "prefetch_pid_file_exists_at_launch: $([ -f "${PREFETCH_PID_FILE}" ] && echo yes || echo no)"

# Wait for prefetch to finish naturally (with a 10s safety timeout) so
# we can measure end-to-end wall clock. In the live pipeline, the
# supervisor races this against the user's approval response — here we
# WANT to observe the natural completion path.
deadline=$(( $(date +%s) + 10 ))
while [ -f "${PREFETCH_PID_FILE}" ] && [ "$(date +%s)" -lt "${deadline}" ]; do
  sleep 0.05
done

prefetch_end_epoch=$(date +%s%N)
elapsed_ms=$(( (prefetch_end_epoch - prefetch_start_epoch) / 1000000 ))

echo "prefetch_wall_clock_ms: ${elapsed_ms}"
echo "prefetch_done_line:"
grep "PHASE_1D_PREFETCH_DONE" "${TASK_DIR}/progress.log" | sed 's/^/  /' || \
  echo "  (no DONE line — prefetch may have been slower than the 10s safety timeout)"

# Stage 2c — cleanup block (verbatim from supervisor-bootstrap.md). At
# this point the background job should have exited naturally and removed
# its own PID file; the cleanup is idempotent and must not error.
CHOICE="approve"
case "${CHOICE}" in
  approve)         PREFETCH_KILL_REASON="approved" ;;
  request_changes) PREFETCH_KILL_REASON="request_changes" ;;
  cancel)          PREFETCH_KILL_REASON="cancel" ;;
  *)               PREFETCH_KILL_REASON="approved" ;;
esac

cleanup_killed="no"
if [ -f "${PREFETCH_PID_FILE}" ]; then
  _pf_pid=$(cat "${PREFETCH_PID_FILE}" 2>/dev/null || echo "")
  if [ -n "${_pf_pid}" ] && kill -0 "${_pf_pid}" 2>/dev/null; then
    kill "${_pf_pid}" 2>/dev/null || true
    cleanup_killed="yes"
  fi
  rm -f "${PREFETCH_PID_FILE}" 2>/dev/null || true
fi

# Verify post-cleanup invariants.
pid_file_gone="no"
if [ ! -f "${PREFETCH_PID_FILE}" ]; then pid_file_gone="yes"; fi
process_still_alive="no"
if kill -0 "${PREFETCH_PID}" 2>/dev/null; then process_still_alive="yes"; fi

echo "cleanup_killed_running_process: ${cleanup_killed}"
echo "pid_file_removed_after_cleanup: ${pid_file_gone}"
echo "background_process_still_alive: ${process_still_alive}"
echo

# ---------------------------------------------------------------------------
# Section 3 — summary.
# ---------------------------------------------------------------------------
echo "============================================================"
echo " Summary"
echo "============================================================"
if [ "${ANY_MISMATCH}" = "0" ] && [ "${pid_file_gone}" = "yes" ] && \
   [ "${process_still_alive}" = "no" ]; then
  echo " RESULT: PASS"
  echo "   - All dispatch counts matched expected values."
  echo "   - Prefetch wall-clock measured at ${elapsed_ms}ms."
  echo "   - PID cleanup left no orphan process."
  exit 0
else
  echo " RESULT: ATTENTION"
  [ "${ANY_MISMATCH}" = "1" ] && \
    echo "   - One or more variants returned an unexpected spawn count."
  [ "${pid_file_gone}" = "no" ] && \
    echo "   - PID file was NOT removed after cleanup."
  [ "${process_still_alive}" = "yes" ] && \
    echo "   - Background prefetch process is STILL ALIVE after cleanup."
  exit 0
fi
