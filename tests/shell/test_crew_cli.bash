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

it "crew help mentions setup/status/telemetry/trace/cost/doctor/config/debug/readiness/question/resume/update/report/issue-ingest/cancel"
assert_contains "${out}" "setup [PROJECT_ROOT]"
assert_contains "${out}" "telemetry [args]"
assert_contains "${out}" "trace [args]"
assert_contains "${out}" "cost [args]"
assert_contains "${out}" "doctor [args]"
assert_contains "${out}" "config doctor|dump"
assert_contains "${out}" "debug [args]"
assert_contains "${out}" "readiness evidence|metrics|gate|workload"
assert_contains "${out}" "question key|record|resolve|render-markdown"
assert_contains "${out}" "resume [--print|--dry-run] TASK_ID"
assert_contains "${out}" "report auto|publish"
assert_contains "${out}" "issue-ingest ISSUE"
assert_contains "${out}" "cancel [--note TEXT] TASK_ID"

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
assert_contains "${out}" "core objective host autonomy ceiling"

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
assert_contains "${out}" "core_objective.host_runtime_ceiling:"

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

it "crew readiness evidence exits 0 with empty task directory"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" readiness evidence --format json 2>&1)
rc=$?
assert_exit 0 "${rc}"
assert_contains "${out}" '"tasks": 0'

it "crew readiness gate reports blockers with empty evidence"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" readiness gate --format json 2>&1)
rc=$?
assert_exit 1 "${rc}"
assert_contains "${out}" '"passed": false'
assert_contains "${out}" '"missing_validation_report"'

it "crew readiness workload generates explicit validation evidence"
WORKLOAD_OUTPUT="$(make_tmp)/workload.json"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" readiness workload --output "${WORKLOAD_OUTPUT}" --format text 2>&1)
rc=$?
assert_exit 0 "${rc}"
assert_contains "${out}" "PASS: readiness workload validation"
assert_file_exists "${WORKLOAD_OUTPUT}"
assert_contains "$(cat "${WORKLOAD_OUTPUT}")" '"source": "agent-crew-readiness-validation-workload"'

it "crew question records and resolves structured choices"
QUESTION_TASK_DIR="${TMP_HOME}/state/$(basename "${TMP_PROJECT}")/tasks/20260101-120001-0"
mkdir -p "${QUESTION_TASK_DIR}/context"
QUESTION_OPTIONS='[{"label":"Approve","description":"Proceed"},{"label":"Cancel","description":"Stop"}]'
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" question key --prompt "Proceed?" --options-json "${QUESTION_OPTIONS}" 2>&1)
rc=$?
assert_exit 0 "${rc}"
QUESTION_ID="$(printf '%s' "${out}" | tr -d '\n')"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" question record --task-dir "${QUESTION_TASK_DIR}" --question-id "${QUESTION_ID}" --prompt "Proceed?" --options-json "${QUESTION_OPTIONS}" --chosen-label "Approve" --source codex_plan_mode --adapter codex 2>&1)
rc=$?
assert_exit 0 "${rc}"
assert_contains "${out}" '"chosen_label": "Approve"'
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" question resolve --task-dir "${QUESTION_TASK_DIR}" --question-id "${QUESTION_ID}" 2>&1)
rc=$?
assert_exit 0 "${rc}"
assert_contains "${out}" '"found": true'
assert_contains "${out}" '"source": "codex_plan_mode"'

TRACE_HOME=$(make_tmp)
TRACE_PROJECT=$(make_tmp)
mkdir -p "${TRACE_PROJECT}"

it "crew run records provider-neutral delegation lineage"
out=$(AGENT_CREW_HOME="${TRACE_HOME}" PROJECT_ROOT="${TRACE_PROJECT}" bash "${CREW}" run "read docs" 2>&1)
rc=$?
assert_exit 0 "${rc}"
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

it "host bridge wait surfaces latest progress while command is running"
out=$(AGENT_CREW_HOME="${TOOL_HOME}" PROJECT_ROOT="${TOOL_PROJECT}" AGENT_CREW_BRIDGE_MONITOR_INTERVAL_SECONDS=0.1 bash "${CREW}" run --host-bridge-command "sleep 0.25; exit 7" "read-only wait monitor" 2>&1)
rc=$?
assert_exit 3 "${rc}"
assert_contains "${out}" "[crew] START"
assert_contains "${out}" "[crew] WAIT | task_id="
assert_contains "${out}" "phase=HOST_BRIDGE_START"
assert_contains "${out}" "last_update_age="
WAIT_TASK_DIR=$(printf '%s\n' "${out}" | awk -F': ' '/^TASK_DIR:/ {print $2; exit}')
assert_contains "$(cat "${WAIT_TASK_DIR}/context/host-bridge-invocation.json")" '"status": "failed"'
assert_contains "$(cat "${WAIT_TASK_DIR}/progress.buffer.jsonl")" "HOST_BRIDGE_START"

