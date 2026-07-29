#!/usr/bin/env bash
# Tests for core/bin/memory wrapper behavior.

set -u

# shellcheck source=./_lib.bash
source "$(dirname "$0")/_lib.bash"
set +e

MEMORY="${REPO_ROOT}/core/bin/memory"

it "crew CLI exists next to memory wrapper"
assert_file_exists "${REPO_ROOT}/core/bin/crew"

TMP=$(make_tmp)
cat > "${TMP}/mnemos" <<'SH'
#!/usr/bin/env bash
if [ "${1:-}" = "capture" ]; then
  if [ "${MNEMOS_BACKEND:-}" != "default" ]; then
    echo "missing default support backend"
    exit 9
  fi
  case " $* " in
    *" --no-classify "*) ;;
    *) echo "missing --no-classify"; exit 9 ;;
  esac
  cat <<'OUT'
captured memory id: 0716384d-091f-4279-838f-73d54785767a
error: git command failed (rc=1): remote rejected main -> main (cannot lock ref)
error: failed to push some refs
OUT
  exit 1
fi
printf 'mnemos %s\n' "$*"
exit 0
SH
chmod +x "${TMP}/mnemos"

it "memory capture returns success when local capture id exists but vault push failed"
OUTPUT=$(MNEMOS_BIN="${TMP}/mnemos" bash "${MEMORY}" capture --layer session --content "probe" 2>&1)
rc=$?
assert_exit 0 "${rc}" "nonfatal sync failure"

it "memory capture emits local capture warning"
assert_contains "${OUTPUT}" "[memory] captured locally: 0716384d-091f-4279-838f-73d54785767a"

it "memory capture emits vault sync warning"
assert_contains "${OUTPUT}" "[memory] warning: vault sync failed or is locked"

it "memory capture adds --no-classify by default"
assert_not_contains "${OUTPUT}" "missing --no-classify"

it "memory capture defaults agent-crew support writes to local mnemos backend"
assert_not_contains "${OUTPUT}" "missing default support backend"

TMP=$(make_tmp)
cat > "${TMP}/mnemos" <<'SH'
#!/usr/bin/env bash
if [ "${1:-}" = "capture" ]; then
  printf 'backend=%s\n' "${MNEMOS_BACKEND:-}"
  exit 0
fi
exit 0
SH
chmod +x "${TMP}/mnemos"

it "memory capture preserves explicit MNEMOS_BACKEND override"
OUTPUT=$(MNEMOS_BACKEND=obsidian MNEMOS_BIN="${TMP}/mnemos" bash "${MEMORY}" capture --layer session --content "probe" 2>&1)
rc=$?
assert_exit 0 "${rc}" "explicit backend preserved"
assert_contains "${OUTPUT}" "backend=obsidian"

TMP=$(make_tmp)
cat > "${TMP}/mnemos" <<'SH'
#!/usr/bin/env bash
if [ "${1:-}" = "read" ]; then
  printf 'read-backend=%s\n' "${MNEMOS_BACKEND:-}"
  exit 0
fi
exit 0
SH
chmod +x "${TMP}/mnemos"

it "memory read defaults to the same local support backend as capture"
OUTPUT=$(MNEMOS_BIN="${TMP}/mnemos" bash "${MEMORY}" read 0716384d-091f-4279-838f-73d54785767a 2>&1)
rc=$?
assert_exit 0 "${rc}" "read default backend"
assert_contains "${OUTPUT}" "read-backend=default"

it "memory read preserves explicit MNEMOS_BACKEND override"
OUTPUT=$(MNEMOS_BACKEND=obsidian MNEMOS_BIN="${TMP}/mnemos" bash "${MEMORY}" read 0716384d-091f-4279-838f-73d54785767a 2>&1)
rc=$?
assert_exit 0 "${rc}" "read explicit backend"
assert_contains "${OUTPUT}" "read-backend=obsidian"

TMP=$(make_tmp)
cat > "${TMP}/mnemos" <<'SH'
#!/usr/bin/env bash
printf 'timeout=%s\n' "${AGENT_CREW_MNEMOS_TIMEOUT_SECONDS:-}"
exit 0
SH
chmod +x "${TMP}/mnemos"

