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

it "crew help mentions setup/status/telemetry/trace/cost/doctor/config/debug/resume/update/report"
assert_contains "${out}" "setup [PROJECT_ROOT]"
assert_contains "${out}" "telemetry [args]"
assert_contains "${out}" "trace [args]"
assert_contains "${out}" "cost [args]"
assert_contains "${out}" "doctor [args]"
assert_contains "${out}" "config doctor|dump"
assert_contains "${out}" "debug [args]"
assert_contains "${out}" "resume [--print|--dry-run] TASK_ID"
assert_contains "${out}" "report auto|publish"

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

it "crew cost exits 0 with empty cost directory"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" cost 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "crew cost reports zero tokens with empty cost directory"
assert_contains "${out}" '"total_tokens": 0'

it "crew cleanup-state helper exits 0 through extracted dispatcher"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" cleanup-state --format json 2>&1)
rc=$?
assert_exit 0 "${rc}"
assert_contains "${out}" '"summary"'

it "crew cost --help documents aggregate metrics"
out=$(bash "${CREW}" cost --help 2>&1)
rc=$?
assert_exit 0 "${rc}"
assert_contains "${out}" "crew cost"

it "crew doctor exits 0 for current repository"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${REPO_ROOT}" bash "${CREW}" doctor 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "crew doctor reports framework review status"
assert_contains "${out}" "PASS: framework review check"

it "crew doctor supports split runtime mode"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${REPO_ROOT}" bash "${CREW}" doctor --mode runtime 2>&1)
rc=$?
assert_exit 0 "${rc}"
assert_contains "${out}" "schema validation"
assert_contains "${out}" "trace rendering"
assert_contains "${out}" "report outbox creation"

it "crew config dump --effective exposes central runtime settings"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" config dump --effective 2>&1)
rc=$?
assert_exit 0 "${rc}"
assert_contains "${out}" "active_adapter:"
assert_contains "${out}" "capability.task_tools:"
assert_contains "${out}" "report_settings.publish:"
assert_contains "${out}" "memory_backend:"
assert_contains "${out}" "install_drift:"

it "crew doctor --help documents readiness checks"
out=$(bash "${CREW}" doctor --help 2>&1)
rc=$?
assert_exit 0 "${rc}"
assert_contains "${out}" "static|runtime|host|all"

it "crew trace exits 0 with empty task directory"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" trace 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "crew trace empty state explains no events"
assert_contains "${out}" "No trace events found."

TRACE_HOME=$(make_tmp)
TRACE_PROJECT=$(make_tmp)
mkdir -p "${TRACE_PROJECT}"

it "crew run records provider-neutral delegation lineage"
out=$(AGENT_CREW_HOME="${TRACE_HOME}" PROJECT_ROOT="${TRACE_PROJECT}" bash "${CREW}" run "read docs" 2>&1)
rc=$?
assert_exit 3 "${rc}"
TRACE_TASK_ID=$(printf '%s\n' "${out}" | awk '/^TASK_ID:/ {print $2; exit}')
TRACE_TASK_DIR=$(printf '%s\n' "${out}" | awk '/^TASK_DIR:/ {print $2; exit}')
assert_file_exists "${TRACE_TASK_DIR}/delegation.jsonl"
assert_contains "$(cat "${TRACE_TASK_DIR}/delegation.jsonl")" "\"agent_role\": \"supervisor\""

it "crew resume default records RESUME_REQUESTED and --print stays read-only"
before_lines=$(wc -l < "${TRACE_TASK_DIR}/progress.buffer.jsonl" | tr -d ' ')
out=$(AGENT_CREW_HOME="${TRACE_HOME}" PROJECT_ROOT="${TRACE_PROJECT}" bash "${CREW}" resume "${TRACE_TASK_ID}" 2>&1)
rc=$?
assert_exit 0 "${rc}"
assert_contains "${out}" "TASK_ID: ${TRACE_TASK_ID}"
assert_contains "$(cat "${TRACE_TASK_DIR}/progress.buffer.jsonl")" "RESUME_REQUESTED"
after_request_lines=$(wc -l < "${TRACE_TASK_DIR}/progress.buffer.jsonl" | tr -d ' ')
out=$(AGENT_CREW_HOME="${TRACE_HOME}" PROJECT_ROOT="${TRACE_PROJECT}" bash "${CREW}" resume --print "${TRACE_TASK_ID}" 2>&1)
rc=$?
assert_exit 0 "${rc}"
after_print_lines=$(wc -l < "${TRACE_TASK_DIR}/progress.buffer.jsonl" | tr -d ' ')
assert_eq "${after_request_lines}" "${after_print_lines}"
test "${after_request_lines}" -gt "${before_lines}"
assert_true "$?" "resume appended a state event"