it "host bridge timeout records terminal failure evidence"
out=$(AGENT_CREW_HOME="${TOOL_HOME}" PROJECT_ROOT="${TOOL_PROJECT}" AGENT_CREW_BRIDGE_MONITOR_INTERVAL_SECONDS=0.05 AGENT_CREW_BRIDGE_TIMEOUT_SECONDS=0.15 bash "${CREW}" run --host-bridge-command "sleep 2" "read-only bridge timeout" 2>&1)
rc=$?
assert_exit 3 "${rc}"
assert_contains "${out}" "host AI bridge timed out"
TIMEOUT_TASK_ID=$(printf '%s\n' "${out}" | awk '/^TASK_ID:/ {print $2; exit}')
TIMEOUT_TASK_DIR=$(printf '%s\n' "${out}" | awk '/^TASK_DIR:/ {print $2; exit}')
timeout_register=$(cat "${TIMEOUT_TASK_DIR}/register.json")
timeout_invocation=$(cat "${TIMEOUT_TASK_DIR}/context/host-bridge-invocation.json")
timeout_tools=$(cat "${TIMEOUT_TASK_DIR}/tool-events.jsonl")
assert_contains "${timeout_register}" '"host_bridge_failure_reason": "bridge_timeout"'
assert_contains "${timeout_invocation}" '"timed_out": true'
assert_contains "${timeout_tools}" '"failure_class": "host_bridge_timeout"'
assert_contains "$(cat "${TIMEOUT_TASK_DIR}/progress.buffer.jsonl")" "HOST_BRIDGE_TIMEOUT"
out=$(AGENT_CREW_HOME="${TOOL_HOME}" PROJECT_ROOT="${TOOL_PROJECT}" bash "${CREW}" trace --task-id "${TIMEOUT_TASK_ID}" --include-tools 2>&1)
assert_contains "${out}" "host_bridge_timeout"

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
assert_contains "$(cat "${SETUP_HOME}/state/$(basename "${SETUP_PROJECT}")/capabilities.json")" '"interactive_question_mode": "codex_plan_mode_conditional"'

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
assert_exit 0 "${rc}"
assert_contains "${out}" "refreshed runtime assets"

it "crew run installs missing runtime repair script during auto-refresh"
assert_file_exists "${RUNTIME_SYNC_HOME}/scripts/repair-task-state.py"

it "crew run installs pipeline quality plan checker during auto-refresh"
assert_file_exists "${RUNTIME_SYNC_HOME}/scripts/pipeline-quality-plan-check.py"

it "crew run installs automatic issue reporter during auto-refresh"
assert_file_exists "${RUNTIME_SYNC_HOME}/scripts/auto-issue-reporter.py"

it "crew run installs readiness gate during auto-refresh"
assert_file_exists "${RUNTIME_SYNC_HOME}/scripts/readiness-gate.py"

it "crew run installs core objective helper during auto-refresh"
assert_file_exists "${RUNTIME_SYNC_HOME}/scripts/core_objective_lib.py"

it "crew run installs readiness workload validation during auto-refresh"
assert_file_exists "${RUNTIME_SYNC_HOME}/scripts/readiness-workload-validate.py"

it "crew run installs interactive question state helper during auto-refresh"
assert_file_exists "${RUNTIME_SYNC_HOME}/scripts/interactive-question-state.py"

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
assert_exit 0 "${rc}"

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
assert_exit 0 "${rc}"
assert_contains "${out}" "refreshed auto-route hooks"

it "crew run refreshes stale project-local hook after global hook is fresh"
assert_contains "$(cat "${HOOK_SYNC_PROJECT}/.codex/hooks/auto-route.sh")" 'Invoke Skill("crew-run")'

it "crew run writes deterministic state then exits handoff_ready"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" run "demo task" 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "crew run output includes task directory"
assert_contains "${out}" "TASK_DIR:"

it "crew run prints concise start banner"
assert_contains "${out}" "[crew] START"
assert_contains "${out}" "agent_uuid:"
assert_contains "${out}" "task_id:"
assert_contains "${out}" "branch:"
assert_contains "${out}" "state:"
assert_contains "${out}" "crew:status"

TASK_DIR=$(printf '%s\n' "${out}" | awk -F': ' '/^TASK_DIR:/ {print $2; exit}')

it "crew run writes register.json"
assert_file_exists "${TASK_DIR}/register.json"

it "crew run writes supervisor handoff"
assert_file_exists "${TASK_DIR}/handoff.md"

it "crew run writes handoff-ready result"
result=$(cat "${TASK_DIR}/result.md")
assert_contains "${result}" "STATUS: handoff_ready"

it "crew run handoff-ready result references internal bridge fallback"
assert_contains "${result}" "HOST_BRIDGE: internal_handoff_ready"

it "crew run blocked result includes concise next step guidance"
assert_contains "${result}" "NEXT: Continue with"

