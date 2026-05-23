#!/usr/bin/env bash
# Shared cleanup command dispatcher for core/bin/crew.

set -euo pipefail

cleanup_die() {
  printf 'crew: %s\n' "$*" >&2
  exit 2
}

cleanup_require_file() {
  local path="$1" label="$2"
  [ -f "${path}" ] || cleanup_die "${label} not found at ${path}; install agent-crew first"
}

cmd_cleanup_host_bridge_helper() {
  if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
    cat <<'EOF'
usage: crew cleanup-host-bridge [--apply] [--status completed|blocked] [--min-age-seconds N]

Finds stale host_bridge_not_invoked tasks. Without --apply, prints a dry-run
list. With --apply, rewrites matched task state via crew repair so current
telemetry is not polluted by already-handled manual fallback handoffs.
EOF
    return 0
  fi

  local cleanup="${ASSET_ROOT}/scripts/cleanup-host-bridge-blockers.py"
  cleanup_require_file "${cleanup}" "host bridge cleanup script"
  python3 "${cleanup}" --state-dir "${STATE_DIR}" "$@"
}

cmd_cleanup_state_helper() {
  if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
    cat <<'EOF'
usage: crew cleanup-state [--apply] [--min-age-seconds N] [--format text|json]

Dry-run-first cleanup and archival plan for stale active markers,
supervisor-pending sentinels, and blocked/repaired task-state retention.
EOF
    return 0
  fi

  local cleanup="${ASSET_ROOT}/scripts/cleanup-task-state.py"
  cleanup_require_file "${cleanup}" "task-state cleanup script"
  python3 "${cleanup}" --state-dir "${STATE_DIR}" "$@"
}

case "${1:-}" in
  cleanup-host-bridge)
    shift
    cmd_cleanup_host_bridge_helper "$@"
    ;;
  cleanup-state)
    shift
    cmd_cleanup_state_helper "$@"
    ;;
  *)
    cleanup_die "unknown cleanup helper command: ${1:-}"
    ;;
esac