TOOL_HOME=$(make_tmp)
TOOL_PROJECT=$(make_tmp)
mkdir -p "${TOOL_PROJECT}"

it "host bridge command failures create redacted tool-events and trace can include tools"
out=$(AGENT_CREW_HOME="${TOOL_HOME}" PROJECT_ROOT="${TOOL_PROJECT}" bash "${CREW}" run --host-bridge-command "printf token=secret123 >&2; exit 7" "read-only host bridge" 2>&1)
rc=$?
assert_exit 3 "${rc}"
TOOL_TASK_ID=$(printf '%s\n' "${out}" | awk '/^TASK_ID:/ {print $2; exit}')
TOOL_TASK_DIR=$(printf '%s\n' "${out}" | awk '/^TASK_DIR:/ {print $2; exit}')
assert_file_exists "${TOOL_TASK_DIR}/tool-events.jsonl"
tool_json=$(cat "${TOOL_TASK_DIR}/tool-events.jsonl")
assert_contains "${tool_json}" "\"tool_name\": \"host_bridge_command\""
assert_contains "${tool_json}" "\"failure_class\": \"host_bridge_command_failed\""
assert_not_contains "${tool_json}" "token=secret123"
out=$(AGENT_CREW_HOME="${TOOL_HOME}" PROJECT_ROOT="${TOOL_PROJECT}" bash "${CREW}" trace --task-id "${TOOL_TASK_ID}" --include-tools 2>&1)
rc=$?
assert_exit 0 "${rc}"
assert_contains "${out}" "Tools:"
assert_contains "${out}" "host_bridge_command"

it "crew debug exits 0 with empty task directory"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" debug --recent 1 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "crew debug includes doctor, telemetry, and cost sections"
assert_contains "${out}" "== doctor =="
assert_contains "${out}" "== telemetry =="
assert_contains "${out}" "== cost =="

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
mkdir -p "${PATH_BIN}" "${PATH_INSTALL}/agents" "${PATH_INSTALL}/user/agents" "${PATH_INSTALL}/user/skills"
cp "${REPO_ROOT}/core/agents/backend.md" "${PATH_INSTALL}/agents/backend.md"
printf 'legacy custom agent\n' > "${PATH_INSTALL}/agents/local-legacy.md"
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

it "local sync explains first fingerprint miss"
assert_contains "${out}" "MISS: update fingerprint"

it "local sync removes duplicate legacy system agents"
assert_file_absent "${PATH_INSTALL}/agents/backend.md"

it "local sync migrates legacy custom agents"
assert_file_exists "${PATH_INSTALL}/user/agents/local-legacy.md"

it "local sync does not leave noisy legacy agent review warning for duplicates"
assert_not_contains "${out}" "possible user-modified file(s)"

it "local sync post-check reports install drift success"
assert_contains "${out}" "PASS: install drift check"

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

it "repeated local sync does not delete regenerated Codex agents or hooks"
out=$(HOME="${PATH_HOME}" AGENT_CREW_HOME="${PATH_INSTALL}" CLAUDE_DIR="${PATH_HOME}/.claude" CODEX_HOME="${PATH_HOME}/.codex" \
  bash "${REPO_ROOT}/core/scripts/sync-local-install.sh" "${REPO_ROOT}" "${PATH_PROJECT}" 2>&1)
