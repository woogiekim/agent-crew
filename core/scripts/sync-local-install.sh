#!/usr/bin/env bash
# sync-local-install.sh - refresh installed agent-crew assets from a local checkout.
#
# This is the deterministic local-source counterpart to crew:update's remote
# fresh-clone flow. Use it after making local changes that should immediately
# affect the installed ~/.agent-crew, Claude, Codex, and project-local adapter
# paths without waiting for those changes to exist on origin/main.

set -euo pipefail

usage() {
  cat <<'EOF'
usage: sync-local-install.sh [SOURCE_ROOT] [PROJECT_ROOT]

Refresh installed agent-crew assets from a local source checkout.

Arguments:
  SOURCE_ROOT   agent-crew source checkout; defaults to current git root
  PROJECT_ROOT  project to refresh host adapter files for; defaults to SOURCE_ROOT

Environment:
  AGENT_CREW_HOME  install root; defaults to ~/.agent-crew
  CLAUDE_DIR       Claude config root; defaults to ~/.claude
  CODEX_HOME       Codex config root; defaults to ~/.codex

EOF
}

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  usage
  exit 0
fi

SOURCE_ROOT="${1:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
PROJECT_ROOT="${2:-${SOURCE_ROOT}}"
AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
CLAUDE_DIR="${CLAUDE_DIR:-${HOME}/.claude}"

SOURCE_ROOT="$(cd "${SOURCE_ROOT}" && pwd)"
PROJECT_ROOT="$(cd "${PROJECT_ROOT}" && pwd)"
PATH_CREW_CLI_MANAGED=0
PROJECT_NAME="$(basename "${PROJECT_ROOT}")"
UPDATE_FINGERPRINT="${AGENT_CREW_HOME}/state/${PROJECT_NAME}/update-fingerprint.json"
UPDATE_TOTAL_START="${SECONDS}"
UPDATE_PHASE_START="${SECONDS}"

update_registry_script() {
  local candidate
  for candidate in \
    "${SOURCE_ROOT}/core/scripts/update-project-registry.py" \
    "${AGENT_CREW_HOME}/system/scripts/update-project-registry.py" \
    "${AGENT_CREW_HOME}/scripts/update-project-registry.py"; do
    [ -f "${candidate}" ] || continue
    printf '%s\n' "${candidate}"
    return 0
  done
  return 1
}

record_global_update_scope() {
  local registry
  registry="$(update_registry_script 2>/dev/null || true)"
  [ -n "${registry}" ] || return 0
  python3 "${registry}" \
    --agent-crew-home "${AGENT_CREW_HOME}" \
    mark-global \
    --source-root "${SOURCE_ROOT}" \
    --mode "${AGENT_CREW_MODE:-update}" || true
}

record_project_update_scope() {
  local registry
  registry="$(update_registry_script 2>/dev/null || true)"
  [ -n "${registry}" ] || return 0
  python3 "${registry}" \
    --agent-crew-home "${AGENT_CREW_HOME}" \
    mark-project \
    --source-root "${SOURCE_ROOT}" \
    --project-root "${PROJECT_ROOT}" || true
  printf 'update_scope: default_project_scope=current-only\n'
  printf 'update_scope: all_projects_hint=crew update --all-projects\n'
}

print_update_phase() {
  local name="$1"
  local now="${SECONDS}"
  local elapsed_ms=$(( (now - UPDATE_PHASE_START) * 1000 ))
  printf 'update_phase: %s=%sms\n' "${name}" "${elapsed_ms}"
  UPDATE_PHASE_START="${now}"
}

print_update_total() {
  local now="${SECONDS}"
  local elapsed_ms=$(( (now - UPDATE_TOTAL_START) * 1000 ))
  printf 'update_phase: total=%sms\n' "${elapsed_ms}"
}

