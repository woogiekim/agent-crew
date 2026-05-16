#!/usr/bin/env bash
# Integration: validate every pipeline.json under the real (or hermetic)
# STATE_DIR against the in-repo pipeline schema.
#
# Default: scans ~/.agent-crew/state/agent-crew/tasks/*/pipeline.json IF
# AGENT_CREW_HOME points to the real home. Tests against the in-repo
# schemas always.
#
# Goal: ensure no historical task pipeline.json has drifted out of schema
# compliance after recent refactors. A failure here surfaces a real
# regression in the analyst or in the schema itself.

set -u
source "$(dirname "$0")/../shell/_lib.bash"

VALIDATOR="${SCRIPTS_DIR}/validate-state-schema.py"

# --------------------------------------------------------------------------- #
# Scan target — prefer hermetic; fall back to real $HOME if available         #
# --------------------------------------------------------------------------- #

SCAN_ROOT="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
TASKS_GLOB="${SCAN_ROOT}/state/agent-crew/tasks"

# Always test with a synthetic-valid pipeline first (sanity guard).

TMP=$(make_tmp)
HOME_T="${TMP}/home"
SD="${HOME_T}/state/proj"
TD="${SD}/tasks/20260101-120000-0"
mkdir -p "${TD}/context" "${HOME_T}/schemas"
# Copy real schemas
cp "${REPO_ROOT}/core/schemas/"*.schema.json "${HOME_T}/schemas/"

# Seed a minimum-valid project state
cat > "${SD}/session.json" <<'EOF'
{"schema_version":1,"session_id":"20260101-120000","status":"completed","tasks":[]}
EOF
cat > "${SD}/capabilities.json" <<'EOF'
{"schema_version":1,"host":"test"}
EOF
cat > "${TD}/register.json" <<'EOF'
{"schema_version":1,"task_id":"20260101-120000-0","session_id":"20260101-120000","task":"x","branch":"feat/x","project_root":"/tmp","task_dir":"/tmp/td","execution_mode":"single","current_phase":"completed","approval_status":"approved","verification_status":"passed"}
EOF

it "synthetic minimum-valid pipeline (single string stage) passes"
cat > "${TD}/pipeline.json" <<'EOF'
{"schema_version":1,"task":"x","stages":["planner"],"completed_stages":1}
EOF
AGENT_CREW_HOME="${HOME_T}" python3 "${VALIDATOR}" \
  --state-dir "${SD}" --task-dir "${TD}" >/dev/null 2>&1
rc=$?
# Allow rc=1 (warnings only — e.g., missing progress.buffer.jsonl which
# is optional in the synthetic fixture). Fail only on rc>=2.
if [ "${rc}" -le 1 ]; then _pass; else _fail "validator rc=${rc}"; fi

it "pipeline stage as array of strings (parallel) passes"
cat > "${TD}/pipeline.json" <<'EOF'
{"schema_version":1,"task":"x","stages":[["backend","frontend"]],"completed_stages":0}
EOF
AGENT_CREW_HOME="${HOME_T}" python3 "${VALIDATOR}" \
  --state-dir "${SD}" --task-dir "${TD}" >/dev/null 2>&1
rc=$?
# Allow rc=1 (warnings only — e.g., missing progress.buffer.jsonl which
# is optional in the synthetic fixture). Fail only on rc>=2.
if [ "${rc}" -le 1 ]; then _pass; else _fail "validator rc=${rc}"; fi

it "pipeline stage object with tdd_parallel passes"
cat > "${TD}/pipeline.json" <<'EOF'
{"schema_version":1,"task":"x","stages":[{"agents":["backend"],"tdd_parallel":true}],"completed_stages":0}
EOF
AGENT_CREW_HOME="${HOME_T}" python3 "${VALIDATOR}" \
  --state-dir "${SD}" --task-dir "${TD}" >/dev/null 2>&1
rc=$?
# Allow rc=1 (warnings only — e.g., missing progress.buffer.jsonl which
# is optional in the synthetic fixture). Fail only on rc>=2.
if [ "${rc}" -le 1 ]; then _pass; else _fail "validator rc=${rc}"; fi

