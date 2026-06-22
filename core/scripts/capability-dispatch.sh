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
#   4. On match success or zero-match, append a `{skill_path, loaded_by}`
#      citation entry per matched skill to
#      `${TASK_DIR}/context/skill-use.json` per the rule-mandated form
#      in `core/rules/agent-tool-dispatch.md` state 3.
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
SKILL_USE_FILE="${TASK_DIR}/context/skill-use.json"
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
  printf '{"agent":"%s","matched":[],"fallback":true,"fallback_policy":"generic-%s-skills","reason":"%s"}\n' \
    "${AGENT_NAME}" "${AGENT_NAME}" "${reason}"
}

# Append `{skill_path, loaded_by}` citation entries to
# `${TASK_DIR}/context/skill-use.json` for each matched skill in the
# dispatch report. Per `core/rules/agent-tool-dispatch.md` state 3.
cite_matched_skills() {
  local report="$1"
  [ -f "${report}" ] || return 0
  python3 - "${report}" "${SKILL_USE_FILE}" "${AGENT_NAME}" <<'PY' 2>/dev/null || true
import json
import os
import sys
from pathlib import Path

report_path = Path(sys.argv[1])
skill_use_path = Path(sys.argv[2])
agent_name = sys.argv[3]

try:
    report = json.loads(report_path.read_text(encoding="utf-8"))
except (OSError, ValueError):
    sys.exit(0)

matched = report.get("matched") or []
if not isinstance(matched, list) or not matched:
    sys.exit(0)

existing = []
if skill_use_path.is_file():
    try:
        loaded = json.loads(skill_use_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        loaded = []
    if isinstance(loaded, list):
        existing = loaded
    elif isinstance(loaded, dict) and isinstance(loaded.get("entries"), list):
        existing = loaded["entries"]

seen = {
    (entry.get("skill_path"), entry.get("loaded_by"))
    for entry in existing
    if isinstance(entry, dict)
}

added = False
for item in matched:
    if not isinstance(item, dict):
        continue
    skill_path = item.get("path") or ""
    if not skill_path:
        continue
    key = (skill_path, agent_name)
    if key in seen:
        continue
    existing.append({"skill_path": skill_path, "loaded_by": agent_name})
    seen.add(key)
    added = True

if not added and skill_use_path.is_file():
    sys.exit(0)

skill_use_path.parent.mkdir(parents=True, exist_ok=True)
tmp = skill_use_path.with_suffix(skill_use_path.suffix + ".tmp")
tmp.write_text(json.dumps(existing, indent=2, sort_keys=True) + "\n", encoding="utf-8")
os.replace(tmp, skill_use_path)
PY
}

_DISPATCH_TMP="${DISPATCH_REPORT}.tmp"

if [ -f "${DISPATCH}" ]; then
  if python3 "${DISPATCH}" \
      --agent "${AGENT_NAME}" \
      --project-root "${PROJECT_ROOT:-}" \
      --task "${TASK:-}" \
      --format json > "${_DISPATCH_TMP}" 2>"${DISPATCH_LOG}"; then
    if mv "${_DISPATCH_TMP}" "${DISPATCH_REPORT}" 2>/dev/null; then
      cite_matched_skills "${DISPATCH_REPORT}"
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