it "memory wrapper default bounded timeout matches mnemos-bounded default"
OUTPUT=$(MNEMOS_BIN="${TMP}/mnemos" bash "${MEMORY}" read 0716384d-091f-4279-838f-73d54785767a 2>&1)
rc=$?
assert_exit 0 "${rc}" "default bounded timeout"
assert_contains "${OUTPUT}" "timeout=8"

TMP=$(make_tmp)
cat > "${TMP}/mnemos" <<'SH'
#!/usr/bin/env bash
if [ "${1:-}" = "capture" ]; then
  cat <<'OUT'
error: git command failed (rc=128): fatal: Unable to create '/tmp/vault/.git/index.lock': File exists.
Another git process seems to be running in this repository.
OUT
  exit 1
fi
exit 0
SH
chmod +x "${TMP}/mnemos"

it "memory capture treats vault index lock as non-blocking"
OUTPUT=$(MNEMOS_BIN="${TMP}/mnemos" bash "${MEMORY}" capture --layer session --content "probe" 2>&1)
rc=$?
assert_exit 0 "${rc}" "index lock is support-path failure"
assert_contains "${OUTPUT}" "capture could not confirm a local id"

TMP=$(make_tmp)
cat > "${TMP}/mnemos" <<'SH'
#!/usr/bin/env bash
if [ "${1:-}" = "capture" ]; then
  echo "fatal: invalid arguments"
  exit 7
fi
exit 0
SH
chmod +x "${TMP}/mnemos"

it "memory capture preserves non-sync failures"
MNEMOS_BIN="${TMP}/mnemos" bash "${MEMORY}" capture --bad >/dev/null 2>&1
rc=$?
assert_exit 7 "${rc}" "non-sync capture failure"

TMP=$(make_tmp)
cat > "${TMP}/mnemos" <<'SH'
#!/usr/bin/env bash
sleep 5
echo "late mnemos output"
exit 0
SH
chmod +x "${TMP}/mnemos"

it "memory recall mode legacy uses bounded mnemos timeout"
OUTPUT=$(AGENT_CREW_MEMORY_RECALL_MODE=legacy AGENT_CREW_MNEMOS_TIMEOUT_SECONDS=1 MNEMOS_BIN="${TMP}/mnemos" bash "${MEMORY}" search slow 2>&1)
rc=$?
assert_exit 124 "${rc}" "search timeout"
assert_contains "${OUTPUT}" "mnemos-bounded: timed out after 1s"

TMP=$(make_tmp)
cat > "${TMP}/mnemos" <<'SH'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "${MNEMOS_CALL_LOG}"
if [ "${1:-}" = "capabilities" ] && [ "${2:-}" = "--json" ]; then
  cat <<'JSON'
{"commands":{"recall":{"json":true},"feedback":{"json":true}}}
JSON
  exit 0
fi
if [ "${1:-}" = "recall" ] && [ "${2:-}" = "--json" ] && [ "${3:-}" = "--request-file" ]; then
  python3 - "$4" <<'PY' >> "${MNEMOS_CALL_LOG}"
import json, sys
path = sys.argv[1]
with open(path, encoding="utf-8") as handle:
    payload = json.load(handle)
print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
PY
  cat <<'JSON'
{"status":"ok","results":[{"id":"recall-v2-1","content":"full v2 content that must not be truncated by agent-crew wrapper","score":0.87}]}
JSON
  exit 0
fi
if [ "${1:-}" = "feedback" ] && [ "${2:-}" = "--json" ] && [ "${3:-}" = "--request-file" ]; then
  python3 - "$4" <<'PY' >> "${MNEMOS_CALL_LOG}"
import json, sys
path = sys.argv[1]
with open(path, encoding="utf-8") as handle:
    payload = json.load(handle)
print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
PY
  cat <<'JSON'
{"status":"ok","feedback_id":"fb-1"}
JSON
  exit 0
fi
if [ "${1:-}" = "search" ]; then
  printf 'legacy-search-result\n'
  exit 0
fi
echo "unexpected $*"
exit 9
SH
chmod +x "${TMP}/mnemos"
CALL_LOG="${TMP}/calls.log"

