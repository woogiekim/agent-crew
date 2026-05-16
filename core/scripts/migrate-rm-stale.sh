#!/usr/bin/env bash
# migrate-rm-stale.sh — Idempotent removal of stale files from an installation.
#
# Purpose:
#   Future `crew:update` migrations remove files that an earlier version of
#   agent-crew installed but a later version no longer ships. The pattern is
#   always the same: a list of candidate paths, each tested with `[ -f ]`,
#   each removed with `rm -f`, with one log line per actual removal and a
#   single summary line at the end. This script extracts that pattern so
#   future migrations in `core/commands/update.md` can call it instead of
#   re-implementing the loop.
#
# Usage:
#   migrate-rm-stale.sh LABEL PATH [PATH ...]
#
#   LABEL: short tag for the log lines (e.g. "Phase 3.1 scribe").
#   PATH:  one or more absolute paths to candidate stale files. Missing
#          paths are silently skipped.
#
# Exit codes:
#   0 — success (regardless of how many files were removed)
#   1 — invalid args (no label or no paths)
#
# Examples:
#   migrate-rm-stale.sh "Phase 3.1 scribe" \
#     "${AGENT_CREW_HOME}/system/agents/scribe.md" \
#     "${CLAUDE_DIR}/agents/scribe.md"
#
# Idempotency:
#   Running the script multiple times against the same path set is safe.
#   On the second run all paths are already missing, the script reports
#   "no stale files found", and exits 0. This is the expected steady-state
#   after a migration has run once.
#
# Schema cross-ref:
#   See `core/commands/update.md` § Migration Conventions for the canonical
#   pattern this script implements.

set -euo pipefail

if [ "$#" -lt 2 ]; then
  printf 'usage: %s LABEL PATH [PATH ...]\n' "$0" >&2
  exit 1
fi

LABEL="$1"
shift

removed=0
for f in "$@"; do
  if [ -f "${f}" ]; then
    rm -f "${f}"
    printf '[crew:update] Removed stale file (%s): %s\n' "${LABEL}" "${f}"
    removed=$((removed + 1))
  fi
done

if [ "${removed}" -eq 0 ]; then
  printf '[crew:update] %s: no stale files found (already migrated).\n' "${LABEL}"
else
  printf '[crew:update] %s: removed %d stale file(s).\n' "${LABEL}" "${removed}"
fi