it "crew run handoff-ready result explains internal handoff behavior"
assert_contains "${result}" "agent-crew recorded a resumable internal handoff."

it "crew run handoff-ready result does not require shell profile bridge configuration"
assert_not_contains "${result}" "set AGENT_CREW_HOST_BRIDGE_COMMAND"

it "crew run routes Korean task text through input-normalizer gate"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" run "방금 멈춤 현상을 검증해주세요" 2>&1)
rc=$?
assert_exit 0 "${rc}"
KOREAN_RUN_TASK_DIR=$(printf '%s\n' "${out}" | awk -F': ' '/^TASK_DIR:/ {print $2; exit}')
register_json=$(cat "${KOREAN_RUN_TASK_DIR}/register.json")
pipeline_json=$(cat "${KOREAN_RUN_TASK_DIR}/pipeline.json")
run_result=$(cat "${KOREAN_RUN_TASK_DIR}/result.md")
assert_contains "${register_json}" '"task": "Normalize raw user input into a canonical English agent-crew workflow instruction.'
assert_contains "${pipeline_json}" '"input-normalizer"'
assert_contains "${run_result}" "NORMALIZATION_GATE: required"
assert_not_contains "${register_json}" "방금"
assert_not_contains "${pipeline_json}" "방금"
assert_not_contains "${run_result}" "방금"
assert_contains "$(cat "${KOREAN_RUN_TASK_DIR}/handoff.md")" "RAW_TASK: 방금 멈춤 현상을 검증해주세요"
assert_contains "$(cat "${KOREAN_RUN_TASK_DIR}/context/input-normalization.json")" '"source_language": "ko"'

it "crew run routes non-English multilingual input through input-normalizer gate"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" run "Corrigez ce problème" 2>&1)
rc=$?
assert_exit 0 "${rc}"
MULTI_RUN_TASK_DIR=$(printf '%s\n' "${out}" | awk -F': ' '/^TASK_DIR:/ {print $2; exit}')
multi_register_json=$(cat "${MULTI_RUN_TASK_DIR}/register.json")
multi_pipeline_json=$(cat "${MULTI_RUN_TASK_DIR}/pipeline.json")
assert_contains "${multi_register_json}" '"task": "Normalize raw user input into a canonical English agent-crew workflow instruction.'
assert_contains "${multi_pipeline_json}" '"input-normalizer"'
assert_not_contains "${multi_register_json}" "Corrigez"
assert_contains "$(cat "${MULTI_RUN_TASK_DIR}/context/input-normalization.json")" '"translation_required": true'

it "crew run routes ambiguous conversational input through input-normalizer gate"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" run "go" 2>&1)
rc=$?
assert_exit 0 "${rc}"
AMBIGUOUS_RUN_TASK_DIR=$(printf '%s\n' "${out}" | awk -F': ' '/^TASK_DIR:/ {print $2; exit}')
ambiguous_pipeline_json=$(cat "${AMBIGUOUS_RUN_TASK_DIR}/pipeline.json")
assert_contains "${ambiguous_pipeline_json}" '"input-normalizer"'
assert_contains "$(cat "${AMBIGUOUS_RUN_TASK_DIR}/context/input-normalization.json")" "short conversational shorthand"

it "crew run blocked result avoids verbose fallback narration"
assert_not_contains "${result}" "If the host bridge is unavailable"
assert_not_contains "${result}" "so `crew telemetry` no longer reports"

it "crew status --json reports handoff-ready run state"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" status --json 2>&1)
assert_contains "${out}" "\"handoff_ready\""
assert_contains "${out}" "\"internal_handoff_ready\""
assert_contains "${out}" "\"health\""
assert_contains "${out}" "\"latest_progress\""
assert_contains "${out}" "\"last_update_age_seconds\""

TASK_ID=$(basename "${TASK_DIR}")

it "crew telemetry --format json reports handoff-ready run as running"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" telemetry --format json --task-id "${TASK_ID}" 2>&1)
rc=$?
assert_exit 0 "${rc}"
assert_contains "${out}" "\"internal_handoff_ready\""
assert_contains "${out}" "\"tasks_running\": 1"
assert_contains "${out}" "\"health\": \"running\""
assert_contains "${out}" "\"latest_progress\""

it "crew status text surfaces latest progress and health"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" status 2>&1)
rc=$?
assert_exit 0 "${rc}"
assert_contains "${out}" "HEALTH"
assert_contains "${out}" "Latest progress:"
assert_contains "${out}" "${TASK_ID}: STATUS"
assert_contains "${out}" "unrecovered"

it "crew trace shows handoff-ready run progress events"
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

it "crew repair clears supervisor boot sentinel"
assert_file_absent "${TASK_DIR}/supervisor-pending.txt"