it "memory search defaults to recall v2 and avoids legacy search"
rm -f "${CALL_LOG}"
OUTPUT=$(MNEMOS_CALL_LOG="${CALL_LOG}" MNEMOS_BIN="${TMP}/mnemos" bash "${MEMORY}" search "probe" --limit 5 2>&1)
rc=$?
assert_exit 0 "${rc}" "default v2 mode"
assert_contains "${OUTPUT}" '"status":"ok"'
assert_contains "${OUTPUT}" "full v2 content that must not be truncated"
assert_contains "$(cat "${CALL_LOG}")" "recall --json --request-file"
assert_not_contains "$(cat "${CALL_LOG}")" "search probe"

it "memory wrapper contains no direct SQLite or FTS fallback"
MEMORY_TEXT=$(sed -n '1,760p' "${MEMORY}")
assert_not_contains "${MEMORY_TEXT}" ".agent/state/fts.db"
assert_not_contains "${MEMORY_TEXT}" "sqlite3"
assert_not_contains "${MEMORY_TEXT}" "mnemos-fast"

it "memory recall mode off disables search without provider calls"
rm -f "${CALL_LOG}"
OUTPUT=$(MNEMOS_CALL_LOG="${CALL_LOG}" AGENT_CREW_MEMORY_RECALL_MODE=off MNEMOS_BIN="${TMP}/mnemos" bash "${MEMORY}" search "probe" --limit 5 2>&1)
rc=$?
assert_exit 0 "${rc}" "off mode"
assert_contains "${OUTPUT}" "status=disabled"
assert_file_absent "${CALL_LOG}"

it "memory recall mode legacy keeps legacy search output"
OUTPUT=$(MNEMOS_CALL_LOG="${CALL_LOG}" AGENT_CREW_MEMORY_RECALL_MODE=legacy MNEMOS_BIN="${TMP}/mnemos" bash "${MEMORY}" search "probe" --limit 5 2>&1)
rc=$?
assert_exit 0 "${rc}" "legacy mode"
assert_contains "${OUTPUT}" "legacy-search-result"
assert_not_contains "${OUTPUT}" "recall-v2-1"

it "memory recall mode shadow runs recall v2 but returns legacy output"
rm -f "${CALL_LOG}"
OUTPUT=$(MNEMOS_CALL_LOG="${CALL_LOG}" AGENT_CREW_MEMORY_RECALL_MODE=shadow MNEMOS_BIN="${TMP}/mnemos" bash "${MEMORY}" search "probe" --limit 5 2>&1)
rc=$?
assert_exit 0 "${rc}" "shadow mode"
assert_contains "${OUTPUT}" "legacy-search-result"
assert_not_contains "${OUTPUT}" "recall-v2-1"
assert_contains "$(cat "${CALL_LOG}")" "recall --json --request-file"
assert_contains "$(cat "${CALL_LOG}")" '"read_only": true'
assert_contains "$(cat "${CALL_LOG}")" '"text": "probe"'

it "memory recall mode v2 preserves recall JSON stdout without legacy fallback"
rm -f "${CALL_LOG}"
OUTPUT=$(MNEMOS_CALL_LOG="${CALL_LOG}" AGENT_CREW_MEMORY_RECALL_MODE=v2 MNEMOS_BIN="${TMP}/mnemos" bash "${MEMORY}" search "probe" --limit 5 2>&1)
rc=$?
assert_exit 0 "${rc}" "v2 mode"
assert_contains "${OUTPUT}" '"status":"ok"'
assert_contains "${OUTPUT}" "full v2 content that must not be truncated"
assert_not_contains "${OUTPUT}" "legacy-search-result"
assert_contains "$(cat "${CALL_LOG}")" "recall --json --request-file"
assert_contains "$(cat "${CALL_LOG}")" '"selected_limit": 5'

it "memory feedback is disabled unless the feedback flag is enabled"
rm -f "${CALL_LOG}"
OUTPUT=$(MNEMOS_CALL_LOG="${CALL_LOG}" AGENT_CREW_MEMORY_FEEDBACK=0 MNEMOS_BIN="${TMP}/mnemos" bash "${MEMORY}" feedback --event used 2>&1)
rc=$?
assert_exit 0 "${rc}" "feedback disabled"
assert_contains "${OUTPUT}" "status=disabled"
assert_file_absent "${CALL_LOG}"

