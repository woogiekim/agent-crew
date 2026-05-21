#!/usr/bin/env bash
# Tests for core/bin/memory wrapper behavior.

set -u

# shellcheck source=./_lib.bash
source "$(dirname "$0")/_lib.bash"
set +e

MEMORY="${REPO_ROOT}/core/bin/memory"
CODEX_SKILL="${REPO_ROOT}/adapters/codex/skill/agent-crew/SKILL.md"

it "crew CLI exists next to memory wrapper"
assert_file_exists "${REPO_ROOT}/core/bin/crew"

it "Codex skill memory contract uses the bounded memory wrapper"
SKILL_TEXT=$(cat "${CODEX_SKILL}")
assert_contains "${SKILL_TEXT}" '.agent-crew/bin/memory'
assert_contains "${SKILL_TEXT}" 'AGENT_CREW_MNEMOS_TIMEOUT_SECONDS'

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

cat > "${TMP}/mnemos" <<'SH'
#!/usr/bin/env bash
sleep 5
echo "late mnemos output"
exit 0
SH
chmod +x "${TMP}/mnemos"

it "memory search uses bounded mnemos timeout"
OUTPUT=$(AGENT_CREW_MEMORY_FAST_SEARCH=0 AGENT_CREW_MNEMOS_TIMEOUT_SECONDS=1 MNEMOS_BIN="${TMP}/mnemos" bash "${MEMORY}" search slow 2>&1)
rc=$?
assert_exit 124 "${rc}" "search timeout"
assert_contains "${OUTPUT}" "mnemos-bounded: timed out after 1s"

FAST_HOME=$(make_tmp)
mkdir -p "${FAST_HOME}/.mnemos/.agent/state"
python3 - "${FAST_HOME}/.mnemos/.agent/state/fts.db" <<'PY'
import json
import sqlite3
import sys

conn = sqlite3.connect(sys.argv[1])
conn.execute(
    """
    CREATE VIRTUAL TABLE items_fts
    USING fts5(item_id UNINDEXED, content, metadata)
    """
)
conn.execute(
    "INSERT INTO items_fts (item_id, content, metadata) VALUES (?, ?, ?)",
    (
        "fast-memory-1",
        "agent crew fast memory search result",
        json.dumps({"layer": "session", "tags": []}),
    ),
)
conn.execute(
    "INSERT INTO items_fts (item_id, content, metadata) VALUES (?, ?, ?)",
    (
        "fast-memory-2",
        "commercialization evaluation found Mnemos latency context",
        json.dumps({"layer": "session", "tags": []}),
    ),
)
conn.commit()
PY
cat > "${TMP}/mnemos" <<'SH'
#!/usr/bin/env bash
echo "slow backend invoked"
exit 99
SH
chmod +x "${TMP}/mnemos"

it "memory search uses read-only FTS fast path before mnemos backend"
OUTPUT=$(HOME="${FAST_HOME}" MNEMOS_REPO_ROOT="${FAST_HOME}/.mnemos" MNEMOS_BIN="${TMP}/mnemos" bash "${MEMORY}" search "agent crew fast" --limit 5 2>&1)
rc=$?
assert_exit 0 "${rc}" "fast FTS search"
assert_contains "${OUTPUT}" "fast-memory-1"
assert_not_contains "${OUTPUT}" "slow backend invoked"

it "memory search relaxes over-specific FTS queries when strict matching is empty"
OUTPUT=$(HOME="${FAST_HOME}" MNEMOS_REPO_ROOT="${FAST_HOME}/.mnemos" MNEMOS_BIN="${TMP}/mnemos" bash "${MEMORY}" search "requirements commercialization production readiness Mnemos latency answer quality" --limit 5 2>&1)
rc=$?
assert_exit 0 "${rc}" "relaxed FTS search"
assert_contains "${OUTPUT}" "fast-memory-2"
assert_not_contains "${OUTPUT}" "slow backend invoked"

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

end_report
