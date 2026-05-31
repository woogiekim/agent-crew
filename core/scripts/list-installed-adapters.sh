#!/usr/bin/env bash
# list-installed-adapters.sh — Enumerate installed adapter skills for a
# dispatcher agent.
#
# Purpose:
#   The dispatcher pattern (see `core/rules/agent-tool-dispatch.md`) loads
#   user-layer skills named `<agent>-<tool>.md` from
#   `~/.agent-crew/user/skills/`. This helper enumerates the `<tool>`
#   values for a given `<agent>` prefix.
#
#   Used by:
#     - dispatcher BLOCKED messages ("supported adapters with installed
#       skills: …")
#     - crew:status / documentation tooling that surfaces "this project
#       has issuer-plane and devops-aws configured"
#     - audit scripts that verify every declared adapter has a
#       corresponding user-layer file
#
# Usage:
#   list-installed-adapters.sh <agent-prefix>
#
#   <agent-prefix>: the dispatcher agent name (e.g. `issuer`, `backend`).
#                   The script lists every file matching
#                   `<agent-prefix>-*.md` in
#                   `${AGENT_CREW_HOME:-${HOME}/.agent-crew}/user/skills/`
#                   and prints the `<tool>` suffix (the part after the
#                   first dash, with the `.md` extension stripped).
#
# Output (stdout):
#   One adapter name per line, sorted, deduplicated. Empty when no
#   matching skills are installed.
#
# Exit codes:
#   0 — success (regardless of whether any adapters were found)
#   1 — invalid args (no prefix provided)
#
# Example:
#   $ ls ~/.agent-crew/user/skills/
#   issuer-github.md  issuer-plane.md  README.md
#   $ list-installed-adapters.sh issuer
#   github
#   plane
#
# Idempotency:
#   Pure read-only operation. Safe to call any number of times.
#
# AI-agnostic posture:
#   Pure POSIX shell + `sed`/`sort`. No host-tool calls, no MCP-specific
#   behaviour, no Python. Mirrors the contract in `core/scripts/README.md`
#   § Contract.

set -u

if [ "$#" -lt 1 ] || [ -z "${1:-}" ]; then
  printf 'usage: %s <agent-prefix>\n' "$0" >&2
  printf '       example: %s issuer\n' "$0" >&2
  exit 1
fi

AGENT_PREFIX="$1"
AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
USER_SKILLS_DIR="${AGENT_CREW_HOME}/user/skills"

if [ ! -d "${USER_SKILLS_DIR}" ]; then
  # Directory absent → no installed adapters. Not an error; print nothing.
  exit 0
fi

# Enumerate `<prefix>-<adapter>.md` and strip prefix+suffix.
# `sed -n s/.../\1/p` only prints lines that matched, eliminating non-matches.
# `sort -u` removes duplicates and orders the output for stable diffs.
ls -1 "${USER_SKILLS_DIR}" 2>/dev/null \
  | sed -n "s/^${AGENT_PREFIX}-\(.*\)\.md$/\1/p" \
  | sort -u

exit 0
