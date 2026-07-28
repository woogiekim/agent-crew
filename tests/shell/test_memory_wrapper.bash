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

it "memory search uses bounded mnemos timeout"
OUTPUT=$(AGENT_CREW_MEMORY_FAST_SEARCH=0 AGENT_CREW_MNEMOS_TIMEOUT_SECONDS=1 MNEMOS_BIN="${TMP}/mnemos" bash "${MEMORY}" search slow 2>&1)
rc=$?
assert_exit 124 "${rc}" "search timeout"
assert_contains "${OUTPUT}" "mnemos-bounded: timed out after 1s"

TMP=$(make_tmp)
cat > "${TMP}/mnemos" <<'SH'
#!/usr/bin/env bash
if [ "${1:-}" = "capabilities" ] && [ "${2:-}" = "--json" ]; then
  cat <<'JSON'
{"commands":{"search":{"fast":true,"json":true}}}
JSON
  exit 0
fi
if [ "${1:-}" = "search" ] && [ "${2:-}" = "--fast" ] && [ "${3:-}" = "--json" ]; then
  cat <<'JSON'
{"results":[{"id":"stable-memory-1","content":"stable provider search result","score":0.91}]}
JSON
  exit 0
fi
echo "unexpected mnemos $*"
exit 9
SH
chmod +x "${TMP}/mnemos"

NO_FTS_HOME=$(make_tmp)
it "memory search uses stable mnemos fast JSON API without direct FTS DB access"
OUTPUT=$(HOME="${NO_FTS_HOME}" MNEMOS_REPO_ROOT="${NO_FTS_HOME}/.mnemos" MNEMOS_BIN="${TMP}/mnemos" bash "${MEMORY}" search "stable provider" --limit 5 2>&1)
rc=$?
assert_exit 0 "${rc}" "stable fast search"
assert_contains "${OUTPUT}" "stable-memory-1"

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
        "legacy-memory-should-not-appear",
        "stable provider legacy fallback result",
        json.dumps({"layer": "session", "tags": []}),
    ),
)
conn.commit()
PY

it "memory search prefers stable mnemos API over deprecated direct FTS fallback"
OUTPUT=$(HOME="${FAST_HOME}" MNEMOS_REPO_ROOT="${FAST_HOME}/.mnemos" MNEMOS_BIN="${TMP}/mnemos" bash "${MEMORY}" search "stable provider" --limit 5 2>&1)
rc=$?
assert_exit 0 "${rc}" "stable API preferred"
assert_contains "${OUTPUT}" "stable-memory-1"
assert_not_contains "${OUTPUT}" "legacy-memory-should-not-appear"

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
conn.execute(
    "INSERT INTO items_fts (item_id, content, metadata) VALUES (?, ?, ?)",
    (
        "req-commercialization-eval-test",
        "Requirements collected for commercialization evaluation telemetry blockers Mnemos latency answer quality",
        json.dumps({"layer": "ephemeral", "tags": ["requirements"]}),
    ),
)
conn.execute(
    "INSERT INTO items_fts (item_id, content, metadata) VALUES (?, ?, ?)",
    (
        "commercialization-e2e-99-review-20260101",
        "Commercialization E2E round review telemetry blockers Mnemos latency answer quality summary context",
        json.dumps({"layer": "session", "tags": []}),
    ),
)
conn.commit()
PY
TMP=$(make_tmp)
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
assert_contains "${OUTPUT}" "score="
assert_not_contains "${OUTPUT}" "slow backend invoked"

it "memory search relaxes over-specific FTS queries when strict matching is empty"
OUTPUT=$(HOME="${FAST_HOME}" MNEMOS_REPO_ROOT="${FAST_HOME}/.mnemos" MNEMOS_BIN="${TMP}/mnemos" bash "${MEMORY}" search "requirements commercialization production readiness Mnemos latency answer quality" --limit 5 2>&1)
rc=$?
assert_exit 0 "${rc}" "relaxed FTS search"
assert_contains "${OUTPUT}" "fast-memory-2"
assert_not_contains "${OUTPUT}" "slow backend invoked"

