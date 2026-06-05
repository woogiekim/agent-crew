#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
HOOK="${REPO_ROOT}/core/hooks/supervisor-progress-guard.sh"

TMPDIR="$(mktemp -d)"
trap 'rm -rf "${TMPDIR}"' EXIT

export AGENT_CREW_HOME="${TMPDIR}/home"
PROJECT_ROOT="${TMPDIR}/project"
STATE_DIR="${AGENT_CREW_HOME}/state/project-123"
TASK_DIR="${STATE_DIR}/tasks/20260605-000000-0"

mkdir -p "${PROJECT_ROOT}" "${TASK_DIR}"
git -C "${PROJECT_ROOT}" init -q
touch "${TASK_DIR}/progress.log"
touch "${STATE_DIR}/tasks/active.20260605-000000-0"

cat > "${STATE_DIR}/capabilities.json" <<'EOF'
{}
EOF

printf '%s | STAGE_DONE | backend - APPROVED\n' "2026-06-05T00:00:00Z" >> "${TASK_DIR}/progress.log"

set +e
OUTPUT="$(
  printf '{"tool_name":"Bash","tool_input":{"cwd":"%s","command":"true"}}' "${PROJECT_ROOT}" \
    | bash "${HOOK}" 2>&1
)"
RC=$?
set -e

if [ "${RC}" -ne 2 ]; then
  printf 'expected hook exit 2, got %s\n%s\n' "${RC}" "${OUTPUT}" >&2
  exit 1
fi

grep -q "supervisor_pipeline_bypass_prevented" "${TASK_DIR}/result.md"
grep -q "supervisor_pipeline_bypass_prevented" <<< "${OUTPUT}"

touch "${TASK_DIR}/pipeline.json"

set +e
OUTPUT_OK="$(
  printf '{"tool_name":"Bash","tool_input":{"cwd":"%s","command":"true"}}' "${PROJECT_ROOT}" \
    | bash "${HOOK}" 2>&1
)"
RC_OK=$?
set -e

if [ "${RC_OK}" -ne 0 ]; then
  printf 'expected hook exit 0 after pipeline exists, got %s\n%s\n' "${RC_OK}" "${OUTPUT_OK}" >&2
  exit 1
fi