it "memory feedback forwards JSON when the feedback flag is enabled"
OUTPUT=$(MNEMOS_CALL_LOG="${CALL_LOG}" AGENT_CREW_MEMORY_FEEDBACK=1 MNEMOS_BIN="${TMP}/mnemos" bash "${MEMORY}" feedback --request-json '{"schema_version":"mnemos.feedback.request.v1","event_id":"event-1","event":"applied","memory_id":"mem-1","task_id":"task-1"}' 2>&1)
rc=$?
assert_exit 0 "${rc}" "feedback enabled"
assert_contains "${OUTPUT}" '"feedback_id":"fb-1"'
assert_contains "$(cat "${CALL_LOG}")" "feedback --json --request-file"
assert_contains "$(cat "${CALL_LOG}")" '"event_id": "event-1"'

TMP=$(make_tmp)
cat > "${TMP}/mnemos" <<'SH'
#!/usr/bin/env bash
if [ "${1:-}" = "capabilities" ] && [ "${2:-}" = "--json" ]; then
  cat <<'JSON'
{"commands":{"search":{"fast":true,"json":true}}}
JSON
  exit 0
fi
if [ "${1:-}" = "search" ]; then
  printf 'legacy-only-provider\n'
  exit 0
fi
echo "unexpected $*"
exit 9
SH
chmod +x "${TMP}/mnemos"

it "memory recall mode v2 reports incompatible provider without legacy fallback"
OUTPUT=$(AGENT_CREW_MEMORY_RECALL_MODE=v2 MNEMOS_BIN="${TMP}/mnemos" bash "${MEMORY}" search "probe" --limit 5 2>&1)
rc=$?
assert_exit 0 "${rc}" "v2 incompatible non-strict"
assert_contains "${OUTPUT}" "incompatible_provider"
assert_not_contains "${OUTPUT}" "legacy-only-provider"

it "memory strict mode makes incompatible provider fail"
OUTPUT=$(AGENT_CREW_MEMORY_RECALL_MODE=v2 AGENT_CREW_MEMORY_STRICT=1 MNEMOS_BIN="${TMP}/mnemos" bash "${MEMORY}" search "probe" --limit 5 2>&1)
rc=$?
assert_exit 2 "${rc}" "v2 incompatible strict"
assert_contains "${OUTPUT}" "incompatible_provider"

TMP=$(make_tmp)
cat > "${TMP}/mnemos" <<'SH'
#!/usr/bin/env bash
if [ "${1:-}" = "capabilities" ]; then
  printf 'not json\n'
  exit 0
fi
exit 9
SH
chmod +x "${TMP}/mnemos"

it "memory recall mode v2 reports invalid capabilities json"
OUTPUT=$(AGENT_CREW_MEMORY_RECALL_MODE=v2 MNEMOS_BIN="${TMP}/mnemos" bash "${MEMORY}" search "probe" --limit 5 2>&1)
rc=$?
assert_exit 0 "${rc}" "v2 invalid json non-strict"
assert_contains "${OUTPUT}" "invalid_json"

TMP=$(make_tmp)
cat > "${TMP}/mnemos" <<'SH'
#!/usr/bin/env bash
if [ "${1:-}" = "capabilities" ] && [ "${2:-}" = "--json" ]; then
  cat <<'JSON'
{"commands":{"recall":{"json":true}}}
JSON
  exit 0
fi
if [ "${1:-}" = "recall" ]; then
  printf '{"status":"degraded","results":[],"warning":"backend degraded"}\n'
  exit 0
fi
exit 9
SH
chmod +x "${TMP}/mnemos"

it "memory recall mode v2 preserves degraded provider json"
OUTPUT=$(AGENT_CREW_MEMORY_RECALL_MODE=v2 MNEMOS_BIN="${TMP}/mnemos" bash "${MEMORY}" search "probe" --limit 5 2>&1)
rc=$?
assert_exit 0 "${rc}" "v2 degraded"
assert_contains "${OUTPUT}" '"status":"degraded"'
assert_contains "${OUTPUT}" "backend degraded"

