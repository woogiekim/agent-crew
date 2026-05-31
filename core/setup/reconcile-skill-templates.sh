#!/usr/bin/env bash
# reconcile-skill-templates.sh — opt-in diff helper for adapter skill templates.
#
# Purpose:
#   The framework ships canonical seed templates under
#   `core/agents/skills/templates/`. After install/update, the user's
#   `~/.agent-crew/user/skills/<name>.md` may diverge from the template
#   (the user customized it, or the template was bumped upstream).
#
#   Per the user-layer-only policy (commit `1f89c02`), `crew:update`
#   NEVER overwrites a user-edited file. Instead, this script writes a
#   unified diff to the state directory so the user can decide whether
#   to hand-merge.
#
#   This script has two modes:
#
#   MODE A — "check" (default).
#     For each installed template, compare against the user-layer file.
#     If they differ, print a single advisory line to stdout:
#       [crew:update] templates/<name> diverged from user skill (N lines);
#                     run 'crew:update --reconcile-skills' to compare
#     Exit code is 0 in all cases; non-divergence is silent.
#
#   MODE B — "--write-diffs <output-dir>".
#     Write a unified diff for each diverged template to
#     `<output-dir>/<name>.diff`. The user reads the diff out-of-band
#     and decides whether to hand-merge. NO automatic write to the user
#     layer happens. Print a single summary line per diff written.
#
#   Both modes are read-only with respect to the user-skills layer. The
#   --write-diffs mode mutates ONLY files inside <output-dir>.
#
# Usage:
#   reconcile-skill-templates.sh \
#     [--write-diffs <output-dir>] \
#     [<source-templates-dir>] \
#     [<user-skills-dir>]
#
#   With no flag: check mode, print advisories.
#   With --write-diffs <dir>: write *.diff files to <dir> and print summary.
#
# Exit codes:
#   0 — success (advisories printed and/or diffs written)
#   1 — invalid args
#
# Idempotency:
#   Pure read-only with respect to user/skills. Re-running --write-diffs
#   overwrites previous diff files (always reflects current state).
#
# See also:
#   core/setup/seed-skill-templates.sh — install/update copy-if-absent helper
#   core/rules/agent-tool-dispatch.md   — design rationale

set -u

AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
TAG="${AGENT_CREW_RECONCILE_TAG:-crew:update}"

WRITE_DIFFS_DIR=""

# Parse flags.
while [ "$#" -gt 0 ]; do
  case "$1" in
    --write-diffs)
      if [ "$#" -lt 2 ] || [ -z "${2:-}" ]; then
        printf 'error: --write-diffs requires an output directory argument\n' >&2
        exit 1
      fi
      WRITE_DIFFS_DIR="$2"
      shift 2
      ;;
    -h|--help)
      printf 'usage: %s [--write-diffs <output-dir>] [<source-templates-dir>] [<user-skills-dir>]\n' "$0"
      exit 0
      ;;
    --) shift; break ;;
    -*)
      printf 'error: unknown flag: %s\n' "$1" >&2
      exit 1
      ;;
    *)
      break
      ;;
  esac
done

SOURCE_TEMPLATES_DIR="${1:-}"
USER_SKILLS_DIR="${2:-}"

# Resolve defaults when arguments are omitted.
if [ -z "${SOURCE_TEMPLATES_DIR}" ]; then
  if [ -d "${AGENT_CREW_HOME}/system/agents/skills/templates" ]; then
    SOURCE_TEMPLATES_DIR="${AGENT_CREW_HOME}/system/agents/skills/templates"
  elif [ -d "${AGENT_CREW_HOME}/agents/skills/templates" ]; then
    SOURCE_TEMPLATES_DIR="${AGENT_CREW_HOME}/agents/skills/templates"
  else
    SOURCE_TEMPLATES_DIR=""
  fi
fi

if [ -z "${USER_SKILLS_DIR}" ]; then
  USER_SKILLS_DIR="${AGENT_CREW_HOME}/user/skills"
fi

# No templates installed → silent no-op.
if [ -z "${SOURCE_TEMPLATES_DIR}" ] || [ ! -d "${SOURCE_TEMPLATES_DIR}" ]; then
  exit 0
fi

# No user skills directory → no possible divergence.
if [ ! -d "${USER_SKILLS_DIR}" ]; then
  exit 0
fi

# In --write-diffs mode, ensure the output directory exists.
if [ -n "${WRITE_DIFFS_DIR}" ]; then
  mkdir -p "${WRITE_DIFFS_DIR}"
fi

diverged=0
absent=0
clean=0
diffs_written=0

while IFS= read -r -d '' tpl; do
  base="$(basename "${tpl}")"

  case "${base}" in
    README.md|SKILL-TEMPLATE.md|.*)
      continue
      ;;
  esac

  user_path="${USER_SKILLS_DIR}/${base}"

  if [ ! -e "${user_path}" ]; then
    # User has not seeded this template yet — that's the seed helper's
    # job, not reconcile's. Skip silently.
    absent=$((absent + 1))
    continue
  fi

  if cmp -s "${tpl}" "${user_path}"; then
    clean=$((clean + 1))
    continue
  fi

  # Files differ.
  diverged=$((diverged + 1))

  # Count diff lines for the advisory message.
  diff_lines=$(diff -u "${tpl}" "${user_path}" 2>/dev/null \
                 | grep -cE '^[-+]' \
                 | head -1)
  # Subtract the two header lines ('--- ...' / '+++ ...') if present.
  if [ "${diff_lines}" -ge 2 ]; then
    diff_lines=$((diff_lines - 2))
  fi

  if [ -n "${WRITE_DIFFS_DIR}" ]; then
    diff_path="${WRITE_DIFFS_DIR}/${base%.md}.diff"
    diff -u "${tpl}" "${user_path}" > "${diff_path}" 2>/dev/null || true
    printf '[%s] reconcile diff written: %s\n' "${TAG}" "${diff_path}"
    diffs_written=$((diffs_written + 1))
  else
    printf '[%s] templates/%s diverged from user skill (%d lines); run '\''crew:update --reconcile-skills'\'' to compare\n' \
      "${TAG}" "${base}" "${diff_lines}"
  fi
done < <(find "${SOURCE_TEMPLATES_DIR}" -maxdepth 1 -name "*.md" -print0 2>/dev/null)

if [ -n "${WRITE_DIFFS_DIR}" ]; then
  printf '[%s] skill template reconcile: %d diff(s) written to %s\n' \
    "${TAG}" "${diffs_written}" "${WRITE_DIFFS_DIR}"
  if [ "${diffs_written}" -gt 0 ]; then
    printf '[%s] Review each .diff file and decide whether to hand-merge.\n' "${TAG}"
    printf '[%s] No automatic write to %s ever happens.\n' "${TAG}" "${USER_SKILLS_DIR}"
  fi
fi

exit 0