it "crew repair removes stale host bridge blocker from task telemetry"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" telemetry --format json --task-id "${TASK_ID}" 2>&1)
assert_contains "${out}" "\"tasks_completed\": 1"
assert_not_contains "${out}" "\"host_bridge_not_invoked\""

it "crew repair can mark an intentionally superseded handoff as cancelled"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" run "superseded handoff cleanup" 2>&1)
rc=$?
assert_exit 0 "${rc}"
CANCEL_TASK_DIR=$(printf '%s\n' "${out}" | awk -F': ' '/^TASK_DIR:/ {print $2; exit}')
CANCEL_TASK_ID=$(basename "${CANCEL_TASK_DIR}")
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" repair --status cancelled --note "user started a newer task" "${CANCEL_TASK_ID}" 2>&1)
rc=$?
assert_exit 0 "${rc}"
assert_contains "${out}" "STATUS: cancelled"
cancel_result=$(cat "${CANCEL_TASK_DIR}/result.md")
assert_contains "${cancel_result}" "STATUS: cancelled"
assert_contains "${cancel_result}" "BLOCKER: manual_fallback_cancelled"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" telemetry --format json --task-id "${CANCEL_TASK_ID}" 2>&1)
assert_contains "${out}" "\"tasks_cancelled\": 1"
assert_contains "${out}" "\"tasks_blocked\": 0"
assert_contains "${out}" "\"denominator_tasks\": 0"
assert_contains "${out}" "\"cancelled_tasks\": 1"
assert_contains "${out}" "\"success_rate\": null"
assert_contains "${out}" "\"cancelled\""

it "crew cancel is a concise wrapper for superseded handoffs"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" run "operator cancelled handoff" 2>&1)
rc=$?
assert_exit 0 "${rc}"
OP_CANCEL_TASK_DIR=$(printf '%s\n' "${out}" | awk -F': ' '/^TASK_DIR:/ {print $2; exit}')
OP_CANCEL_TASK_ID=$(basename "${OP_CANCEL_TASK_DIR}")
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" cancel --note "operator superseded task" "${OP_CANCEL_TASK_ID}" 2>&1)
rc=$?
assert_exit 0 "${rc}"
assert_contains "${out}" "STATUS: cancelled"
assert_contains "$(cat "${OP_CANCEL_TASK_DIR}/result.md")" "operator superseded task"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" telemetry --format json --task-id "${OP_CANCEL_TASK_ID}" 2>&1)
assert_contains "${out}" "\"manual_fallback_cancelled\""

it "crew cleanup-host-bridge dry-run finds stale host bridge task"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" run --host-bridge-command "exit 7" "cleanup stale host bridge task" 2>&1)
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

it "crew run discovers installed Codex bridge default from capabilities"
DEFAULT_BRIDGE_HOME="$(make_tmp)"
DEFAULT_BRIDGE_PROJECT="$(make_tmp)"
DEFAULT_BRIDGE_LOG="$(make_tmp)/default-bridge.log"
DEFAULT_BRIDGE_BIN="${DEFAULT_BRIDGE_HOME}/adapters/codex/bin/codex-host-bridge"
mkdir -p "$(dirname "${DEFAULT_BRIDGE_BIN}")" "${DEFAULT_BRIDGE_HOME}/state/$(basename "${DEFAULT_BRIDGE_PROJECT}")"
cat > "${DEFAULT_BRIDGE_HOME}/state/$(basename "${DEFAULT_BRIDGE_PROJECT}")/capabilities.json" <<EOF
{"host":"codex"}
EOF
cat > "${DEFAULT_BRIDGE_BIN}" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "${AGENT_CREW_TASK_ID}" > "${AGENT_CREW_DEFAULT_BRIDGE_LOG}"
EOF
chmod +x "${DEFAULT_BRIDGE_BIN}"
out=$(
  AGENT_CREW_HOME="${DEFAULT_BRIDGE_HOME}" \
  PROJECT_ROOT="${DEFAULT_BRIDGE_PROJECT}" \
  AGENT_CREW_DEFAULT_BRIDGE_LOG="${DEFAULT_BRIDGE_LOG}" \
    bash "${CREW}" run "default bridge task" 2>&1
)
rc=$?
assert_exit 0 "${rc}"
assert_contains "${out}" "HOST_BRIDGE: auto_completed"
DEFAULT_AUTO_TASK_DIR=$(printf '%s\n' "${out}" | awk -F': ' '/^TASK_DIR:/ {print $2; exit}')
DEFAULT_AUTO_TASK_ID=$(basename "${DEFAULT_AUTO_TASK_DIR}")
assert_eq "${DEFAULT_AUTO_TASK_ID}" "$(cat "${DEFAULT_BRIDGE_LOG}")"
assert_contains "$(cat "${DEFAULT_AUTO_TASK_DIR}/context/host-bridge-completion.json")" "${DEFAULT_BRIDGE_BIN}"