rc=$?
assert_exit 0 "${rc}"
assert_contains "${out}" "skipped adapter refresh"
assert_not_contains "${out}" "Removing stale file from ${PATH_PROJECT}/.codex: agents/"
assert_not_contains "${out}" "Removing stale file from ${PATH_PROJECT}/.codex: hooks/"
assert_not_contains "${out}" "Removing stale file from ${PATH_PROJECT}/.codex: hooks.json"

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

LEGACY_REVIEW_HOME=$(make_tmp)
LEGACY_REVIEW_INSTALL=$(make_tmp)
LEGACY_REVIEW_PROJECT=$(make_tmp)
mkdir -p "${LEGACY_REVIEW_INSTALL}/agents"
printf '# Backend\n\nuser-modified legacy backend\n' > "${LEGACY_REVIEW_INSTALL}/agents/backend.md"

it "local sync preserves user-modified legacy system-name agents"
out=$(HOME="${LEGACY_REVIEW_HOME}" AGENT_CREW_HOME="${LEGACY_REVIEW_INSTALL}" CLAUDE_DIR="${LEGACY_REVIEW_HOME}/.claude" CODEX_HOME="${LEGACY_REVIEW_HOME}/.codex" \
  bash "${REPO_ROOT}/core/scripts/sync-local-install.sh" "${REPO_ROOT}" "${LEGACY_REVIEW_PROJECT}" 2>&1)
rc=$?
assert_exit 0 "${rc}"
assert_file_exists "${LEGACY_REVIEW_INSTALL}/agents/backend.md"
assert_contains "${out}" "possible user-modified file(s)"

RUNTIME_SYNC_HOME=$(make_tmp)
RUNTIME_SYNC_PROJECT=$(make_tmp)
RUNTIME_SYNC_BIN=$(make_tmp)
mkdir -p "${RUNTIME_SYNC_PROJECT}/core" "${RUNTIME_SYNC_BIN}"
cp -R "${REPO_ROOT}/core/commands" "${RUNTIME_SYNC_PROJECT}/core/"
cp -R "${REPO_ROOT}/core/scripts" "${RUNTIME_SYNC_PROJECT}/core/"
cp -R "${REPO_ROOT}/core/hooks" "${RUNTIME_SYNC_PROJECT}/core/"
cp -R "${REPO_ROOT}/core/evaluations" "${RUNTIME_SYNC_PROJECT}/core/"
cp -R "${REPO_ROOT}/core/schemas" "${RUNTIME_SYNC_PROJECT}/core/"
cp -R "${REPO_ROOT}/core/policies" "${RUNTIME_SYNC_PROJECT}/core/"
cp -R "${REPO_ROOT}/core/bin" "${RUNTIME_SYNC_PROJECT}/core/"
cp -R "${REPO_ROOT}/adapters" "${RUNTIME_SYNC_PROJECT}/"
cp "${REPO_ROOT}/core/bin/crew" "${RUNTIME_SYNC_BIN}/crew"
printf '\n# stale managed PATH crew copy\n' >> "${RUNTIME_SYNC_BIN}/crew"
chmod +x "${RUNTIME_SYNC_BIN}/crew"
mkdir -p "${RUNTIME_SYNC_HOME}/scripts"
printf 'stale runtime\n' > "${RUNTIME_SYNC_HOME}/scripts/crew-runtime.py"

it "crew run auto-refreshes drifted runtime assets from local source"
out=$(PATH="${RUNTIME_SYNC_BIN}:${PATH}" AGENT_CREW_HOME="${RUNTIME_SYNC_HOME}" PROJECT_ROOT="${RUNTIME_SYNC_PROJECT}" "${RUNTIME_SYNC_BIN}/crew" run "runtime sync task" 2>&1)
rc=$?
assert_exit 3 "${rc}"
assert_contains "${out}" "refreshed runtime assets"

it "crew run installs missing runtime repair script during auto-refresh"
assert_file_exists "${RUNTIME_SYNC_HOME}/scripts/repair-task-state.py"

it "crew run installs pipeline quality plan checker during auto-refresh"
assert_file_exists "${RUNTIME_SYNC_HOME}/scripts/pipeline-quality-plan-check.py"

it "crew run installs automatic issue reporter during auto-refresh"
assert_file_exists "${RUNTIME_SYNC_HOME}/scripts/auto-issue-reporter.py"

