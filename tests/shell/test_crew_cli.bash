#!/usr/bin/env bash
# Tests for the native core/bin/crew shell entrypoint.

set -u

# shellcheck source=./_lib.bash
source "$(dirname "$0")/_lib.bash"
set +e

CREW="${REPO_ROOT}/core/bin/crew"

it "crew help exits 0"
out=$(bash "${CREW}" --help 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "crew help mentions setup/status/telemetry/update"
assert_contains "${out}" "setup [PROJECT_ROOT]"
assert_contains "${out}" "telemetry [args]"

it "crew help states prompt-workflow control plane"
assert_contains "${out}" "local control plane for AI-host prompt workflows"

TMP_HOME=$(make_tmp)
TMP_PROJECT=$(make_tmp)
mkdir -p "${TMP_HOME}/state/$(basename "${TMP_PROJECT}")/tasks"

it "crew status exits 0 with empty task directory"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" status 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "crew status prints project state path"
assert_contains "${out}" "State  : ${TMP_HOME}/state/$(basename "${TMP_PROJECT}")"

it "crew status --json exits 0"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" status --json 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "crew status --json contains tasks key"
assert_contains "${out}" "\"tasks\""

it "crew telemetry exits 0 with empty task directory"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" telemetry 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "crew telemetry empty state prints no tasks"
assert_contains "${out}" "(no tasks matched)"

it "e2e SLO checker supports CI latency budgets without external memory"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" \
  python3 "${REPO_ROOT}/core/scripts/e2e-slo-check.py" \
    --project-root "${TMP_PROJECT}" \
    --crew-bin "${CREW}" \
    --status-budget-ms 10000 \
    --telemetry-budget-ms 10000 \
    --skip-memory-search \
    --skip-retrieval-eval \
    --skip-update-dry-run 2>&1)
rc=$?
assert_exit 0 "${rc}"
assert_contains "${out}" "PASS: e2e slo check"

SETUP_HOME=$(make_tmp)
SETUP_PROJECT=$(make_tmp)

it "crew setup bootstraps an empty AGENT_CREW_HOME from source checkout"
out=$(AGENT_CREW_HOME="${SETUP_HOME}" PROJECT_ROOT="${SETUP_PROJECT}" bash "${CREW}" setup "${SETUP_PROJECT}" 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "crew setup bootstrap installs setup dispatcher"
assert_file_exists "${SETUP_HOME}/setup/setup-host.sh"

it "crew setup bootstrap installs agent skills"
assert_file_exists "${SETUP_HOME}/system/agents/skills/tdd.md"

it "crew setup bootstrap initializes project capabilities"
assert_file_exists "${SETUP_HOME}/state/$(basename "${SETUP_PROJECT}")/capabilities.json"

PATH_HOME=$(make_tmp)
PATH_INSTALL=$(make_tmp)
PATH_PROJECT=$(make_tmp)
PATH_BIN="${PATH_HOME}/.local/bin"
mkdir -p "${PATH_BIN}" "${PATH_INSTALL}/user/agents" "${PATH_INSTALL}/user/skills"
printf 'custom agent\n' > "${PATH_INSTALL}/user/agents/custom-agent.md"
printf 'custom skill\n' > "${PATH_INSTALL}/user/skills/custom-skill.md"
cat > "${PATH_BIN}/crew" <<'EOF_STALE_CREW'
#!/usr/bin/env bash
# crew - experimental Codex launcher for agent-crew
exec codex exec "$@"
EOF_STALE_CREW
chmod +x "${PATH_BIN}/crew"

it "local sync replaces stale PATH crew launcher with native CLI"
out=$(HOME="${PATH_HOME}" AGENT_CREW_HOME="${PATH_INSTALL}" CLAUDE_DIR="${PATH_HOME}/.claude" CODEX_HOME="${PATH_HOME}/.codex" \
  bash "${REPO_ROOT}/core/scripts/sync-local-install.sh" "${REPO_ROOT}" "${PATH_PROJECT}" 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "local sync reports native PATH crew install"
assert_contains "${out}" "installed native crew CLI"

it "PATH crew now serves native mutating-agent guard without Codex launcher"
out=$(HOME="${PATH_HOME}" AGENT_CREW_HOME="${PATH_INSTALL}" PROJECT_ROOT="${PATH_PROJECT}" \
  "${PATH_BIN}/crew" agent "fix the pipeline" 2>&1)
rc=$?
assert_exit 2 "${rc}"
assert_contains "${out}" "Use crew run for mutating work"

it "local sync preserves user-owned agent and skill files"
assert_file_exists "${PATH_INSTALL}/user/agents/custom-agent.md"
assert_file_exists "${PATH_INSTALL}/user/skills/custom-skill.md"

it "local sync writes update preservation manifest"
manifest_count=$(find "${PATH_INSTALL}/state/$(basename "${PATH_PROJECT}")/update-preservation" -type f -name '*.json' 2>/dev/null | wc -l | tr -d ' ')
assert_eq "1" "${manifest_count}"

CUSTOM_HOME=$(make_tmp)
CUSTOM_INSTALL=$(make_tmp)
CUSTOM_PROJECT=$(make_tmp)
CUSTOM_BIN="${CUSTOM_HOME}/.local/bin"
mkdir -p "${CUSTOM_BIN}"
cat > "${CUSTOM_BIN}/crew" <<'EOF_CUSTOM_CREW'
#!/usr/bin/env bash
echo custom-crew
EOF_CUSTOM_CREW
chmod +x "${CUSTOM_BIN}/crew"

it "local sync preserves unmanaged PATH crew executable"
out=$(HOME="${CUSTOM_HOME}" AGENT_CREW_HOME="${CUSTOM_INSTALL}" CLAUDE_DIR="${CUSTOM_HOME}/.claude" CODEX_HOME="${CUSTOM_HOME}/.codex" \
  bash "${REPO_ROOT}/core/scripts/sync-local-install.sh" "${REPO_ROOT}" "${CUSTOM_PROJECT}" 2>&1)
rc=$?
assert_exit 0 "${rc}"
assert_contains "${out}" "skipping PATH crew CLI"

it "unmanaged PATH crew remains unchanged"
out=$("${CUSTOM_BIN}/crew" 2>&1)
assert_contains "${out}" "custom-crew"

HOOK_SYNC_HOME=$(make_tmp)
HOOK_SYNC_PROJECT=$(make_tmp)
mkdir -p "${HOOK_SYNC_HOME}/commands" "${HOOK_SYNC_HOME}/scripts" \
  "${HOOK_SYNC_HOME}/hooks" "${HOOK_SYNC_HOME}/system/hooks" \
  "${HOOK_SYNC_PROJECT}/core/hooks" \
  "${HOOK_SYNC_PROJECT}/.agent-crew/hooks" "${HOOK_SYNC_PROJECT}/.codex/hooks"
cp -R "${REPO_ROOT}/core/commands/." "${HOOK_SYNC_HOME}/commands/"
cp -R "${REPO_ROOT}/core/scripts/." "${HOOK_SYNC_HOME}/scripts/"
cp -R "${REPO_ROOT}/core/hooks/." "${HOOK_SYNC_PROJECT}/core/hooks/"
printf 'stale hook\n' > "${HOOK_SYNC_HOME}/hooks/auto-route.sh"
printf 'stale hook\n' > "${HOOK_SYNC_PROJECT}/.agent-crew/hooks/auto-route.sh"
printf 'stale hook\n' > "${HOOK_SYNC_PROJECT}/.codex/hooks/auto-route.sh"

it "crew run auto-refreshes drifted hooks from source checkout"
out=$(AGENT_CREW_HOME="${HOOK_SYNC_HOME}" PROJECT_ROOT="${HOOK_SYNC_PROJECT}" bash "${CREW}" run "demo hook sync task" 2>&1)
rc=$?
assert_exit 3 "${rc}"

it "crew run reports hook drift repair"
assert_contains "${out}" "refreshed auto-route hooks"

it "crew run refreshes installed global auto-route hook"
assert_contains "$(cat "${HOOK_SYNC_HOME}/hooks/auto-route.sh")" 'Invoke Skill("crew-run")'

it "crew run refreshes project-local Codex auto-route hook"
assert_contains "$(cat "${HOOK_SYNC_PROJECT}/.codex/hooks/auto-route.sh")" 'Invoke Skill("crew-run")'

printf 'stale project hook\n' > "${HOOK_SYNC_PROJECT}/.codex/hooks/auto-route.sh"

it "crew run detects project-local hook drift even when global hook is fresh"
out=$(AGENT_CREW_HOME="${HOOK_SYNC_HOME}" PROJECT_ROOT="${HOOK_SYNC_PROJECT}" bash "${CREW}" run "demo project hook sync task" 2>&1)
rc=$?
assert_exit 3 "${rc}"
assert_contains "${out}" "refreshed auto-route hooks"

it "crew run refreshes stale project-local hook after global hook is fresh"
assert_contains "$(cat "${HOOK_SYNC_PROJECT}/.codex/hooks/auto-route.sh")" 'Invoke Skill("crew-run")'

it "crew run writes deterministic state then exits blocked"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" run "demo task" 2>&1)
rc=$?
assert_exit 3 "${rc}"

it "crew run output includes task directory"
assert_contains "${out}" "TASK_DIR:"

TASK_DIR=$(printf '%s\n' "${out}" | awk -F': ' '/^TASK_DIR:/ {print $2; exit}')

it "crew run writes register.json"
assert_file_exists "${TASK_DIR}/register.json"

it "crew run writes supervisor handoff"
assert_file_exists "${TASK_DIR}/handoff.md"

it "crew run writes blocked result"
result=$(cat "${TASK_DIR}/result.md")
assert_contains "${result}" "STATUS: blocked"

it "crew run blocked result references host bridge"
assert_contains "${result}" "host AI bridge has not completed this handoff"

it "crew run blocked result includes next step guidance"
assert_contains "${result}" "NEXT: Hand the generated handoff.md to the host AI prompt runtime"

it "crew status --json reports blocked run blocker"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" status --json 2>&1)
assert_contains "${out}" "\"host AI bridge has not completed this handoff\""
assert_contains "${out}" "\"host_bridge_not_invoked\""
assert_contains "${out}" "\"guidance\""

it "crew telemetry --format json reports blocked run blocker"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" telemetry --format json 2>&1)
rc=$?
assert_exit 0 "${rc}"
assert_contains "${out}" "\"host_bridge_not_invoked\""
assert_contains "${out}" "\"tasks_blocked\": 1"

TASK_ID=$(basename "${TASK_DIR}")

it "crew repair marks a manually completed handoff as completed"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" repair --status completed --note "manual fallback done" "${TASK_ID}" 2>&1)
rc=$?
assert_exit 0 "${rc}"
assert_contains "${out}" "STATUS: completed"

it "crew repair writes repair evidence"
assert_file_exists "${TASK_DIR}/context/manual-fallback-repair.json"

it "crew repair removes stale host bridge blocker from task telemetry"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" telemetry --format json --task-id "${TASK_ID}" 2>&1)
assert_contains "${out}" "\"tasks_completed\": 1"
assert_not_contains "${out}" "\"host_bridge_not_invoked\""

it "crew run fake host can complete"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" run --fake-host-result completed "fake host task" 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "crew run fake host output is completed"
assert_contains "${out}" "STATUS: completed"

it "crew agent writes deterministic direct-agent handoff"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" agent analyst "what changed?" 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "crew agent output includes request directory"
assert_contains "${out}" "REQUEST_DIR:"

AGENT_REQUEST_DIR=$(printf '%s\n' "${out}" | awk -F': ' '/^REQUEST_DIR:/ {print $2; exit}')

it "crew agent writes request.json"
assert_file_exists "${AGENT_REQUEST_DIR}/request.json"

it "crew agent writes direct handoff"
assert_file_exists "${AGENT_REQUEST_DIR}/handoff.md"

it "crew agent blocks mutating direct requests"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" agent analyst "fix the bug" 2>&1)
rc=$?
assert_exit 2 "${rc}"

it "crew agent mutating failure redirects to crew run"
assert_contains "${out}" "Use crew run for mutating work"

it "crew agent auto-route mutating failure redirects to crew run"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" agent "fix the pipeline" 2>&1)
rc=$?
assert_exit 2 "${rc}"
assert_contains "${out}" "Use crew run for mutating work"

it "crew update --help exits 0"
out=$(bash "${CREW}" update --help 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "crew update --help documents local mode"
assert_contains "${out}" "crew update [--local [SOURCE_ROOT]]"

it "crew update --help documents remote default"
assert_contains "${out}" "clones origin/main into a fresh temporary checkout"

end_report