it "Codex host bridge command invokes codex exec with crew run handoff env"
CODEX_BRIDGE="${REPO_ROOT}/adapters/codex/bin/codex-host-bridge"
FAKE_CODEX_DIR="$(make_tmp)"
FAKE_CODEX="${FAKE_CODEX_DIR}/codex"
FAKE_CODEX_LOG="${FAKE_CODEX_DIR}/codex.log"
cat > "${FAKE_CODEX}" <<'EOF'
#!/usr/bin/env bash
set -u
{
  printf 'ARGS:%s\n' "$*"
  printf 'TASK_ID:%s\n' "${AGENT_CREW_TASK_ID:-}"
  printf 'TASK_DIR:%s\n' "${AGENT_CREW_TASK_DIR:-}"
  printf 'HANDOFF:%s\n' "${AGENT_CREW_HANDOFF_PATH:-}"
  printf 'RESULT:%s\n' "${AGENT_CREW_RESULT_PATH:-}"
  printf 'PROJECT_ROOT:%s\n' "${AGENT_CREW_PROJECT_ROOT:-}"
  printf 'ACTIVE:%s\n' "${AGENT_CREW_HOST_BRIDGE_ACTIVE:-}"
  printf 'AUTO_ROUTE_DISABLED:%s\n' "${AGENT_CREW_AUTO_ROUTE_DISABLED:-}"
  while IFS= read -r line; do
    printf 'PROMPT:%s\n' "${line}"
  done
} > "${AGENT_CREW_FAKE_CODEX_LOG}"
EOF
chmod +x "${FAKE_CODEX}"
out=$(
  AGENT_CREW_HOME="${TMP_HOME}" \
  PROJECT_ROOT="${TMP_PROJECT}" \
  AGENT_CREW_CODEX_BIN="${FAKE_CODEX}" \
  AGENT_CREW_CODEX_ALLOW_NESTED=1 \
  AGENT_CREW_FAKE_CODEX_LOG="${FAKE_CODEX_LOG}" \
  AGENT_CREW_HOST_BRIDGE_COMMAND="${CODEX_BRIDGE}" \
    bash "${CREW}" run "read docs" 2>&1
)
rc=$?
assert_exit 0 "${rc}"
assert_contains "${out}" "HOST_BRIDGE: auto_completed"
CODEX_AUTO_TASK_DIR=$(printf '%s\n' "${out}" | awk -F': ' '/^TASK_DIR:/ {print $2; exit}')
CODEX_AUTO_TASK_ID=$(basename "${CODEX_AUTO_TASK_DIR}")
RESOLVED_TMP_PROJECT=$(cd "${TMP_PROJECT}" && pwd -P)
assert_file_exists "${CODEX_AUTO_TASK_DIR}/context/codex-host-bridge-prompt.md"
assert_contains "$(cat "${FAKE_CODEX_LOG}")" "ARGS:--ask-for-approval never exec -C ${RESOLVED_TMP_PROJECT} --add-dir ${CODEX_AUTO_TASK_DIR} -o ${CODEX_AUTO_TASK_DIR}/context/codex-host-bridge-last-message.md -"
assert_contains "$(cat "${FAKE_CODEX_LOG}")" "TASK_ID:${CODEX_AUTO_TASK_ID}"
assert_contains "$(cat "${FAKE_CODEX_LOG}")" "TASK_DIR:${CODEX_AUTO_TASK_DIR}"
assert_contains "$(cat "${FAKE_CODEX_LOG}")" "HANDOFF:${CODEX_AUTO_TASK_DIR}/handoff.md"
assert_contains "$(cat "${FAKE_CODEX_LOG}")" "RESULT:${CODEX_AUTO_TASK_DIR}/result.md"
assert_contains "$(cat "${FAKE_CODEX_LOG}")" "PROJECT_ROOT:${RESOLVED_TMP_PROJECT}"
assert_contains "$(cat "${FAKE_CODEX_LOG}")" "ACTIVE:1"
assert_contains "$(cat "${FAKE_CODEX_LOG}")" "AUTO_ROUTE_DISABLED:1"
assert_contains "$(cat "${FAKE_CODEX_LOG}")" "PROMPT:Resume this existing agent-crew crew:run handoff in Codex."
assert_contains "$(cat "${FAKE_CODEX_LOG}")" "PROMPT:Do not run crew repair for normal bridge completion."
assert_contains "$(cat "${FAKE_CODEX_LOG}")" "Use repair guidance only when the task is genuinely blocked"

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
assert_file_exists "${AGENT_REQUEST_DIR}/result.md"
assert_file_exists "${AGENT_REQUEST_DIR}/context/host-bridge-invocation.json"
assert_file_exists "${AGENT_REQUEST_DIR}/context/host-bridge-completion.json"
assert_eq "${AGENT_REQUEST_ID}" "$(cat "${AGENT_BRIDGE_LOG}")"
assert_contains "$(cat "${AGENT_REQUEST_DIR}/result.md")" "## Bridge Output"

