#!/usr/bin/env bash
# Tests for core/scripts/mnemos-bounded.sh.

set -u

# shellcheck source=./_lib.bash
source "$(dirname "$0")/_lib.bash"
set +e

SCRIPT="${SCRIPTS_DIR}/mnemos-bounded.sh"
TMP=$(make_tmp)

cat > "${TMP}/mnemos-fast" <<'SH'
#!/usr/bin/env bash
printf 'mnemos-fast %s\n' "$*"
exit 0
SH
chmod +x "${TMP}/mnemos-fast"

it "mnemos-bounded forwards stdout and exit code"
OUT=$(MNEMOS_BIN="${TMP}/mnemos-fast" bash "${SCRIPT}" search agent-crew 2>&1)
rc=$?
assert_exit 0 "${rc}" "fast command"

it "mnemos-bounded forwards command arguments"
assert_contains "${OUT}" "mnemos-fast search agent-crew" "argument forwarding"

it "mnemos-bounded does not timeout a completed command while polling"
OUT=$(AGENT_CREW_MNEMOS_TIMEOUT_SECONDS=1 AGENT_CREW_MNEMOS_POLL_INTERVAL_SECONDS=2 MNEMOS_BIN="${TMP}/mnemos-fast" \
  bash "${SCRIPT}" search quick 2>&1)
rc=$?
assert_exit 0 "${rc}" "completed command should not be treated as timed out"
assert_contains "${OUT}" "mnemos-fast search quick"

cat > "${TMP}/mnemos-slow" <<'SH'
#!/usr/bin/env bash
sleep 5
echo "late output"
exit 0
SH
chmod +x "${TMP}/mnemos-slow"

it "mnemos-bounded times out slow commands"
OUT=$(AGENT_CREW_MNEMOS_TIMEOUT_SECONDS=1 MNEMOS_BIN="${TMP}/mnemos-slow" \
  bash "${SCRIPT}" search agent-crew 2>&1)
rc=$?
assert_exit 124 "${rc}" "slow command timeout"

it "mnemos-bounded timeout is visible"
assert_contains "${OUT}" "mnemos-bounded: timed out after 1s" "timeout message"

it "mnemos-bounded --help exits 0"
bash "${SCRIPT}" --help >/dev/null 2>&1
rc=$?
assert_exit 0 "${rc}" "help"

it "mnemos-bounded rejects invalid poll interval"
OUT=$(AGENT_CREW_MNEMOS_POLL_INTERVAL_SECONDS=bad MNEMOS_BIN="${TMP}/mnemos-fast" \
  bash "${SCRIPT}" search agent-crew 2>&1)
rc=$?
assert_exit 2 "${rc}" "invalid poll interval"
assert_contains "${OUT}" "poll interval must be numeric"

end_report
