#!/usr/bin/env bash
# seed-skill-templates.sh — Channel B template seeding for adapter skills.
#
# Purpose:
#   The dispatcher pattern (`core/rules/agent-tool-dispatch.md`) loads
#   user-layer skills named `<agent>-<tool>.md` from
#   `~/.agent-crew/user/skills/`. The framework ships canonical seed
#   templates under `core/agents/skills/templates/` so vendor knowledge
#   (Plane quirks, GitHub rate-limit headers, …) can ride with the
#   framework without violating the user-layer-only policy from
#   commit `1f89c02`.
#
#   This script copies each template into the user-skills layer using
#   **copy-if-absent** semantics. It NEVER overwrites a user-edited file.
#   When the user-layer file already exists, the template is skipped
#   with an informational log line — even if the bytes differ.
#
#   The reconcile flow (`reconcile-skill-templates.sh`) is the opt-in
#   counterpart: it writes a unified diff to the state dir so the user
#   can decide whether to hand-merge.
#
# Usage:
#   seed-skill-templates.sh [SOURCE_TEMPLATES_DIR] [USER_SKILLS_DIR]
#
#   Both arguments are optional. Defaults:
#     SOURCE_TEMPLATES_DIR = ${AGENT_CREW_HOME}/system/agents/skills/templates
#                            (falls back to ${AGENT_CREW_HOME}/agents/skills/templates
#                             if the system path does not exist)
#     USER_SKILLS_DIR      = ${AGENT_CREW_HOME}/user/skills
#
#   When invoked from `crew:setup` / `crew:update`, callers pass the
#   resolved paths explicitly so the script stays decoupled from the
#   AGENT_CREW_HOME global. When invoked manually (developer flow), the
#   defaults Just Work.
#
# Exit codes:
#   0 — success (regardless of how many templates were seeded vs skipped)
#   1 — invalid args (only when caller passed a non-existent SOURCE dir
#       and explicitly insisted on it)
#
# Output (stdout):
#   One log line per template:
#     [crew:setup] seeded user skill: <name> (from template)
#     [crew:setup] user skill already present, template not applied: <name>
#   Summary line at the end:
#     [crew:setup] skill templates: seeded=N skipped=M total=N+M
#
# Idempotency:
#   Re-running is safe. Every already-seeded file is skipped on the
#   second run; total churn on stable trees is zero.
#
# Policy:
#   - NEVER overwrites a user-layer file. Period.
#   - NEVER auto-merges template changes into the user layer.
#   - The runtime contract (dispatcher loads `user/skills/<name>.md`) is
#     unchanged.
#
# See also:
#   core/setup/reconcile-skill-templates.sh — opt-in diff helper
#   core/rules/agent-tool-dispatch.md       — design rationale

set -u

AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"

SOURCE_TEMPLATES_DIR="${1:-}"
USER_SKILLS_DIR="${2:-}"

# Resolve defaults when arguments are omitted.
if [ -z "${SOURCE_TEMPLATES_DIR}" ]; then
  if [ -d "${AGENT_CREW_HOME}/system/agents/skills/templates" ]; then
    SOURCE_TEMPLATES_DIR="${AGENT_CREW_HOME}/system/agents/skills/templates"
  elif [ -d "${AGENT_CREW_HOME}/agents/skills/templates" ]; then
    SOURCE_TEMPLATES_DIR="${AGENT_CREW_HOME}/agents/skills/templates"
  else
    # No templates installed — silent no-op. Not an error: the framework
    # may ship zero seed templates initially.
    SOURCE_TEMPLATES_DIR=""
  fi
fi

if [ -z "${USER_SKILLS_DIR}" ]; then
  USER_SKILLS_DIR="${AGENT_CREW_HOME}/user/skills"
fi

# Tag for log lines — caller may override via env to distinguish setup/update.
TAG="${AGENT_CREW_SEED_TAG:-crew:setup}"

# When SOURCE_TEMPLATES_DIR is empty (no templates installed), exit silently 0.
if [ -z "${SOURCE_TEMPLATES_DIR}" ] || [ ! -d "${SOURCE_TEMPLATES_DIR}" ]; then
  printf '[%s] skill templates: source directory absent — nothing to seed.\n' \
    "${TAG}"
  exit 0
fi

mkdir -p "${USER_SKILLS_DIR}"

seeded=0
skipped=0

# Iterate every *.md file in the templates directory (flat, non-recursive).
# README.md inside the templates dir is treated as documentation, not as a
# seedable skill — it is filtered out so users don't end up with a
# README.md skill in their user-skills layer.
while IFS= read -r -d '' tpl; do
  base="$(basename "${tpl}")"

  case "${base}" in
    README.md|SKILL-TEMPLATE.md|.*)
      # Documentation / hidden files — skip silently.
      continue
      ;;
  esac

  user_path="${USER_SKILLS_DIR}/${base}"

  if [ -e "${user_path}" ]; then
    printf '[%s] user skill already present, template not applied: %s\n' \
      "${TAG}" "${base}"
    skipped=$((skipped + 1))
  else
    cp "${tpl}" "${user_path}"
    printf '[%s] seeded user skill: %s (from template)\n' \
      "${TAG}" "${base}"
    seeded=$((seeded + 1))
  fi
done < <(find "${SOURCE_TEMPLATES_DIR}" -maxdepth 1 -name "*.md" -print0 2>/dev/null)

total=$((seeded + skipped))
printf '[%s] skill templates: seeded=%d skipped=%d total=%d\n' \
  "${TAG}" "${seeded}" "${skipped}" "${total}"

exit 0
