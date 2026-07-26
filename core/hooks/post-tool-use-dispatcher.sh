#!/usr/bin/env bash
# PostToolUse dispatcher: read the host payload once, spool the exact bytes to
# disk, handle latency-critical checks inline, and detach heavyweight fan-out.

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

SCRIPT="${AGENT_CREW_HOME}/scripts/post-tool-use-dispatcher.py"
if [ ! -f "${SCRIPT}" ]; then
    SCRIPT="$(cd "$(dirname "$0")/../scripts" 2>/dev/null && pwd -P)/post-tool-use-dispatcher.py"
fi

set +e
ENVELOPE="$(python3 -S "${SCRIPT}" "${TMP_PAYLOAD}" "${PAYLOAD_ROOT}" "${AGENT_CREW_HOME}")"
PY_STATUS=$?
set -e
trap - EXIT

if [ "${PY_STATUS}" -eq 2 ]; then
    exit 2
fi
if [ "${PY_STATUS}" -ne 0 ]; then
    exit 0
fi

TOOL_NAME="$(printf '%s' "${ENVELOPE}" | sed -nE 's/.*"tool_name":"([^"]*)".*/\1/p')"

envelope_bool() {
    local name="$1"
    case "${ENVELOPE}" in
        *"\"${name}\":true"*|*"\"${name}\": true"*)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

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
    # route-directive-guard.sh fan-out matcher: aliases the Codex
    # subagent tool_name `multi_agent_v1wait_agent` alongside `Agent`
    # (Issue #125 follow-up). `multi_agent_v1wait_agent` is the only
    # Codex tool_name whose tool_response schema is designed to carry a
    # completed-agent-response body (status keyed by target); `spawn_agent`
    # and `multi_agent_v1send_input` are deliberately NOT aliased here —
    # direct inspection of spooled PostToolUse payloads confirmed both are
    # ack-only (agent_id/nickname, submission_id) and never carry a
    # completed response, so aliasing them would only produce false-positive
    # blocks on the kickoff/interrupt ack.
    cat <<EOF
Agent|multi_agent_v1wait_agent:bash '${AGENT_CREW_HOME}/hooks/route-directive-guard.sh'
Bash:async:bash '${AGENT_CREW_HOME}/hooks/auto-issue-report.sh'
Edit|Write|MultiEdit|apply_patch:bash '${AGENT_CREW_HOME}/hooks/verify-rules.sh'
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
        case "${command}" in
            *mnemos-capture-guard.sh*)
                envelope_bool "contains_mnemos_capture_notification" || continue
                ;;
            *auto-issue-report.sh*)
                envelope_bool "contains_auto_issue_signal" || continue
                ;;
        esac

        ASYNC_DIR="${PAYLOAD_ROOT}/.async"
        mkdir -p "${ASYNC_DIR}" 2>/dev/null || true
        ASYNC_ENVELOPE="$(mktemp "${ASYNC_DIR}/posttooluse-envelope.XXXXXX" 2>/dev/null || true)"
        if [ -n "${ASYNC_ENVELOPE}" ]; then
            printf '%s' "${ENVELOPE}" > "${ASYNC_ENVELOPE}" 2>/dev/null || true
            nohup bash -c 'cat "$1" | bash -c "$2"; rm -f "$1"' _ "${ASYNC_ENVELOPE}" "${command}" >/dev/null 2>&1 &
        fi
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