REQUEST_JSON=$(cat "${AGENT_REQUEST_DIR}/request.json")
assert_contains "${REQUEST_JSON}" '"status": "auto_completed"'
assert_contains "${REQUEST_JSON}" '"host_bridge_status": "auto_completed"'

it "crew agent treats nested Codex refusal as current-session handoff"
out=$(
  AGENT_CREW_HOME="${TMP_HOME}" \
  PROJECT_ROOT="${TMP_PROJECT}" \
  AGENT_CREW_HOST_BRIDGE_COMMAND='printf "%s\n" "AGENT_CREW_BRIDGE_STATUS: current_session_required" "codex-host-bridge: refusing nested Codex exec from an active Codex session" >&2; exit 2' \
    bash "${CREW}" agent analyst "current session handoff" 2>&1
)
rc=$?
assert_exit 0 "${rc}"
assert_contains "${out}" "STATUS: handoff_ready"
assert_contains "${out}" "HOST_BRIDGE: current_session_required"
assert_not_contains "${out}" "BLOCKER:"
CURRENT_SESSION_REQUEST_DIR=$(printf '%s\n' "${out}" | awk -F': ' '/^REQUEST_DIR:/ {print $2; exit}')
CURRENT_SESSION_REQUEST_JSON=$(cat "${CURRENT_SESSION_REQUEST_DIR}/request.json")
CURRENT_SESSION_INVOCATION_JSON=$(cat "${CURRENT_SESSION_REQUEST_DIR}/context/host-bridge-invocation.json")
CURRENT_SESSION_TOOL_EVENTS=$(cat "${CURRENT_SESSION_REQUEST_DIR}/tool-events.jsonl")
assert_contains "${CURRENT_SESSION_REQUEST_JSON}" '"host_bridge_status": "current_session_required"'
assert_contains "${CURRENT_SESSION_REQUEST_JSON}" '"host_bridge_failure_reason": "nested_codex_current_session_required"'
assert_contains "${CURRENT_SESSION_INVOCATION_JSON}" '"failure_class": "current_session_required"'
assert_contains "${CURRENT_SESSION_INVOCATION_JSON}" '"status": "current_session_required"'
assert_contains "${CURRENT_SESSION_TOOL_EVENTS}" '"status": "completed"'
assert_contains "$(cat "${CURRENT_SESSION_REQUEST_DIR}/progress.buffer.jsonl")" "HOST_BRIDGE_CURRENT_SESSION"
assert_file_absent "${CURRENT_SESSION_REQUEST_DIR}/result.md"

it "crew agent treats zero-exit blocked bridge output as failed"
out=$(
  AGENT_CREW_HOME="${TMP_HOME}" \
  PROJECT_ROOT="${TMP_PROJECT}" \
  AGENT_CREW_HOST_BRIDGE_COMMAND='printf "%s\n" "STATUS: blocked" "BLOCKER: downstream blocked"' \
    bash "${CREW}" agent analyst "direct bridge blocked output" 2>&1
)
rc=$?
assert_exit 3 "${rc}"
assert_contains "${out}" "STATUS: blocked"
assert_contains "${out}" "BLOCKER: host AI bridge has not completed this agent request"
BLOCKED_AGENT_REQUEST_DIR=$(printf '%s\n' "${out}" | awk -F': ' '/^REQUEST_DIR:/ {print $2; exit}')
BLOCKED_REQUEST_JSON=$(cat "${BLOCKED_AGENT_REQUEST_DIR}/request.json")
assert_contains "${BLOCKED_REQUEST_JSON}" '"host_bridge_status": "failed"'
assert_contains "${BLOCKED_REQUEST_JSON}" '"host_bridge_failure_reason": "bridge_reported_blocked"'
assert_file_exists "${BLOCKED_AGENT_REQUEST_DIR}/context/host-bridge-invocation.json"
assert_file_absent "${BLOCKED_AGENT_REQUEST_DIR}/context/host-bridge-completion.json"
assert_file_absent "${BLOCKED_AGENT_REQUEST_DIR}/result.md"

