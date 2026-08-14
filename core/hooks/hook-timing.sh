#!/usr/bin/env bash
# Lightweight lifecycle-hook timing breadcrumbs.

agent_crew_hook_timing_default_log() {
  local home="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"

  if [ -d "${home}/hooks" ] && [ -d "${home}/scripts" ] && [ -d "${home}/../.git" ]; then
    printf '%s\n' "${HOME}/.agent-crew/state/hook-timings.jsonl"
    return 0
  fi

  printf '%s\n' "${home}/state/hook-timings.jsonl"
}

agent_crew_hook_timing_log() {
  local event="$1" hook_name="$2" elapsed="${3:-}" log_file log_dir ts

  [ "${AGENT_CREW_HOOK_TIMING:-1}" != "0" ] || return 0

  log_file="${AGENT_CREW_HOOK_TIMING_LOG:-$(agent_crew_hook_timing_default_log)}"
  log_dir="$(dirname "${log_file}")"
  mkdir -p "${log_dir}" 2>/dev/null || return 0

  ts="$(date -u +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || printf 'unknown')"
  if [ -n "${elapsed}" ]; then
    printf '{"ts":"%s","event":"%s","hook":"%s","pid":%s,"ppid":%s,"elapsed_seconds":%s,"aoe_instance_id":"%s"}\n' \
      "${ts}" "${event}" "${hook_name}" "$$" "${PPID:-0}" "${elapsed}" "${AOE_INSTANCE_ID:-}" >> "${log_file}" 2>/dev/null || true
  else
    printf '{"ts":"%s","event":"%s","hook":"%s","pid":%s,"ppid":%s,"aoe_instance_id":"%s"}\n' \
      "${ts}" "${event}" "${hook_name}" "$$" "${PPID:-0}" "${AOE_INSTANCE_ID:-}" >> "${log_file}" 2>/dev/null || true
  fi
}

agent_crew_hook_timing_start() {
  AGENT_CREW_HOOK_TIMING_NAME="$1"
  SECONDS=0
  agent_crew_hook_timing_log "start" "${AGENT_CREW_HOOK_TIMING_NAME}"
}

agent_crew_hook_timing_finish() {
  local rc="${1:-0}"

  agent_crew_hook_timing_log "finish" "${AGENT_CREW_HOOK_TIMING_NAME:-unknown}" "${SECONDS:-0}"
  return "${rc}"
}