it "crew run installs memory GC command during auto-refresh"
assert_file_exists "${RUNTIME_SYNC_HOME}/scripts/memory-gc.py"

it "crew run installs agent capability checker during auto-refresh"
assert_file_exists "${RUNTIME_SYNC_HOME}/scripts/agent-capability-check.py"

it "crew run installs pipeline capability checker during auto-refresh"
assert_file_exists "${RUNTIME_SYNC_HOME}/scripts/pipeline-capability-check.py"

it "crew run installs workflow replay checker during auto-refresh"
assert_file_exists "${RUNTIME_SYNC_HOME}/scripts/workflow-replay-check.py"

it "crew run installs retry chaos checker during auto-refresh"
assert_file_exists "${RUNTIME_SYNC_HOME}/scripts/retry-chaos-check.py"

it "crew run installs telemetry taxonomy checker during auto-refresh"
assert_file_exists "${RUNTIME_SYNC_HOME}/scripts/telemetry-taxonomy-check.py"

it "crew run installs agent capability policy during auto-refresh"
assert_file_exists "${RUNTIME_SYNC_HOME}/policies/agent-capabilities.json"

it "crew run installs workflow replay fixture during auto-refresh"
assert_file_exists "${RUNTIME_SYNC_HOME}/evaluations/workflow-replay.json"

it "crew run installs retry chaos fixture during auto-refresh"
assert_file_exists "${RUNTIME_SYNC_HOME}/evaluations/retry-chaos.json"

it "crew run refreshes managed PATH crew CLI during auto-refresh"
cmp -s "${REPO_ROOT}/core/bin/crew" "${RUNTIME_SYNC_BIN}/crew"
rc=$?
assert_exit 0 "${rc}"

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

it "crew run blocked result includes concise next step guidance"
assert_contains "${result}" "NEXT: Continue with"

it "crew run blocked result explains native runtime bridge behavior"
assert_contains "${result}" "DETAIL: host bridge command was not invoked automatically in this runtime."

it "crew run blocked result suggests bridge command configuration"
assert_contains "${result}" "set AGENT_CREW_HOST_BRIDGE_COMMAND"

it "crew run blocked result avoids verbose fallback narration"
assert_not_contains "${result}" "If the host bridge is unavailable"
assert_not_contains "${result}" "so `crew telemetry` no longer reports"

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

it "crew trace shows blocked run progress events"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" trace --task-id "${TASK_ID}" 2>&1)
rc=$?
assert_exit 0 "${rc}"
assert_contains "${out}" "Task: ${TASK_ID}"
assert_contains "${out}" "STATUS"

it "crew resume prints handoff coordinates"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" resume "${TASK_ID}" 2>&1)
rc=$?
assert_exit 0 "${rc}"
assert_contains "${out}" "TASK_ID: ${TASK_ID}"
assert_contains "${out}" "HANDOFF:"
assert_contains "${out}" "NEXT: Continue in the host prompt runtime"

it "crew resume blocks missing required workflow state markers"
BROKEN_TASK_ID="20260101-999999-0"
BROKEN_TASK_DIR="${TMP_HOME}/state/$(basename "${TMP_PROJECT}")/tasks/${BROKEN_TASK_ID}"
mkdir -p "${BROKEN_TASK_DIR}"
printf 'broken resume fixture\n' > "${BROKEN_TASK_DIR}/task.txt"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" resume "${BROKEN_TASK_ID}" 2>&1)
rc=$?
assert_exit 2 "${rc}"
assert_contains "${out}" "BLOCKER: missing_required_state_markers"

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

it "crew cleanup-host-bridge dry-run finds stale host bridge task"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" run "cleanup stale host bridge task" 2>&1)
rc=$?
assert_exit 3 "${rc}"
CLEANUP_TASK_DIR=$(printf '%s\n' "${out}" | awk -F': ' '/^TASK_DIR:/ {print $2; exit}')
CLEANUP_TASK_ID=$(basename "${CLEANUP_TASK_DIR}")
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" cleanup-host-bridge --format json 2>&1)
assert_contains "${out}" "${CLEANUP_TASK_ID}"

