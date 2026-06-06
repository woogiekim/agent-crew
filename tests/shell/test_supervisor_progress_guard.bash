#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
HOOK="${REPO_ROOT}/core/hooks/supervisor-progress-guard.sh"

TMPDIR="$(mktemp -d)"
trap 'rm -rf "${TMPDIR}"' EXIT

export AGENT_CREW_HOME="${TMPDIR}/home"
PROJECT_ROOT="${TMPDIR}/project"
STATE_DIR="${AGENT_CREW_HOME}/state/project"
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

test ! -f "${TASK_DIR}/result.md"
grep -q "supervisor_pipeline_bypass_prevented" "${TASK_DIR}/result.violation.md"
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

LEGACY_TASK_DIR="${STATE_DIR}/tasks/20260605-legacy-0"
mkdir -p "${LEGACY_TASK_DIR}"
printf '%s | COMPLETED | legacy docs-only task\n' "2026-06-05T00:00:00Z" > "${LEGACY_TASK_DIR}/progress.log"
printf 'STATUS: completed\nDETAIL: historical result\n' > "${LEGACY_TASK_DIR}/result.md"
touch "${STATE_DIR}/tasks/active"

set +e
OUTPUT_LEGACY="$(
  printf '{"tool_name":"Bash","tool_input":{"cwd":"%s","command":"true"}}' "${PROJECT_ROOT}" \
    | bash "${HOOK}" 2>&1
)"
RC_LEGACY=$?
set -e

if [ "${RC_LEGACY}" -ne 0 ]; then
  printf 'expected legacy active marker to be ignored, got %s\n%s\n' "${RC_LEGACY}" "${OUTPUT_LEGACY}" >&2
  exit 1
fi

grep -q "STATUS: completed" "${LEGACY_TASK_DIR}/result.md"
test ! -f "${LEGACY_TASK_DIR}/result.violation.md"
rm -f "${STATE_DIR}/tasks/active"

TERMINAL_TASK_DIR="${STATE_DIR}/tasks/20260605-terminal-0"
mkdir -p "${TERMINAL_TASK_DIR}"
printf '%s | COMPLETED | already terminal task\n' "2026-06-05T00:00:00Z" > "${TERMINAL_TASK_DIR}/progress.log"
printf 'STATUS: completed\nDETAIL: do not overwrite\n' > "${TERMINAL_TASK_DIR}/result.md"
touch "${STATE_DIR}/tasks/active.20260605-terminal-0"

set +e
OUTPUT_TERMINAL="$(
  printf '{"tool_name":"Bash","tool_input":{"cwd":"%s","command":"true"}}' "${PROJECT_ROOT}" \
    | bash "${HOOK}" 2>&1
)"
RC_TERMINAL=$?
set -e

if [ "${RC_TERMINAL}" -ne 0 ]; then
  printf 'expected terminal active task to be ignored, got %s\n%s\n' "${RC_TERMINAL}" "${OUTPUT_TERMINAL}" >&2
  exit 1
fi

grep -q "STATUS: completed" "${TERMINAL_TASK_DIR}/result.md"
grep -q "do not overwrite" "${TERMINAL_TASK_DIR}/result.md"
test ! -f "${TERMINAL_TASK_DIR}/result.violation.md"

OTHER_STATE_DIR="${AGENT_CREW_HOME}/state/other-project"
OTHER_TASK_DIR="${OTHER_STATE_DIR}/tasks/20260605-other-0"
mkdir -p "${OTHER_TASK_DIR}"
printf '%s | STAGE_DONE | unrelated project task\n' "2026-06-05T00:00:00Z" > "${OTHER_TASK_DIR}/progress.log"
touch "${OTHER_STATE_DIR}/tasks/active.20260605-other-0"

set +e
OUTPUT_OTHER="$(
  printf '{"tool_name":"Bash","tool_input":{"cwd":"%s","command":"true"}}' "${PROJECT_ROOT}" \
    | bash "${HOOK}" 2>&1
)"
RC_OTHER=$?
set -e

if [ "${RC_OTHER}" -ne 0 ]; then
  printf 'expected unrelated project active marker to be ignored, got %s\n%s\n' "${RC_OTHER}" "${OUTPUT_OTHER}" >&2
  exit 1
fi

test ! -f "${OTHER_TASK_DIR}/result.violation.md"
