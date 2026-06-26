#!/usr/bin/env bash
# capability-dispatch.sh — shared capability-dispatch helper for all 13
# dispatch-enabled agents (#186, finding [8]).
#
# Usage:
#   bash core/scripts/capability-dispatch.sh <agent_name>
#
# Behavior:
#   1. Locate the Python dispatcher (`review-profile-dispatch.py`) under
#      the installed system path, with a source-checkout fallback.
#   2. Run it with `--agent <name>` and write the JSON result atomically
#      into `${TASK_DIR}/context/capability-skills-<agent>.json`.
#   3. On script-missing, script-failed, or mv-failed conditions, emit
#      the canonical degraded JSON payload (built via the dispatcher's
#      `--emit-fallback <reason>` mode when available; literal fallback
#      only when the dispatcher itself is missing) plus the matching
#      `[crew] DEGRADED | capability-dispatch=<reason> agent=<name>` line.
#   4. On match success or zero-match, preserve only the framework-computed
#      resolver state in `${TASK_DIR}/context/capability-skills-<agent>.json`.
#      Do not synthesize `skill-use.json` proof artifacts from dispatch alone.
#
# Required env:
#   TASK_DIR       — task directory; must exist
#   PROJECT_ROOT   — project root used as detection context
#   TASK           — optional task text passed as detection input
#   AGENT_CREW_HOME — optional; defaults to ${HOME}/.agent-crew
#
# Exit codes:
#   0 — normal success OR a documented degraded fallback was emitted
#   2 — invalid invocation (missing agent argument or TASK_DIR)
#
# POSIX bash; no Claude-only / host-specific tokens.

set -u

if [ "$#" -lt 1 ] || [ -z "${1:-}" ]; then
  printf 'usage: capability-dispatch.sh <agent_name>\n' >&2
  exit 2
fi

AGENT_NAME="$1"
: "${TASK_DIR:?TASK_DIR is required}"

mkdir -p "${TASK_DIR}/context" 2>/dev/null || true

DISPATCH_REPORT="${TASK_DIR}/context/capability-skills-${AGENT_NAME}.json"
DISPATCH_LOG="${TASK_DIR}/context/capability-dispatch-${AGENT_NAME}.log"

# Locate the dispatcher: prefer the installed system path, then a source
# checkout fallback. The same precedence the agent .md files used to use.
DISPATCH="${AGENT_CREW_HOME:-${HOME}/.agent-crew}/system/scripts/review-profile-dispatch.py"
if [ ! -f "${DISPATCH}" ] && [ -n "${PROJECT_ROOT:-}" ]; then
  DISPATCH="${PROJECT_ROOT}/core/scripts/review-profile-dispatch.py"
fi

# Emit the canonical degraded JSON payload for a given <reason>.
# Prefer the dispatcher's `--emit-fallback` mode (finding [9]) so the
# fallback string is computed in exactly one place. If the dispatcher
# itself is missing or refuses --emit-fallback, fall back to a literal
# JSON that follows the same shape — but never carry a hand-typed
# `generic-<agent>-skills` token across multiple .md files.
emit_fallback_json() {
  local reason="$1"
  local emit_output=""
  if [ -f "${DISPATCH}" ]; then
    if emit_output=$(python3 "${DISPATCH}" --agent "${AGENT_NAME}" \
        --emit-fallback "${reason}" 2>/dev/null); then
      printf '%s\n' "${emit_output}"
      return 0
    fi
  fi
  # Last-resort literal — only reached if the dispatcher is missing AND
  # we have no other way to compute the policy string. We deliberately do
  # NOT hand-type `generic-<agent>-skills` here as a value carried per
  # agent; the literal is constructed at runtime from the agent name.
  printf '%s%s%s%s%s%s%s%s%s%s%s%s\n' \
    '{"agent":"'"${AGENT_NAME}"'","matched":[],' \
    '"duplicate_resolved":[],"unindexed_user_skills":[],' \
    '"fallback":true,"fallback_policy":"generic-'"${AGENT_NAME}"'-skills",' \
    '"reason":"'"${reason}"'","decision_context":{' \
    '"source":"framework_computed","artifact_required":false,' \
    '"coverage":{"skill_discovery":0,"skill_resolution":0},' \
    '"known_gaps":[{"id":"capability_dispatch:'"${reason}"'",' \
    '"type":"capability_dispatch_degraded","severity":"medium",' \
    '"agent":"'"${AGENT_NAME}"'","reason":"'"${reason}"'",' \
    '"impact":"capability skills were not resolved; agent should continue with declared base skills",' \
    '"recommended_action":"inspect dispatcher availability only if this affects task quality",' \
    '"deferrable":true}]}}'
}

_DISPATCH_TMP="${DISPATCH_REPORT}.tmp"

if [ -f "${DISPATCH}" ]; then
  if python3 "${DISPATCH}" \
      --agent "${AGENT_NAME}" \
      --project-root "${PROJECT_ROOT:-}" \
      --task "${TASK:-}" \
      --format json > "${_DISPATCH_TMP}" 2>"${DISPATCH_LOG}"; then
    if mv "${_DISPATCH_TMP}" "${DISPATCH_REPORT}" 2>/dev/null; then
      :
    else
      rm -f "${_DISPATCH_TMP}"
      emit_fallback_json "mv_failed" > "${DISPATCH_REPORT}"
      printf '[crew] DEGRADED | capability-dispatch=mv_failed agent=%s\n' "${AGENT_NAME}"
    fi
  else
    rm -f "${_DISPATCH_TMP}"
    emit_fallback_json "script_failed" > "${DISPATCH_REPORT}"
    printf '[crew] DEGRADED | capability-dispatch=script_failed agent=%s\n' "${AGENT_NAME}"
  fi
else
  emit_fallback_json "script_missing" > "${DISPATCH_REPORT}"
  printf '[crew] DEGRADED | capability-dispatch=script_missing agent=%s\n' "${AGENT_NAME}"
fi

exit 0