it "crew cleanup-host-bridge apply removes stale host bridge blocker"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" cleanup-host-bridge --apply --status completed --note "bulk completed" --format json 2>&1)
rc=$?
assert_exit 0 "${rc}"
assert_contains "${out}" "${CLEANUP_TASK_ID}"

it "crew cleanup-host-bridge apply writes stale cleanup evidence"
assert_file_exists "${CLEANUP_TASK_DIR}/context/stale-host-bridge-cleanup.json"

out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" telemetry --format json --task-id "${CLEANUP_TASK_ID}" 2>&1)
assert_contains "${out}" "\"tasks_completed\": 1"
assert_not_contains "${out}" "\"host_bridge_not_invoked\""

it "crew run fake host can complete"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" run --fake-host-result completed "fake host task" 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "crew run fake host output is completed"
assert_contains "${out}" "STATUS: completed"

it "crew run host bridge command can auto-complete a handoff"
BRIDGE_LOG="$(make_tmp)/host-bridge.log"
out=$(
  AGENT_CREW_HOME="${TMP_HOME}" \
  PROJECT_ROOT="${TMP_PROJECT}" \
  AGENT_CREW_BRIDGE_LOG="${BRIDGE_LOG}" \
  AGENT_CREW_HOST_BRIDGE_COMMAND='printf "%s\n" "$AGENT_CREW_TASK_ID" > "$AGENT_CREW_BRIDGE_LOG"' \
    bash "${CREW}" run "auto bridge task" 2>&1
)
rc=$?
assert_exit 0 "${rc}"
assert_contains "${out}" "HOST_BRIDGE: auto_completed"
AUTO_TASK_DIR=$(printf '%s\n' "${out}" | awk -F': ' '/^TASK_DIR:/ {print $2; exit}')
AUTO_TASK_ID=$(basename "${AUTO_TASK_DIR}")

it "crew run host bridge command writes completion evidence"
assert_file_exists "${AUTO_TASK_DIR}/context/host-bridge-completion.json"
assert_contains "$(cat "${AUTO_TASK_DIR}/result.md")" "STATUS: completed"
assert_eq "${AUTO_TASK_ID}" "$(cat "${BRIDGE_LOG}")"

it "crew telemetry distinguishes auto host bridge completion"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" telemetry --format json --task-id "${AUTO_TASK_ID}" 2>&1)
assert_contains "${out}" "\"tasks_completed\": 1"
assert_contains "${out}" "\"host_bridge_status\": \"auto_completed\""
assert_contains "${out}" "\"auto_completed\": 1"

it "crew agent host bridge command can auto-complete direct requests"
AGENT_BRIDGE_LOG="$(make_tmp)/agent-host-bridge.log"
out=$(
  AGENT_CREW_HOME="${TMP_HOME}" \
  PROJECT_ROOT="${TMP_PROJECT}" \
  AGENT_CREW_BRIDGE_LOG="${AGENT_BRIDGE_LOG}" \
  AGENT_CREW_HOST_BRIDGE_COMMAND='printf "%s\n" "$AGENT_CREW_AGENT_REQUEST_ID" > "$AGENT_CREW_BRIDGE_LOG"' \
    bash "${CREW}" agent analyst "direct bridge agent" 2>&1
)
rc=$?
assert_exit 0 "${rc}"
assert_contains "${out}" "HOST_BRIDGE: auto_completed"
assert_contains "${out}" "STATUS: completed"
AGENT_REQUEST_ID=$(printf '%s\n' "${out}" | awk -F': ' '/^AGENT_REQUEST_ID:/ {print $2; exit}')
AGENT_REQUEST_DIR=$(printf '%s\n' "${out}" | awk -F': ' '/^REQUEST_DIR:/ {print $2; exit}')
assert_file_exists "${AGENT_REQUEST_DIR}/request.json"
assert_file_exists "${AGENT_REQUEST_DIR}/context/host-bridge-invocation.json"
assert_eq "${AGENT_REQUEST_ID}" "$(cat "${AGENT_BRIDGE_LOG}")"

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
