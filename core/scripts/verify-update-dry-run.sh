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
  "${AGENT_CREW_HOME}/user/agents" \
  "${AGENT_CREW_HOME}/user/skills" \
  "${CODEX_HOME}/agents" \
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

printf 'stale\n' > "${CODEX_HOME}/agents/task-runner.toml"
printf 'stale\n' > "${CODEX_HOME}/agent-crew/skills/stale.md"

AGENT_CREW_HOME="${AGENT_CREW_HOME}" \
CODEX_HOME="${CODEX_HOME}" \
CLAUDE_DIR="${CLAUDE_DIR}" \
AGENT_CREW_PATH_BIN="${PATH_BIN}" \
  bash "${SOURCE_ROOT}/core/scripts/sync-local-install.sh" "${SOURCE_ROOT}" "${PROJECT_ROOT}" >/dev/null

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
assert_exists "${AGENT_CREW_HOME}/skills/local-skill.md"
assert_exists "${CODEX_HOME}/agents/supervisor.toml"
assert_exists "${AGENT_CREW_HOME}/hooks/auto-route.sh"
assert_exists "${PROJECT_ROOT}/.codex/hooks/auto-route.sh"
assert_exists "${PROJECT_ROOT}/.codex/agents/supervisor.toml"
assert_exists "${AGENT_CREW_HOME}/state/$(basename "${PROJECT_ROOT}")/update-preservation"
assert_absent "${CODEX_HOME}/agents/task-runner.toml"
assert_absent "${CODEX_HOME}/agent-crew/skills/stale.md"
assert_contains "${CODEX_HOME}/agents/supervisor.toml" "${AGENT_CREW_HOME}/system/agents/supervisor.md"
assert_contains "${PROJECT_ROOT}/.codex/agents/supervisor.toml" "${AGENT_CREW_HOME}/system/agents/supervisor.md"
assert_contains "${AGENT_CREW_HOME}/hooks/auto-route.sh" 'Invoke Skill("crew-run")'
assert_contains "${PROJECT_ROOT}/.codex/hooks/auto-route.sh" 'Invoke Skill("crew-run")'
if ! find "${AGENT_CREW_HOME}/state/$(basename "${PROJECT_ROOT}")/update-preservation" \
  -type f -name '*.json' | grep -q .; then
  printf 'verify-update-dry-run: preservation manifest was not written\n' >&2
  exit 1
fi

printf 'PASS: update dry-run verifier (sandbox=%s)\n' "${TMP_ROOT}"