it "memory search ranks requirements evidence before round summary context"
OUTPUT=$(HOME="${FAST_HOME}" MNEMOS_REPO_ROOT="${FAST_HOME}/.mnemos" MNEMOS_BIN="${TMP}/mnemos" bash "${MEMORY}" search "commercialization evaluation telemetry blockers Mnemos latency answer quality" --limit 1 2>&1)
rc=$?
assert_exit 0 "${rc}" "requirements evidence ranking"
assert_contains "${OUTPUT}" "req-commercialization-eval-test"
assert_not_contains "${OUTPUT}" "commercialization-e2e-99-review-20260101"

GC_HOME=$(make_tmp)
mkdir -p "${GC_HOME}/.mnemos/.agent/state"
python3 - "${GC_HOME}/.mnemos/.agent/state/fts.db" <<'PY'
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

conn = sqlite3.connect(sys.argv[1])
conn.execute(
    """
    CREATE VIRTUAL TABLE items_fts
    USING fts5(item_id UNINDEXED, content, metadata)
    """
)
now = datetime.now(timezone.utc)
recent = (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
old = (now - timedelta(days=400)).strftime("%Y-%m-%dT%H:%M:%SZ")

rows = [
    (
        "duplicate-memory-canonical",
        "valuable duplicate content for memory gc retention",
        {"layer": "session", "created_at": recent},
    ),
    (
        "duplicate-memory-copy",
        "valuable duplicate content for memory gc retention",
        {"layer": "ephemeral", "created_at": old},
    ),
    (
        "stale-probe-memory",
        "probe",
        {"layer": "ephemeral", "created_at": old},
    ),
]
for item_id, content, metadata in rows:
    conn.execute(
        "INSERT INTO items_fts (item_id, content, metadata) VALUES (?, ?, ?)",
        (item_id, content, json.dumps(metadata)),
    )
conn.commit()
PY

it "memory gc dry-run reports duplicate and low-value candidates"
OUTPUT=$(HOME="${GC_HOME}" bash "${MEMORY}" gc --format json --mnemos-root "${GC_HOME}/.mnemos" 2>&1)
rc=$?
assert_exit 0 "${rc}" "memory gc dry run"
assert_contains "${OUTPUT}" "duplicate-memory-copy"
assert_contains "${OUTPUT}" "stale-probe-memory"

it "memory gc apply writes archive and evicted id list"
OUTPUT=$(HOME="${GC_HOME}" bash "${MEMORY}" gc --format json --apply --mnemos-root "${GC_HOME}/.mnemos" --archive-path "${GC_HOME}/archive.jsonl" --evicted-path "${GC_HOME}/evicted-ids.txt" 2>&1)
rc=$?
assert_exit 0 "${rc}" "memory gc apply"
assert_file_exists "${GC_HOME}/archive.jsonl"
assert_file_exists "${GC_HOME}/evicted-ids.txt"
EVICTED_TEXT=$(cat "${GC_HOME}/evicted-ids.txt")
assert_contains "${EVICTED_TEXT}" "duplicate-memory-copy"

it "memory search omits IDs evicted by memory gc"
OUTPUT=$(HOME="${GC_HOME}" MNEMOS_REPO_ROOT="${GC_HOME}/.mnemos" AGENT_CREW_MEMORY_GC_EVICTED="${GC_HOME}/evicted-ids.txt" MNEMOS_BIN="${TMP}/mnemos" bash "${MEMORY}" search "valuable duplicate content memory gc retention" --limit 5 2>&1)
rc=$?
assert_exit 0 "${rc}" "memory search after gc"
assert_contains "${OUTPUT}" "duplicate-memory-canonical"
assert_not_contains "${OUTPUT}" "duplicate-memory-copy"

it "memory search reports unsupported score support for non-FTS backend"
TMP=$(make_tmp)
cat > "${TMP}/mnemos" <<'SH'
#!/usr/bin/env bash
printf 'mnemos %s\n' "$*"
exit 0
SH
chmod +x "${TMP}/mnemos"
OUTPUT=$(AGENT_CREW_MEMORY_FAST_SEARCH=0 AGENT_CREW_MEMORY_REPORT_SCORE_SUPPORT=1 MNEMOS_BIN="${TMP}/mnemos" bash "${MEMORY}" search "probe" 2>&1)
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