TMP=$(make_tmp)
cat > "${TMP}/mnemos" <<'SH'
#!/usr/bin/env bash
if [ "${1:-}" = "capabilities" ] && [ "${2:-}" = "--json" ]; then
  cat <<'JSON'
{"commands":{"recall":{"json":true}}}
JSON
  exit 0
fi
if [ "${1:-}" = "recall" ]; then
  sleep 5
fi
exit 0
SH
chmod +x "${TMP}/mnemos"

it "memory recall mode v2 reports timeout distinctly"
OUTPUT=$(AGENT_CREW_MEMORY_RECALL_MODE=v2 AGENT_CREW_MNEMOS_TIMEOUT_SECONDS=1 MNEMOS_BIN="${TMP}/mnemos" bash "${MEMORY}" search "probe" --limit 5 2>&1)
rc=$?
assert_exit 0 "${rc}" "v2 timeout"
assert_contains "${OUTPUT}" "timeout"

it "memory recall mode v2 reports unavailable when mnemos is missing"
OUTPUT=$(AGENT_CREW_MEMORY_RECALL_MODE=v2 MNEMOS_BIN="${TMP}/missing-mnemos" bash "${MEMORY}" search "probe" --limit 5 2>&1)
rc=$?
assert_exit 0 "${rc}" "v2 unavailable"
assert_contains "${OUTPUT}" "unavailable"

TMP=$(make_tmp)
cat > "${TMP}/mnemos" <<'SH'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "${MNEMOS_CALL_LOG}"
if [ "${1:-}" = "gc" ]; then
  printf '{"status":"ok","mode":"provider-gc"}\n'
  exit 0
fi
echo "unexpected $*"
exit 9
SH
chmod +x "${TMP}/mnemos"
CALL_LOG="${TMP}/gc-calls.log"

it "memory gc delegates to mnemos provider without agent-crew FTS analysis"
OUTPUT=$(MNEMOS_CALL_LOG="${CALL_LOG}" MNEMOS_BIN="${TMP}/mnemos" bash "${MEMORY}" gc --format json --apply 2>&1)
rc=$?
assert_exit 0 "${rc}" "memory gc provider delegation"
assert_contains "${OUTPUT}" '"mode":"provider-gc"'
assert_contains "$(cat "${CALL_LOG}")" "gc --format json --apply"

it "memory search reports unsupported score support for non-FTS backend"
TMP=$(make_tmp)
cat > "${TMP}/mnemos" <<'SH'
#!/usr/bin/env bash
printf 'mnemos %s\n' "$*"
exit 0
SH
chmod +x "${TMP}/mnemos"
OUTPUT=$(AGENT_CREW_MEMORY_RECALL_MODE=legacy AGENT_CREW_MEMORY_REPORT_SCORE_SUPPORT=1 MNEMOS_BIN="${TMP}/mnemos" bash "${MEMORY}" search "probe" 2>&1)
rc=$?
assert_exit 0 "${rc}" "unsupported score reporting"
assert_contains "${OUTPUT}" "score_support=unsupported"

TMP=$(make_tmp)
cat > "${TMP}/mnemos" <<'SH'
#!/usr/bin/env bash
sleep 5
echo "late mnemos output"
exit 0
SH
chmod +x "${TMP}/mnemos"

it "memory capture timeout is non-blocking"
OUTPUT=$(AGENT_CREW_MNEMOS_TIMEOUT_SECONDS=1 MNEMOS_BIN="${TMP}/mnemos" bash "${MEMORY}" capture --layer session --content slow 2>&1)
rc=$?
assert_exit 0 "${rc}" "capture timeout"
assert_contains "${OUTPUT}" "[memory] warning: capture timed out"

TMP=$(make_tmp)
it "memory convention capture uses the local convention cache without mnemos"
OUTPUT=$(MNEMOS_BIN="${TMP}/missing-mnemos" bash "${MEMORY}" convention capture --owner alice --cache-dir "${TMP}/cache" --content "Prefer pathlib for new Python paths." 2>&1)
rc=$?
assert_exit 0 "${rc}" "convention capture"
assert_contains "${OUTPUT}" '"id"'

it "memory convention capture writes owner-scoped cache"
assert_file_exists "${TMP}/cache/alice.json"

end_report