it "Codex host bridge command passes direct-agent request env"
FAKE_AGENT_CODEX_LOG="${FAKE_CODEX_DIR}/agent-codex.log"
out=$(
  AGENT_CREW_HOME="${TMP_HOME}" \
  PROJECT_ROOT="${TMP_PROJECT}" \
  AGENT_CREW_CODEX_BIN="${FAKE_CODEX}" \
  AGENT_CREW_CODEX_ALLOW_NESTED=1 \
  AGENT_CREW_FAKE_CODEX_LOG="${FAKE_AGENT_CODEX_LOG}" \
  AGENT_CREW_HOST_BRIDGE_COMMAND="${CODEX_BRIDGE}" \
    bash "${CREW}" agent analyst "explain routing" 2>&1
)
rc=$?
assert_exit 0 "${rc}"
assert_contains "${out}" "HOST_BRIDGE: auto_completed"
CODEX_AGENT_REQUEST_ID=$(printf '%s\n' "${out}" | awk -F': ' '/^AGENT_REQUEST_ID:/ {print $2; exit}')
CODEX_AGENT_REQUEST_DIR=$(printf '%s\n' "${out}" | awk -F': ' '/^REQUEST_DIR:/ {print $2; exit}')
assert_file_exists "${CODEX_AGENT_REQUEST_DIR}/context/codex-host-bridge-prompt.md"
assert_contains "$(cat "${FAKE_AGENT_CODEX_LOG}")" "TASK_ID:${CODEX_AGENT_REQUEST_ID}"
assert_contains "$(cat "${FAKE_AGENT_CODEX_LOG}")" "TASK_DIR:${CODEX_AGENT_REQUEST_DIR}"
assert_contains "$(cat "${FAKE_AGENT_CODEX_LOG}")" "HANDOFF:${CODEX_AGENT_REQUEST_DIR}/handoff.md"
assert_contains "$(cat "${FAKE_AGENT_CODEX_LOG}")" "RESULT:${CODEX_AGENT_REQUEST_DIR}/result.md"
assert_contains "$(cat "${FAKE_AGENT_CODEX_LOG}")" "PROMPT:Resume this existing agent-crew direct-agent handoff in Codex."
assert_contains "$(cat "${FAKE_AGENT_CODEX_LOG}")" "PROMPT:AGENT_CREW_AGENT_NAME: analyst"
assert_contains "$(cat "${FAKE_AGENT_CODEX_LOG}")" "PROMPT:AGENT_CREW_AGENT_REQUEST_ID: ${CODEX_AGENT_REQUEST_ID}"
assert_contains "$(cat "${FAKE_AGENT_CODEX_LOG}")" "PROMPT:AGENT_CREW_REQUEST_DIR: ${CODEX_AGENT_REQUEST_DIR}"
assert_contains "$(cat "${FAKE_AGENT_CODEX_LOG}")" "AUTO_ROUTE_DISABLED:1"

it "crew agent host bridge command failure keeps request resumable"
out=$(
  AGENT_CREW_HOME="${TMP_HOME}" \
  PROJECT_ROOT="${TMP_PROJECT}" \
  AGENT_CREW_HOST_BRIDGE_COMMAND='exit 42' \
    bash "${CREW}" agent analyst "failing bridge agent" 2>&1
)
rc=$?
assert_exit 3 "${rc}"
assert_contains "${out}" "BLOCKER: host AI bridge has not completed this agent request"
assert_contains "${out}" "STATUS: blocked"
AGENT_REQUEST_ID=$(printf '%s\n' "${out}" | awk -F': ' '/^AGENT_REQUEST_ID:/ {print $2; exit}')
AGENT_REQUEST_DIR=$(printf '%s\n' "${out}" | awk -F': ' '/^REQUEST_DIR:/ {print $2; exit}')
REQUEST_JSON=$(cat "${AGENT_REQUEST_DIR}/request.json")
assert_contains "${REQUEST_JSON}" '"status": "handoff_ready"'
assert_contains "${REQUEST_JSON}" '"host_bridge_status": "failed"'
assert_file_exists "${AGENT_REQUEST_DIR}/context/host-bridge-invocation.json"

it "crew agent host bridge timeout keeps request resumable"
out=$(
  AGENT_CREW_HOME="${TMP_HOME}" \
  PROJECT_ROOT="${TMP_PROJECT}" \
  AGENT_CREW_BRIDGE_MONITOR_INTERVAL_SECONDS=0.05 \
  AGENT_CREW_DIRECT_AGENT_BRIDGE_TIMEOUT_SECONDS=0.15 \
  AGENT_CREW_HOST_BRIDGE_COMMAND='sleep 2' \
    bash "${CREW}" agent analyst "timeout bridge agent" 2>&1
)
rc=$?
assert_exit 3 "${rc}"
assert_contains "${out}" "host AI bridge timed out"
TIMEOUT_AGENT_REQUEST_DIR=$(printf '%s\n' "${out}" | awk -F': ' '/^REQUEST_DIR:/ {print $2; exit}')
TIMEOUT_REQUEST_JSON=$(cat "${TIMEOUT_AGENT_REQUEST_DIR}/request.json")
TIMEOUT_INVOCATION_JSON=$(cat "${TIMEOUT_AGENT_REQUEST_DIR}/context/host-bridge-invocation.json")
assert_contains "${TIMEOUT_REQUEST_JSON}" '"status": "handoff_ready"'
assert_contains "${TIMEOUT_REQUEST_JSON}" '"host_bridge_failure_reason": "bridge_timeout"'
assert_contains "${TIMEOUT_REQUEST_JSON}" '"host_bridge_stall_class": "no_output_startup_stall"'
assert_contains "${TIMEOUT_INVOCATION_JSON}" '"timed_out": true'
assert_contains "${TIMEOUT_INVOCATION_JSON}" '"stall_class": "no_output_startup_stall"'
assert_contains "$(cat "${TIMEOUT_AGENT_REQUEST_DIR}/tool-events.jsonl")" '"failure_class": "host_bridge_timeout"'
assert_contains "$(cat "${TIMEOUT_AGENT_REQUEST_DIR}/progress.buffer.jsonl")" "DIRECT_AGENT_REQUEST"
assert_contains "$(cat "${TIMEOUT_AGENT_REQUEST_DIR}/progress.buffer.jsonl")" "HOST_BRIDGE_START"
assert_not_contains "${out}" "no progress events yet"

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