write_update_integrity_manifest() {
  local integrity_dir="${AGENT_CREW_HOME}/state/${PROJECT_NAME}/integrity"

  [ "${AGENT_CREW_WRITE_INSTALL_MANIFEST:-1}" = "1" ] || return 0
  [ -f "${AGENT_CREW_HOME}/system/scripts/generate-release-checksums.py" ] || return 0

  mkdir -p "${integrity_dir}"
  python3 "${AGENT_CREW_HOME}/system/scripts/generate-release-checksums.py" \
    --project-root "${SOURCE_ROOT}" \
    --output "${integrity_dir}/update-integrity.json" \
    --sha256sums "${integrity_dir}/SHA256SUMS" \
    install.sh \
    core/bin/crew \
    core/commands/update.md \
    core/scripts/sync-local-install.sh >/dev/null
  printf 'sync-local-install: wrote update integrity manifest at %s\n' \
    "${integrity_dir}/update-integrity.json"
}

if [ ! -d "${SOURCE_ROOT}/core" ] || [ ! -d "${SOURCE_ROOT}/adapters" ]; then
  printf 'sync-local-install: SOURCE_ROOT is not an agent-crew checkout: %s\n' "${SOURCE_ROOT}" >&2
  exit 2
fi

path_crew_cli_is_managed() {
  local dest="${AGENT_CREW_PATH_BIN:-${HOME}/.local/bin}/crew"
  [ -f "${dest}" ] || return 1
  grep -q "experimental Codex launcher for agent-crew\\|deterministic shell entrypoint for agent-crew" "${dest}" 2>/dev/null
}

PRESERVATION_MANIFEST=""
if [ -f "${SOURCE_ROOT}/core/scripts/update-preservation-manifest.py" ]; then
  PRESERVATION_MANIFEST="$(python3 "${SOURCE_ROOT}/core/scripts/update-preservation-manifest.py" begin \
    --agent-crew-home "${AGENT_CREW_HOME}" \
    --project-root "${PROJECT_ROOT}")"
fi

if [ "${AGENT_CREW_DISABLE_FAST_NOOP_UPDATE:-0}" != "1" ] \
  && [ -f "${SOURCE_ROOT}/core/scripts/update-fingerprint.py" ]; then
  fingerprint_args=(
    --source-root "${SOURCE_ROOT}"
    --project-root "${PROJECT_ROOT}"
    --agent-crew-home "${AGENT_CREW_HOME}"
    --codex-home "${CODEX_HOME:-${HOME}/.codex}"
    --claude-dir "${CLAUDE_DIR}"
    --path-bin "${AGENT_CREW_PATH_BIN:-${HOME}/.local/bin}"
    --fingerprint "${UPDATE_FINGERPRINT}"
  )
  if python3 "${SOURCE_ROOT}/core/scripts/update-fingerprint.py" "${fingerprint_args[@]}" --check >/dev/null 2>&1; then
    print_update_phase "fingerprint_check"
    if [ -n "${PRESERVATION_MANIFEST}" ]; then
      python3 "${SOURCE_ROOT}/core/scripts/update-preservation-manifest.py" finish \
        --manifest "${PRESERVATION_MANIFEST}"
      print_update_phase "preservation_manifest"
    fi

    verify_args=(
      --source-root "${SOURCE_ROOT}"
      --agent-crew-home "${AGENT_CREW_HOME}"
      --path-bin "${AGENT_CREW_PATH_BIN:-${HOME}/.local/bin}"
      --prune-extra
    )
    if ! path_crew_cli_is_managed; then
      verify_args+=(--skip-path-bin)
    fi
    python3 "${SOURCE_ROOT}/core/scripts/verify-install-drift.py" "${verify_args[@]}"
    print_update_phase "drift_verification"
    record_global_update_scope
    record_project_update_scope
    write_update_integrity_manifest
    print_update_total
    printf 'sync-local-install: no source/user/output drift detected; skipped adapter refresh\n'
    exit 0
  fi
  print_update_phase "fingerprint_check"
  python3 "${SOURCE_ROOT}/core/scripts/update-fingerprint.py" "${fingerprint_args[@]}" --format text || true
fi

