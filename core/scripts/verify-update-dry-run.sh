#!/usr/bin/env bash
# verify-update-dry-run.sh — validate update behavior in a temporary install tree.
#
# The verifier intentionally runs the real local sync/update helpers, but all
# mutation targets are temporary AGENT_CREW_HOME, CODEX_HOME, CLAUDE_DIR,
# PATH-bin, and PROJECT_ROOT directories. It never writes to the operator's
# actual install paths.

set -euo pipefail

SOURCE_ROOT="${1:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
SOURCE_ROOT="$(cd "${SOURCE_ROOT}" && pwd)"

if [ ! -d "${SOURCE_ROOT}/core" ] || [ ! -d "${SOURCE_ROOT}/adapters" ]; then
  printf 'verify-update-dry-run: SOURCE_ROOT is not an agent-crew checkout: %s\n' "${SOURCE_ROOT}" >&2
  exit 2
fi

TMP_ROOT="$(mktemp -d)"
cleanup() {
  rm -rf "${TMP_ROOT}"
}
trap cleanup EXIT

PROJECT_ROOT="${TMP_ROOT}/project"
AGENT_CREW_HOME="${TMP_ROOT}/agent-crew-home"
CODEX_HOME="${TMP_ROOT}/codex-home"
CLAUDE_DIR="${TMP_ROOT}/claude-home"
PATH_BIN="${TMP_ROOT}/path-bin"

mkdir -p \
  "${PROJECT_ROOT}" \
  "${AGENT_CREW_HOME}/scripts" \
  "${AGENT_CREW_HOME}/user/agents" \
  "${AGENT_CREW_HOME}/user/skills" \
  "${CODEX_HOME}/agents" \
  "${CODEX_HOME}/skills/crew:run" \
  "${CODEX_HOME}/skills/agent-crew" \
  "${CODEX_HOME}/agent-crew/skills" \
  "${CLAUDE_DIR}" \
  "${PATH_BIN}"

git -C "${PROJECT_ROOT}" init -q

cat > "${AGENT_CREW_HOME}/user/agents/local-keeper.md" <<'EOF'
---
name: local-keeper
description: Local user agent preserved across update dry-run.
---

# local-keeper
EOF

cat > "${AGENT_CREW_HOME}/user/skills/local-skill.md" <<'EOF'
# local-skill

User-owned skill preserved across update dry-run.
EOF

cat > "${AGENT_CREW_HOME}/user/skills/dobby-review-heuristics.md" <<'EOF'
---
name: dobby-review-heuristics
description: User-owned review-profile fixture preserved across update dry-run.
loaded_by: reviewer
profile_type: review-policy
detection: Dobby-style review fixture
---

# dobby-review-heuristics

User-owned review-profile skill preserved across update dry-run.
EOF

printf 'stale\n' > "${CODEX_HOME}/agents/task-runner.toml"
printf 'stale\n' > "${CODEX_HOME}/agent-crew/skills/stale.md"
printf 'stale\n' > "${AGENT_CREW_HOME}/scripts/stale-leftover.py"
cat > "${CODEX_HOME}/config.toml" <<'EOF'
model = "gpt-test"

[mcp_servers.gitlab]
command = "bash"
args = ["-lc", "gitlab-mcp"]
EOF

AGENT_CREW_HOME="${AGENT_CREW_HOME}" \
CODEX_HOME="${CODEX_HOME}" \
CLAUDE_DIR="${CLAUDE_DIR}" \
AGENT_CREW_PATH_BIN="${PATH_BIN}" \
  bash "${SOURCE_ROOT}/core/scripts/sync-local-install.sh" "${SOURCE_ROOT}" "${PROJECT_ROOT}" >/dev/null

STATE_DIR="$(AGENT_CREW_HOME="${AGENT_CREW_HOME}" PROJECT_ROOT="${PROJECT_ROOT}" \
  python3 "${SOURCE_ROOT}/core/scripts/project_state.py" resolve \
    --agent-crew-home "${AGENT_CREW_HOME}" \
    --project-root "${PROJECT_ROOT}" \
    --format json \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["state_dir"])')"

assert_exists() {
  local path="$1"
  if [ ! -e "${path}" ]; then
    printf 'verify-update-dry-run: missing expected path: %s\n' "${path}" >&2
    exit 1
  fi
}

assert_absent() {
  local path="$1"
  if [ -e "${path}" ]; then
    printf 'verify-update-dry-run: stale path still exists: %s\n' "${path}" >&2
    exit 1
  fi
}

assert_contains() {
  local path="$1" needle="$2"
  if ! grep -Fq "${needle}" "${path}"; then
    printf 'verify-update-dry-run: %s does not contain %s\n' "${path}" "${needle}" >&2
    exit 1
  fi
}

assert_exists "${AGENT_CREW_HOME}/user/agents/local-keeper.md"
assert_exists "${AGENT_CREW_HOME}/user/skills/local-skill.md"
assert_exists "${AGENT_CREW_HOME}/user/skills/dobby-review-heuristics.md"
assert_exists "${AGENT_CREW_HOME}/skills/local-skill.md"
assert_exists "${AGENT_CREW_HOME}/skills/dobby-review-heuristics.md"
assert_exists "${CODEX_HOME}/agents/supervisor.toml"
assert_exists "${AGENT_CREW_HOME}/hooks/auto-route.sh"
assert_exists "${PROJECT_ROOT}/.codex/hooks/auto-route.sh"
assert_exists "${PROJECT_ROOT}/.codex/agents/supervisor.toml"
assert_exists "${STATE_DIR}/update-preservation"
assert_absent "${CODEX_HOME}/agents/task-runner.toml"
assert_absent "${CODEX_HOME}/skills/agent-crew"
assert_exists "${CODEX_HOME}/skills/crew:run/SKILL.md"
assert_absent "${CODEX_HOME}/agent-crew/skills/stale.md"
assert_absent "${AGENT_CREW_HOME}/scripts/stale-leftover.py"
assert_contains "${CODEX_HOME}/config.toml" "[mcp_servers.gitlab]"
assert_contains "${CODEX_HOME}/config.toml" 'args = ["-lc", "gitlab-mcp"]'
assert_contains "${CODEX_HOME}/agents/supervisor.toml" "${AGENT_CREW_HOME}/system/agents/supervisor.md"
assert_contains "${PROJECT_ROOT}/.codex/agents/supervisor.toml" "${AGENT_CREW_HOME}/system/agents/supervisor.md"
assert_contains "${AGENT_CREW_HOME}/hooks/auto-route.sh" 'explicit {command} invocation detected'
assert_contains "${PROJECT_ROOT}/.codex/hooks/auto-route.sh" 'explicit {command} invocation detected'
if ! find "${STATE_DIR}/update-preservation" \
  -type f -name '*.json' | grep -q .; then
  printf 'verify-update-dry-run: preservation manifest was not written\n' >&2
  exit 1
fi

printf 'PASS: update dry-run verifier (sandbox=%s)\n' "${TMP_ROOT}"