it "crew agent keeps intended agent for Korean inline normalization"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" agent analyst "방금 질문을 설명해주세요" 2>&1)
rc=$?
assert_exit 0 "${rc}"
KOREAN_REQUEST_DIR=$(printf '%s\n' "${out}" | awk -F': ' '/^REQUEST_DIR:/ {print $2; exit}')
request_json=$(cat "${KOREAN_REQUEST_DIR}/request.json")
assert_contains "${request_json}" '"agent": "analyst"'
assert_contains "${request_json}" '"normalization_status": "required"'
assert_contains "${request_json}" '"normalization_mode": "inline_direct_bridge"'
assert_contains "${request_json}" '"normalization_agent": "input-normalizer"'
assert_contains "${request_json}" '"intended_agent_after_normalization": "analyst"'
assert_not_contains "${request_json}" "방금"
assert_contains "$(cat "${KOREAN_REQUEST_DIR}/handoff.md")" "RAW_TASK: 방금 질문을 설명해주세요"
assert_contains "$(cat "${KOREAN_REQUEST_DIR}/handoff.md")" "NORMALIZATION_MODE: inline_direct_bridge"
assert_contains "$(cat "${KOREAN_REQUEST_DIR}/handoff.md")" "Do not spawn input-normalizer"

it "crew agent blocks Korean mutating direct requests before normalization"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" agent analyst "파일을 수정해주세요" 2>&1)
rc=$?
assert_exit 2 "${rc}"
assert_contains "${out}" "Use crew run for mutating work"

ISSUE_BIN=$(make_tmp)
mkdir -p "${ISSUE_BIN}"
cat > "${ISSUE_BIN}/gh" <<'GH'
#!/usr/bin/env bash
cat <<'JSON'
{
  "number": 77,
  "title": "Body misses comment requirement",
  "url": "https://github.com/example/repo/issues/77",
  "body": "Fix the normalizer.",
  "labels": [{"name": "enhancement"}],
  "comments": [
    {
      "body": "- must ingest comments before planning\n- should record comments_ingested evidence",
      "createdAt": "2026-05-24T00:00:00Z",
      "url": "https://github.com/example/repo/issues/77#issuecomment-1",
      "isMinimized": false,
      "minimizedReason": ""
    }
  ]
}
JSON
GH
chmod +x "${ISSUE_BIN}/gh"
ISSUE_TASK_ID="20260101-010101-0"
ISSUE_TASK_DIR="${TMP_HOME}/state/$(basename "${TMP_PROJECT}")/tasks/${ISSUE_TASK_ID}"
mkdir -p "${ISSUE_TASK_DIR}/context"

it "crew issue-ingest records issue body and comments before planning"
out=$(PATH="${ISSUE_BIN}:${PATH}" AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" issue-ingest 77 --task-id "${ISSUE_TASK_ID}" --repo example/repo --format json 2>&1)
rc=$?
assert_exit 0 "${rc}"
assert_contains "${out}" '"comments_ingested": true'
assert_contains "${out}" '"comment_count": 1'
assert_contains "${out}" "must ingest comments before planning"
assert_file_exists "${ISSUE_TASK_DIR}/context/issue-77-ingestion.json"

it "crew run automatically ingests referenced issue comments before planning"
out=$(PATH="${ISSUE_BIN}:${PATH}" AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" run "resolve #77" 2>&1)
rc=$?
assert_exit 0 "${rc}"
ISSUE_RUN_TASK_DIR=$(printf '%s\n' "${out}" | awk -F': ' '/^TASK_DIR:/ {print $2; exit}')
assert_file_exists "${ISSUE_RUN_TASK_DIR}/context/issue-77-ingestion.json"
issue_run_register=$(cat "${ISSUE_RUN_TASK_DIR}/register.json")
issue_run_ingestion=$(cat "${ISSUE_RUN_TASK_DIR}/context/issue-77-ingestion.json")
assert_contains "${issue_run_register}" '"issue_comment_ingestion"'
assert_contains "${issue_run_ingestion}" '"comments_ingested": true'
assert_contains "${issue_run_ingestion}" "should record comments_ingested evidence"

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