mkdir -p \
  "${AGENT_CREW_HOME}/system/commands" "${AGENT_CREW_HOME}/commands" \
  "${AGENT_CREW_HOME}/system/rules" "${AGENT_CREW_HOME}/rules" \
  "${AGENT_CREW_HOME}/system/hooks" "${AGENT_CREW_HOME}/hooks" \
  "${AGENT_CREW_HOME}/system/scripts" "${AGENT_CREW_HOME}/scripts" \
  "${AGENT_CREW_HOME}/system/schemas" "${AGENT_CREW_HOME}/schemas" \
  "${AGENT_CREW_HOME}/system/policies" "${AGENT_CREW_HOME}/policies" \
  "${AGENT_CREW_HOME}/system/setup" "${AGENT_CREW_HOME}/setup" \
  "${AGENT_CREW_HOME}/system/adapters" "${AGENT_CREW_HOME}/adapters" \
  "${AGENT_CREW_HOME}/system/agents" "${AGENT_CREW_HOME}/system/skills" \
  "${AGENT_CREW_HOME}/skills" "${AGENT_CREW_HOME}/bin"

copy_flat() {
  local src="$1" dest="$2" pattern="$3"
  [ -d "${src}" ] || return 0
  # shellcheck disable=SC2086
  cp -f "${src}"/${pattern} "${dest}/" 2>/dev/null || true
}

copy_tree() {
  local src="$1" dest="$2"
  [ -d "${src}" ] || return 0
  cp -rf "${src}/." "${dest}/"
}

install_path_crew_cli() {
  local src="${SOURCE_ROOT}/core/bin/crew"
  local dest_dir="${AGENT_CREW_PATH_BIN:-${HOME}/.local/bin}"
  local dest="${dest_dir}/crew"
  [ -f "${src}" ] || return 0

  mkdir -p "${dest_dir}"
  if [ -f "${dest}" ] \
    && ! grep -q "experimental Codex launcher for agent-crew" "${dest}" 2>/dev/null \
    && ! grep -q "deterministic shell entrypoint for agent-crew" "${dest}" 2>/dev/null; then
    printf 'sync-local-install: skipping PATH crew CLI; unmanaged file exists at %s\n' "${dest}"
    PATH_CREW_CLI_MANAGED=0
    return 0
  fi

  cp -f "${src}" "${dest}"
  chmod +x "${dest}"
  PATH_CREW_CLI_MANAGED=1
  printf 'sync-local-install: installed native crew CLI at %s\n' "${dest}"
}

copy_flat "${SOURCE_ROOT}/core/commands" "${AGENT_CREW_HOME}/system/commands" "*.md"
copy_flat "${SOURCE_ROOT}/core/commands" "${AGENT_CREW_HOME}/commands" "*.md"
copy_tree "${SOURCE_ROOT}/core/rules" "${AGENT_CREW_HOME}/system/rules"
copy_tree "${SOURCE_ROOT}/core/rules" "${AGENT_CREW_HOME}/rules"
copy_flat "${SOURCE_ROOT}/core/hooks" "${AGENT_CREW_HOME}/system/hooks" "*.sh"
copy_flat "${SOURCE_ROOT}/core/hooks" "${AGENT_CREW_HOME}/hooks" "*.sh"
copy_tree "${SOURCE_ROOT}/core/scripts" "${AGENT_CREW_HOME}/system/scripts"
copy_tree "${SOURCE_ROOT}/core/scripts" "${AGENT_CREW_HOME}/scripts"
copy_tree "${SOURCE_ROOT}/core/evaluations" "${AGENT_CREW_HOME}/system/evaluations"
copy_tree "${SOURCE_ROOT}/core/evaluations" "${AGENT_CREW_HOME}/evaluations"
copy_flat "${SOURCE_ROOT}/core/schemas" "${AGENT_CREW_HOME}/system/schemas" "*.json"
copy_flat "${SOURCE_ROOT}/core/schemas" "${AGENT_CREW_HOME}/schemas" "*.json"
copy_tree "${SOURCE_ROOT}/core/policies" "${AGENT_CREW_HOME}/system/policies"
copy_tree "${SOURCE_ROOT}/core/policies" "${AGENT_CREW_HOME}/policies"
copy_flat "${SOURCE_ROOT}/core/setup" "${AGENT_CREW_HOME}/system/setup" "*.sh"
copy_flat "${SOURCE_ROOT}/core/setup" "${AGENT_CREW_HOME}/setup" "*.sh"
copy_tree "${SOURCE_ROOT}/adapters" "${AGENT_CREW_HOME}/system/adapters"
copy_tree "${SOURCE_ROOT}/adapters" "${AGENT_CREW_HOME}/adapters"
copy_tree "${SOURCE_ROOT}/core/agents" "${AGENT_CREW_HOME}/system/agents"
copy_tree "${SOURCE_ROOT}/core/agents/skills" "${AGENT_CREW_HOME}/system/skills"
copy_flat "${SOURCE_ROOT}/core/bin" "${AGENT_CREW_HOME}/bin" "*"
install_path_crew_cli
print_update_phase "asset_copy"
record_global_update_scope