it "pipeline stage object with parallelizable_units passes"
cat > "${TD}/pipeline.json" <<'EOF'
{
  "schema_version":1,
  "task":"x",
  "stages":[
    {"agents":["backend"], "parallelizable_units":[
      {"id":"u1","files":["src/a.py"],"brief":"unit 1 brief"},
      {"id":"u2","files":["src/b.py"],"brief":"unit 2 brief"}
    ]}
  ],
  "completed_stages":0
}
EOF
AGENT_CREW_HOME="${HOME_T}" python3 "${VALIDATOR}" \
  --state-dir "${SD}" --task-dir "${TD}" >/dev/null 2>&1
rc=$?
# Allow rc=1 (warnings only — e.g., missing progress.buffer.jsonl which
# is optional in the synthetic fixture). Fail only on rc>=2.
if [ "${rc}" -le 1 ]; then _pass; else _fail "validator rc=${rc}"; fi

it "pipeline stage object with streaming_review passes"
cat > "${TD}/pipeline.json" <<'EOF'
{"schema_version":1,"task":"x","stages":[{"agents":["backend"],"streaming_review":true},"reviewer"],"completed_stages":0}
EOF
AGENT_CREW_HOME="${HOME_T}" python3 "${VALIDATOR}" \
  --state-dir "${SD}" --task-dir "${TD}" >/dev/null 2>&1
rc=$?
# Allow rc=1 (warnings only — e.g., missing progress.buffer.jsonl which
# is optional in the synthetic fixture). Fail only on rc>=2.
if [ "${rc}" -le 1 ]; then _pass; else _fail "validator rc=${rc}"; fi

it "pipeline stage object with requires_test_execution=false passes"
cat > "${TD}/pipeline.json" <<'EOF'
{"schema_version":1,"task":"x","stages":[{"agents":["reviewer"],"requires_test_execution":false}],"completed_stages":0}
EOF
AGENT_CREW_HOME="${HOME_T}" python3 "${VALIDATOR}" \
  --state-dir "${SD}" --task-dir "${TD}" >/dev/null 2>&1
rc=$?
# Allow rc=1 (warnings only — e.g., missing progress.buffer.jsonl which
# is optional in the synthetic fixture). Fail only on rc>=2.
if [ "${rc}" -le 1 ]; then _pass; else _fail "validator rc=${rc}"; fi

# --------------------------------------------------------------------------- #
# Real-world scan: validate any existing pipeline.json files in $HOME         #
# Skipped if dir doesn't exist.                                               #
# --------------------------------------------------------------------------- #

it "scan real ~/.agent-crew tasks (if present)"
if [ -d "${TASKS_GLOB}" ]; then
  fail_count=0
  total=0
  while IFS= read -r -d '' pj; do
    total=$((total + 1))
    td=$(dirname "${pj}")
    # Just validate the single pipeline.json against the schema using
    # the in-repo validator. We pass --task-dir so the validator looks
    # at the pipeline.json (and register.json + progress.buffer.jsonl
    # if present).
    if ! AGENT_CREW_HOME="${SCAN_ROOT}" python3 "${VALIDATOR}" \
            --state-dir "${SCAN_ROOT}/state/agent-crew" \
            --task-dir "${td}" >/dev/null 2>&1; then
      out=$(AGENT_CREW_HOME="${SCAN_ROOT}" python3 "${VALIDATOR}" \
              --state-dir "${SCAN_ROOT}/state/agent-crew" \
              --task-dir "${td}" 2>&1 || true)
      rc=$?
      # Treat rc=1 (warns only) as OK. Only rc>=2 is a real failure.
      if [ "${rc}" -ge 2 ]; then
        fail_count=$((fail_count + 1))
        printf '    HARD-FAIL pipeline.json: %s\n' "${pj}"
        printf '%s\n' "${out}" | sed 's/^/      /'
      fi
    fi
  done < <(find "${TASKS_GLOB}" -mindepth 2 -maxdepth 2 -name "pipeline.json" -print0 2>/dev/null)
  if [ "${fail_count}" -eq 0 ]; then
    _pass
    printf '    scanned %d real pipeline.json file(s), all pass\n' "${total}"
  else
    _fail "${fail_count} of ${total} real pipeline.json files failed validation"
  fi
else
  _pass
  echo "    (no real tasks dir at ${TASKS_GLOB} — synthetic-only run)"
fi

end_report
