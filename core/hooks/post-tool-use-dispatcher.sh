#!/usr/bin/env bash
# PostToolUse dispatcher: read the host payload once, spool the exact bytes to
# disk, and fan out a small envelope to hook handlers.

set -euo pipefail

AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
PAYLOAD_ROOT="${AGENT_CREW_HOOK_PAYLOAD_DIR:-${AGENT_CREW_HOME}/state/hook-payloads}"
TMP_DIR="${PAYLOAD_ROOT}/.tmp"
mkdir -p "${TMP_DIR}"

TMP_PAYLOAD="$(mktemp "${TMP_DIR}/posttooluse.XXXXXX")"
cleanup() {
    [ -f "${TMP_PAYLOAD}" ] && rm -f "${TMP_PAYLOAD}"
}
trap cleanup EXIT

cat > "${TMP_PAYLOAD}"

ENVELOPE="$(
python3 - "${TMP_PAYLOAD}" "${PAYLOAD_ROOT}" <<'PYEOF'
import datetime as _dt
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path

tmp_payload = Path(sys.argv[1])
payload_root = Path(sys.argv[2]).expanduser()
raw = tmp_payload.read_bytes()
digest = hashlib.sha256(raw).hexdigest()
now = _dt.datetime.now(_dt.timezone.utc)
payload_dir = payload_root / now.strftime("%Y%m%d")
payload_dir.mkdir(parents=True, exist_ok=True)
payload_path = payload_dir / f"posttooluse-{digest[:16]}.json"

if payload_path.exists():
    tmp_payload.unlink(missing_ok=True)
else:
    shutil.move(str(tmp_payload), str(payload_path))

def json_string_field(name: bytes) -> str:
    match = re.search(rb'"' + re.escape(name) + rb'"\s*:\s*"((?:\\.|[^"\\])*)"', raw)
    if not match:
        return ""
    try:
        return json.loads(b'"' + match.group(1) + b'"')
    except Exception:
        return match.group(1).decode("utf-8", errors="replace")

def json_int_field(name: bytes):
    match = re.search(rb'"' + re.escape(name) + rb'"\s*:\s*(-?\d+)', raw)
    if not match:
        return None
    try:
        return int(match.group(1))
    except Exception:
        return None

def json_bool_field(name: bytes) -> bool:
    return bool(re.search(rb'"' + re.escape(name) + rb'"\s*:\s*true\b', raw))

tool_name = json_string_field(b"tool_name")
cwd = json_string_field(b"cwd") or os.getcwd()
file_path = json_string_field(b"file_path")
path = json_string_field(b"path")
new_path = json_string_field(b"new_path")
command = json_string_field(b"command")
exit_code = json_int_field(b"exit_code")
if exit_code is None:
    exit_code = json_int_field(b"returncode")
is_error = json_bool_field(b"is_error")
if exit_code is None and is_error:
    exit_code = 1

notification_raw = (
    "✻".encode("utf-8") in raw
    and "🧠".encode("utf-8") in raw
) or (b"\\u273b" in raw and (b"\\ud83e\\udde0" in raw or b"\\U0001f9e0" in raw))
command_bytes = command.encode("utf-8", errors="replace")
auto_issue_re = re.compile(
    rb"(^|[^./A-Za-z0-9_-])agent[-_\s]?crew([^/A-Za-z0-9_-]|$)"
    rb"|(^|[^A-Za-z0-9_])crew\s+(run|agent|status|repair|report|update|setup|sync|cost|smm)([^A-Za-z0-9_]|$)"
    rb"|crew:[A-Za-z-]+|[$]crew|supervisor_blocked|blocked_by|STATUS:\s*blocked|BLOCKER:",
    re.IGNORECASE,
)
korean_auto_issue_re = re.compile("에이전트\\s*크루|에이전트크루".encode("utf-8"))
if len(raw) > 1_000_000:
    auto_issue_signal = True
else:
    auto_issue_signal = bool(
        auto_issue_re.search(command_bytes)
        or auto_issue_re.search(raw)
        or korean_auto_issue_re.search(raw)
    )
route_directive_signal = (
    b"[agent-crew] STOP" in raw
    or b"[agent-crew] ROUTE" in raw
)

envelope = {
    "agent_crew_hook_envelope": 1,
    "hook_event_name": json_string_field(b"hook_event_name") or "PostToolUse",
    "payload_path": str(payload_path),
    "payload_sha256": digest,
    "payload_bytes": len(raw),
    "tool_name": tool_name,
    "cwd": cwd,
    "file_path": file_path,
    "path": path,
    "new_path": new_path,
    "command": command,
    "exit_code": exit_code,
    "is_error": is_error,
    "contains_mnemos_capture_notification": notification_raw,
    "contains_auto_issue_signal": auto_issue_signal,
    "contains_route_directive_signal": route_directive_signal,
}
print(json.dumps(envelope, ensure_ascii=False, separators=(",", ":")))
PYEOF
)"

trap - EXIT

TOOL_NAME="$(
python3 - "${ENVELOPE}" <<'PYEOF'
import json
import sys
print(json.loads(sys.argv[1]).get("tool_name") or "")
PYEOF
)"

matches_hook() {
    local matcher="$1" tool="$2" part
    [ "${matcher}" = "*" ] && return 0
    IFS='|' read -r -a parts <<< "${matcher}"
    for part in "${parts[@]}"; do
        [ "${part}" = "${tool}" ] && return 0
    done
    return 1
}

default_children() {
    cat <<EOF
Agent:bash '${AGENT_CREW_HOME}/hooks/route-directive-guard.sh'
Bash:bash '${AGENT_CREW_HOME}/hooks/tool-event-recorder.sh'
Bash:async:bash '${AGENT_CREW_HOME}/hooks/auto-issue-report.sh'
Edit|Write|MultiEdit|apply_patch:bash '${AGENT_CREW_HOME}/hooks/verify-rules.sh'
*:bash '${AGENT_CREW_HOME}/hooks/supervisor-progress-guard.sh'
*:async:bash '${AGENT_CREW_HOME}/hooks/mnemos-capture-guard.sh'
EOF
}

CHILDREN="${AGENT_CREW_POST_TOOL_USE_CHILDREN:-}"
if [ -z "${CHILDREN}" ]; then
    CHILDREN="$(default_children)"
fi

STATUS=0
while IFS= read -r child; do
    [ -n "${child}" ] || continue
    matcher="${child%%:*}"
    rest="${child#*:}"
    mode="sync"
    command="${rest}"
    case "${rest}" in
        sync:*)
            mode="sync"
            command="${rest#sync:}"
            ;;
        async:*)
            mode="async"
            command="${rest#async:}"
            ;;
    esac
    if ! matches_hook "${matcher}" "${TOOL_NAME}"; then
        continue
    fi
    if [ "${mode}" = "async" ]; then
        (
            printf '%s' "${ENVELOPE}" | bash -c "${command}" >/dev/null 2>&1 || true
        ) >/dev/null 2>&1 &
        continue
    fi
    set +e
    printf '%s' "${ENVELOPE}" | bash -c "${command}"
    rc=$?
    set -e
    if [ "${rc}" -eq 2 ]; then
        STATUS=2
    fi
done <<< "${CHILDREN}"

exit "${STATUS}"