chmod +x \
  "${AGENT_CREW_HOME}/system/hooks/"*.sh "${AGENT_CREW_HOME}/hooks/"*.sh \
  "${AGENT_CREW_HOME}/system/scripts/"*.sh "${AGENT_CREW_HOME}/scripts/"*.sh \
  "${AGENT_CREW_HOME}/system/scripts/"*.py "${AGENT_CREW_HOME}/scripts/"*.py \
  "${AGENT_CREW_HOME}/system/setup/"*.sh "${AGENT_CREW_HOME}/setup/"*.sh \
  "${AGENT_CREW_HOME}/system/adapters/"*/bin/* "${AGENT_CREW_HOME}/adapters/"*/bin/* \
  "${AGENT_CREW_HOME}/bin/"* \
  2>/dev/null || true

# shellcheck source=/dev/null
. "${AGENT_CREW_HOME}/system/setup/common.sh"

sync_system_agents \
  "${SOURCE_ROOT}/core/agents" \
  "${AGENT_CREW_HOME}/system/agents" \
  "mcp-manager.md"

merge_agents_to_discovery \
  "${AGENT_CREW_HOME}/system/agents" \
  "${AGENT_CREW_HOME}/user/agents" \
  "${CLAUDE_DIR}/agents"

sync_system_skills \
  "${SOURCE_ROOT}/core/agents/skills" \
  "${AGENT_CREW_HOME}/system/skills"

merge_skills_to_discovery \
  "${AGENT_CREW_HOME}/system/skills" \
  "${AGENT_CREW_HOME}/user/skills" \
  "${AGENT_CREW_HOME}/skills"

SOURCE_ROOT="${SOURCE_ROOT}" AGENT_CREW_MODE=update \
  bash "${AGENT_CREW_HOME}/system/scripts/update-global-adapters.sh"

SOURCE_ROOT="${SOURCE_ROOT}" AGENT_CREW_MODE=update \
  bash "${AGENT_CREW_HOME}/system/setup/setup-host.sh" "${PROJECT_ROOT}"
print_update_phase "adapter_setup"
record_project_update_scope

if [ -n "${PRESERVATION_MANIFEST}" ]; then
  python3 "${AGENT_CREW_HOME}/system/scripts/update-preservation-manifest.py" finish \
    --manifest "${PRESERVATION_MANIFEST}"
  print_update_phase "preservation_manifest"
fi

verify_args=(
  --source-root "${SOURCE_ROOT}"
  --agent-crew-home "${AGENT_CREW_HOME}"
  --path-bin "${AGENT_CREW_PATH_BIN:-${HOME}/.local/bin}"
  --prune-extra
)
if [ "${PATH_CREW_CLI_MANAGED}" != "1" ]; then
  verify_args+=(--skip-path-bin)
fi
python3 "${AGENT_CREW_HOME}/system/scripts/verify-install-drift.py" "${verify_args[@]}"
print_update_phase "drift_verification"

if [ -f "${AGENT_CREW_HOME}/system/scripts/update-fingerprint.py" ]; then
  python3 "${AGENT_CREW_HOME}/system/scripts/update-fingerprint.py" \
    --source-root "${SOURCE_ROOT}" \
    --project-root "${PROJECT_ROOT}" \
    --agent-crew-home "${AGENT_CREW_HOME}" \
    --codex-home "${CODEX_HOME:-${HOME}/.codex}" \
    --claude-dir "${CLAUDE_DIR}" \
    --path-bin "${AGENT_CREW_PATH_BIN:-${HOME}/.local/bin}" \
    --fingerprint "${UPDATE_FINGERPRINT}" \
    --write >/dev/null
  print_update_phase "fingerprint_write"
fi

print_update_total
printf 'sync-local-install: refreshed installed assets from %s\n' "${SOURCE_ROOT}"

write_update_integrity_manifest
