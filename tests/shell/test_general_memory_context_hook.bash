#!/usr/bin/env bash
set -u

source "$(dirname "$0")/_lib.bash"

HOOK="${HOOKS_DIR}/general-memory-context.sh"
TMP="$(make_tmp)"
MEMORY_BIN="${TMP}/memory"
CALLS="${TMP}/calls.txt"

cat > "${MEMORY_BIN}" <<EOF
#!/usr/bin/env bash
printf '%s\n' "\$*" >> "${CALLS}"
cat <<'JSON'
{"status":"ok","results":[{"memory_id":"mem-1","layer":"project","content":"과거에 검증한 재사용 가능한 결정"}]}
JSON
EOF
chmod +x "${MEMORY_BIN}"

it "general memory hook recalls ordinary conversation through the memory wrapper"
out=$(printf '%s' '{"hook_event_name":"UserPromptSubmit","prompt":"지난 결정을 참고해서 설명해줘"}' | \
  AGENT_CREW_MEMORY_BIN="${MEMORY_BIN}" bash "${HOOK}")
assert_contains "$(cat "${CALLS}" 2>/dev/null || true)" "search 지난 결정을 참고해서 설명해줘 --limit 5"

it "general memory hook injects recalled content as advisory context"
assert_contains "${out}" "과거에 검증한 재사용 가능한 결정"

it "general memory hook instructs explicit durable capture without automatic persistence"
assert_contains "${out}" "memory capture"
assert_contains "${out}" "자동으로 저장하지 마라"

it "general memory hook emits valid UserPromptSubmit hook JSON"
hook_event=$(printf '%s' "${out}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["hookSpecificOutput"]["hookEventName"])')
assert_eq "UserPromptSubmit" "${hook_event}"

cat > "${MEMORY_BIN}" <<EOF
#!/usr/bin/env bash
printf '%s\n' "\$*" >> "${CALLS}"
printf '%s\n' '{"status":"ok","results":[]}'
EOF
chmod +x "${MEMORY_BIN}"

it "general memory hook keeps explicit capture guidance when recall has no matches"
out=$(printf '%s' '{"hook_event_name":"UserPromptSubmit","prompt":"새로운 일반 질문"}' | \
  AGENT_CREW_MEMORY_BIN="${MEMORY_BIN}" bash "${HOOK}")
assert_contains "${out}" "memory capture"

: > "${CALLS}"
it "general memory hook skips explicit crew workflow commands"
out=$(printf '%s' '{"hook_event_name":"UserPromptSubmit","prompt":"$crew:run 테스트를 실행해줘"}' | \
  AGENT_CREW_MEMORY_BIN="${MEMORY_BIN}" bash "${HOOK}")
assert_eq "" "${out}"
assert_eq "" "$(cat "${CALLS}")"

: > "${CALLS}"
it "general memory hook skips native space-separated crew commands"
out=$(printf '%s' '{"hook_event_name":"UserPromptSubmit","prompt":"crew run 테스트를 실행해줘"}' | \
  AGENT_CREW_MEMORY_BIN="${MEMORY_BIN}" bash "${HOOK}")
assert_eq "" "${out}"
assert_eq "" "$(cat "${CALLS}")"

: > "${CALLS}"
it "general memory hook skips slash commands"
out=$(printf '%s' '{"hook_event_name":"UserPromptSubmit","prompt":"/review"}' | \
  AGENT_CREW_MEMORY_BIN="${MEMORY_BIN}" bash "${HOOK}")
assert_eq "" "${out}"
assert_eq "" "$(cat "${CALLS}")"

cat > "${MEMORY_BIN}" <<EOF
#!/usr/bin/env bash
printf '%s\n' "\$*" >> "${CALLS}"
exit 124
EOF
chmod +x "${MEMORY_BIN}"

it "general memory hook fails open when recall times out"
out=$(printf '%s' '{"hook_event_name":"UserPromptSubmit","prompt":"일반 질문"}' | \
  AGENT_CREW_MEMORY_BIN="${MEMORY_BIN}" bash "${HOOK}" 2>/dev/null)
rc=$?
assert_exit 0 "${rc}"
assert_eq "" "${out}"

it "Codex setup registers the general memory hook for user prompts"
assert_contains "$(cat "${REPO_ROOT}/adapters/codex/setup.sh")" "general-memory-context.sh"

it "Claude setup registers the general memory hook for user prompts"
assert_contains "$(cat "${REPO_ROOT}/adapters/claude/setup.sh")" "general-memory-context.sh"

end_report
