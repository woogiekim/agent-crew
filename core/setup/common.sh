#!/usr/bin/env bash
set -euo pipefail

if [ -f "${AGENT_CREW_HOME:-${HOME}/.agent-crew}/scripts/project-state.sh" ]; then
  # shellcheck source=/dev/null
  . "${AGENT_CREW_HOME:-${HOME}/.agent-crew}/scripts/project-state.sh"
elif [ -n "${SOURCE_ROOT:-}" ] && [ -f "${SOURCE_ROOT}/core/scripts/project-state.sh" ]; then
  # shellcheck source=/dev/null
  . "${SOURCE_ROOT}/core/scripts/project-state.sh"
fi

# ── Visual diff helpers ────────────────────────────────────────────────────────
# Accumulates per-file change summaries for the final summary block.
# Each entry format: "<label>(<dest>)\t+<added> -<removed>"
_DIFF_LOG=()

# diff_copy <src> <dest> [label]
#
# Copies src to dest while printing an inline diff in Claude Code Edit style:
#   Update(path)           — if dest already exists
#   Install(path)          — if dest is new
#   Added N lines / Removed N lines
#   + added line
#   - removed line
#
# Appends a summary entry to _DIFF_LOG for print_diff_summary.
# Falls back to a plain cp when python3 is unavailable.
diff_copy() {
  local src="$1"
  local dest="$2"
  local label="${3:-}"

  [ -f "${src}" ] || return 0

  # Determine label from file existence
  if [ -z "${label}" ]; then
    if [ -f "${dest}" ]; then
      label="Update"
    else
      label="Install"
    fi
  fi

  mkdir -p "$(dirname "${dest}")"

  # Compute diff via python3 (cross-platform, no external diff flags needed)
  if command -v python3 >/dev/null 2>&1; then
    local diff_output
    diff_output=$(python3 - "${src}" "${dest}" "${label}" <<'PYEOF'
import sys, difflib
from pathlib import Path

src_path  = sys.argv[1]
dest_path = sys.argv[2]
label     = sys.argv[3]

src_lines  = Path(src_path).read_text(errors="replace").splitlines()
dest_lines = Path(dest_path).read_text(errors="replace").splitlines() \
             if Path(dest_path).exists() else []

added   = sum(1 for l in difflib.unified_diff(dest_lines, src_lines) if l.startswith('+') and not l.startswith('+++'))
removed = sum(1 for l in difflib.unified_diff(dest_lines, src_lines) if l.startswith('-') and not l.startswith('---'))

print(f"{label}({dest_path})")
if added == 0 and removed == 0:
    print("  (no changes)")
else:
    parts = []
    if added:   parts.append(f"Added {added} lines")
    if removed: parts.append(f"Removed {removed} lines")
    print("  " + " / ".join(parts))
    for line in difflib.unified_diff(dest_lines, src_lines, lineterm=""):
        if line.startswith('+++') or line.startswith('---') or line.startswith('@@'):
            continue
        if line.startswith('+'):
            print(f"  {line}")
        elif line.startswith('-'):
            print(f"  {line}")

# Summary token on last line (tab-separated, not shown to user)
print(f"__DIFF_SUMMARY__\t{label}({dest_path})\t+{added}\t-{removed}", end="")
PYEOF
    )

    # Split off summary token before printing
    local visible summary
    visible=$(printf '%s\n' "${diff_output}" | grep -v '^__DIFF_SUMMARY__')
    summary=$(printf '%s\n' "${diff_output}" | grep '^__DIFF_SUMMARY__' | cut -f2-)
    printf '%s\n' "${visible}"
    [ -n "${summary}" ] && _DIFF_LOG+=("${summary}")
  else
    # Fallback: plain copy, no diff output
    printf '%s(%s)\n' "${label}" "${dest}"
    _DIFF_LOG+=("${label}(${dest})\t(diff unavailable — python3 not found)")
  fi

  cp "${src}" "${dest}"
}

# diff_install <src_dir> <dest_dir>
#
# Iterates every regular file in src_dir and calls diff_copy for each.
# Produces per-file diff output inline, identical to what diff_copy emits.
diff_install() {
  local src="$1"
  local dest="$2"
  [ -d "${src}" ] || return 0
  mkdir -p "${dest}"
  while IFS= read -r -d '' src_file; do
    local rel_path
    rel_path="${src_file#${src}/}"
    diff_copy "${src_file}" "${dest}/${rel_path}"
  done < <(find "${src}" -type f ! -name ".DS_Store" -print0 2>/dev/null | LC_ALL=C sort -z)
}

# print_diff_summary
#
# Prints the accumulated _DIFF_LOG entries as a final summary block.
# Call once at the end of install/update scripts after all copy operations.
print_diff_summary() {
  if [ ${#_DIFF_LOG[@]} -eq 0 ]; then
    return 0
  fi
  printf '\n'
  printf '════════════════════════════════════════\n'
  printf '  File Change Summary\n'
  printf '════════════════════════════════════════\n'
  local total_added=0 total_removed=0
  for entry in "${_DIFF_LOG[@]}"; do
    local path_label added_count removed_count
    path_label=$(printf '%s' "${entry}" | cut -f1)
    added_count=$(printf '%s' "${entry}" | cut -f2 | tr -d '+')
    removed_count=$(printf '%s' "${entry}" | cut -f3 | tr -d '-')
    # Accumulate totals when values are numeric
    if [[ "${added_count}" =~ ^[0-9]+$ ]]; then
      total_added=$((total_added + added_count))
    fi
    if [[ "${removed_count}" =~ ^[0-9]+$ ]]; then
      total_removed=$((total_removed + removed_count))
    fi
    printf '  %s  +%s -%s\n' "${path_label}" "${added_count:-0}" "${removed_count:-0}"
  done
  printf '────────────────────────────────────────\n'
  printf '  %d file(s) changed  +%d -%d\n' "${#_DIFF_LOG[@]}" "${total_added}" "${total_removed}"
  printf '════════════════════════════════════════\n'
}
# ── End visual diff helpers ────────────────────────────────────────────────────

copy_dir_contents() {
  local src="$1" dest="$2"
  [ -d "${src}" ] || return 0
  mkdir -p "${dest}"
  diff_install "${src}" "${dest}"
  find "${dest}" -name ".DS_Store" -delete 2>/dev/null || true
}

copy_file_if_changed() {
  local src="$1" dest="$2"
  [ -f "${src}" ] || return 0
  mkdir -p "$(dirname "${dest}")"
  if [ -f "${dest}" ] && cmp -s "${src}" "${dest}" 2>/dev/null; then
    return 0
  fi
  cp -f "${src}" "${dest}"
}

sync_dir_contents_prune() {
  local src="$1" dest="$2"
  [ -d "${src}" ] || return 0
  mkdir -p "${dest}"

  while IFS= read -r -d '' dest_file; do
    local rel
    rel="${dest_file#"${dest}/"}"
    if [ ! -e "${src}/${rel}" ]; then
      printf '[agent-crew] Removing stale file from %s: %s\n' "${dest}" "${rel}"
      rm -f "${dest_file}"
    fi
  done < <(find "${dest}" -type f -print0 2>/dev/null)

  cp -R "${src}/." "${dest}/"
  find "${dest}" -name ".DS_Store" -delete 2>/dev/null || true
}

register_local_git_excludes() {
  local project_root="$1"
  shift

  git -C "${project_root}" rev-parse --is-inside-work-tree >/dev/null 2>&1 || return 0

  local exclude_file
  exclude_file="$(git -C "${project_root}" rev-parse --git-path info/exclude)"
  mkdir -p "$(dirname "${exclude_file}")"
  touch "${exclude_file}"

  python3 - "${exclude_file}" "$@" <<'PYEOF'
import sys
from pathlib import Path

exclude_path = Path(sys.argv[1])
entries = [entry for entry in sys.argv[2:] if entry]
marker_start = "# agent-crew generated artifacts"
marker_end = "# /agent-crew generated artifacts"

existing = exclude_path.read_text().splitlines() if exclude_path.exists() else []

outside = []
inside = False
for line in existing:
    if line == marker_start:
        inside = True
        continue
    if line == marker_end:
        inside = False
        continue
    if not inside:
        outside.append(line)

block = [marker_start, *entries, marker_end]
content = outside
if content and content[-1] != "":
    content.append("")
content.extend(block)
exclude_path.write_text("\n".join(content).rstrip("\n") + "\n")
PYEOF
}

# Sync system agents from source to system/agents/ destination, enforcing that
# only agents present in the source (or matching the exception list) remain.
# Files in system/agents/ that are not in source AND not in the exception list
# are removed to prevent stale agents accumulating over updates.
#
# Classification rules:
#   - Agents in the remote repo source  → system layer (copied from source)
#   - Agents NOT in remote repo source  → user layer   (should not be in system)
#   - Exception: mcp-manager            → always system (hard-coded exception)
#
# Arguments:
#   $1  source_agents  — e.g. core/agents/ from the repo
#   $2  system_agents  — e.g. ~/.agent-crew/system/agents/
#   $3  exceptions     — space-separated list of agent basenames that are always
#                        kept in system even if absent from source (e.g. "mcp-manager.md")
sync_system_agents() {
  local source_agents="$1"
  local system_agents="$2"
  local exceptions="${3:-mcp-manager.md}"

  [ -d "${source_agents}" ] || return 0
  mkdir -p "${system_agents}/skills"

  # Copy all source agents into system (update existing, add new)
  while IFS= read -r -d '' src_file; do
    local basename_file
    basename_file=$(basename "${src_file}")
    diff_copy "${src_file}" "${system_agents}/${basename_file}"
  done < <(find "${source_agents}" -maxdepth 1 -name "*.md" -print0 2>/dev/null | LC_ALL=C sort -z)
  if [ -d "${source_agents}/skills" ]; then
    while IFS= read -r -d '' src_file; do
      local basename_file
      basename_file=$(basename "${src_file}")
      diff_copy "${src_file}" "${system_agents}/skills/${basename_file}"
    done < <(find "${source_agents}/skills" -maxdepth 1 -name "*.md" -print0 2>/dev/null | LC_ALL=C sort -z)
  fi

  # Remove stale system agents: those not in source AND not in exceptions list
  while IFS= read -r -d '' system_file; do
    local basename_file
    basename_file=$(basename "${system_file}")

    # Check if in exceptions list
    local is_exception=0
    for exc in ${exceptions}; do
      [ "${basename_file}" = "${exc}" ] && is_exception=1 && break
    done
    [ "${is_exception}" -eq 1 ] && continue

    # Check if in source
    if [ ! -f "${source_agents}/${basename_file}" ]; then
      printf '[agent-crew] Removing stale system agent: %s (not in source, not an exception)\n' "${basename_file}"
      rm -f "${system_file}"
    fi
  done < <(find "${system_agents}" -maxdepth 1 -name "*.md" -print0 2>/dev/null)

  # Remove stale skills from system/agents/skills/: those no longer in source/skills/
  if [ -d "${system_agents}/skills" ]; then
    while IFS= read -r -d '' skill_file; do
      local basename_file
      basename_file=$(basename "${skill_file}")
      if [ ! -f "${source_agents}/skills/${basename_file}" ]; then
        printf '[agent-crew] Removing stale system agent skill: %s (not in source)\n' "${basename_file}"
        rm -f "${skill_file}"
      fi
    done < <(find "${system_agents}/skills" -maxdepth 1 -name "*.md" -print0 2>/dev/null)
  fi

  find "${system_agents}" -name ".DS_Store" -delete 2>/dev/null || true
}

# Migrate legacy ~/.agent-crew/agents/ flat directory to proper system/user layers.
# Non-repo files that aren't already in system or user are moved to user/agents/.
# After migration, if the legacy directory is empty (or contains only subdirs), it
# can be removed by the caller.
#
# Arguments:
#   $1  legacy_agents  — e.g. ~/.agent-crew/agents/
#   $2  source_agents  — e.g. core/agents/ from the repo (to determine repo membership)
#   $3  system_agents  — e.g. ~/.agent-crew/system/agents/
#   $4  user_agents    — e.g. ~/.agent-crew/user/agents/
#   $5  exceptions     — space-separated list always kept in system (e.g. "mcp-manager.md")
migrate_legacy_agents() {
  local legacy_agents="$1"
  local source_agents="$2"
  local system_agents="$3"
  local user_agents="$4"
  local exceptions="${5:-mcp-manager.md}"

  [ -d "${legacy_agents}" ] || return 0

  local migrated=0
  local removed=0
  local retained=0

  while IFS= read -r -d '' legacy_file; do
    local basename_file
    basename_file=$(basename "${legacy_file}")

    # Skip README.md
    [ "${basename_file}" = "README.md" ] && continue

    # Determine classification
    local in_source=0
    local is_exception=0

    [ -f "${source_agents}/${basename_file}" ] && in_source=1

    for exc in ${exceptions}; do
      [ "${basename_file}" = "${exc}" ] && is_exception=1 && break
    done

    if [ "${in_source}" -eq 1 ] || [ "${is_exception}" -eq 1 ]; then
      # Repo agent or system exception: already handled by sync_system_agents.
      # Remove only exact duplicates. A differing file may contain user edits
      # from the legacy flat layout, so keep it for manual review.
      local canonical_file=""
      if [ -f "${source_agents}/${basename_file}" ]; then
        canonical_file="${source_agents}/${basename_file}"
      elif [ -f "${system_agents}/${basename_file}" ]; then
        canonical_file="${system_agents}/${basename_file}"
      fi

      if [ -n "${canonical_file}" ] && cmp -s "${legacy_file}" "${canonical_file}"; then
        rm -f "${legacy_file}"
        removed=$((removed + 1))
      else
        retained=$((retained + 1))
      fi
    else
      # Non-repo, non-exception: belongs in user/agents/
      if [ ! -f "${user_agents}/${basename_file}" ]; then
        mkdir -p "${user_agents}"
        diff_copy "${legacy_file}" "${user_agents}/${basename_file}" "Install"
        printf '[agent-crew] Migrated %s → user/agents/\n' "${basename_file}"
        rm -f "${legacy_file}"
        migrated=$((migrated + 1))
      elif cmp -s "${legacy_file}" "${user_agents}/${basename_file}"; then
        rm -f "${legacy_file}"
        removed=$((removed + 1))
      else
        printf '[agent-crew] Preserving %s — differs from user/agents copy\n' "${legacy_file}"
        retained=$((retained + 1))
      fi
    fi
  done < <(find "${legacy_agents}" -maxdepth 1 -name "*.md" -print0 2>/dev/null)

  if [ "${migrated}" -gt 0 ] || [ "${removed}" -gt 0 ] || [ "${retained}" -gt 0 ]; then
    printf '[agent-crew] Legacy agents migration: %d moved to user/agents/, %d duplicate system/user file(s) removed, %d retained for review\n' \
      "${migrated}" "${removed}" "${retained}"
  fi

  # Remove the legacy directory if it only contains auto-migrated or duplicate files.
  local remaining_md
  remaining_md=$(find "${legacy_agents}" -maxdepth 1 -name "*.md" 2>/dev/null | wc -l | tr -d ' ')
  if [ "${remaining_md}" -eq 0 ]; then
    rm -rf "${legacy_agents}"
    printf '[agent-crew] Removed empty legacy agents directory: %s\n' "${legacy_agents}"
  else
    printf '[agent-crew] NOTE: Legacy agents directory has %d possible user-modified file(s); preserved for manual review at %s\n' \
      "${remaining_md}" "${legacy_agents}"
    if [ "${AGENT_CREW_VERBOSE_LEGACY_AGENTS:-0}" = "1" ]; then
      find "${legacy_agents}" -maxdepth 1 -name "*.md" 2>/dev/null | while IFS= read -r f; do
        printf '  %s\n' "${f}"
      done
    fi
  fi
}

# Merge system and user agents into the discovery destination (~/.claude/agents/).
#
# Policy (Option B): if the same filename exists in both system/agents/ and
# user/agents/, emit a warning and skip copying that file from user/. The
# system copy is always placed first; only non-conflicting user agents follow.
#
# Stale cleanup: any top-level .md file in dest that is not present in
# system/agents/ AND not present in user/agents/ is removed, preventing old
# removed agents from lingering in the discovery path across updates.
#
# The dest/skills/ subdirectory is a shared host discovery path. Agent-crew
# refreshes skills that are present in system/agents/skills/ through the normal
# copy step, but preserves unknown third-party skill files instead of deleting
# them without an ownership manifest.
#
# Arguments:
#   $1  system_agents  — e.g. ~/.agent-crew/system/agents/
#   $2  user_agents    — e.g. ~/.agent-crew/user/agents/
#   $3  dest           — e.g. ~/.claude/agents/
merge_agents_to_discovery() {
  local system_agents="$1"
  local user_agents="$2"
  local dest="$3"

  mkdir -p "${dest}"

  # Remove stale agents from dest: files not in system OR user
  while IFS= read -r -d '' dest_file; do
    local basename_file
    basename_file=$(basename "${dest_file}")
    [ "${basename_file}" = "README.md" ] && continue

    local in_system=0
    local in_user=0
    [ -f "${system_agents}/${basename_file}" ] && in_system=1
    [ -f "${user_agents}/${basename_file}" ] && in_user=1

    if [ "${in_system}" -eq 0 ] && [ "${in_user}" -eq 0 ]; then
      printf '[agent-crew] Removing stale agent from discovery: %s\n' "${basename_file}"
      rm -f "${dest_file}"
    fi
  done < <(find "${dest}" -maxdepth 1 -name "*.md" -print0 2>/dev/null)

  # Preserve third-party skills in the shared dest/skills/ discovery path.
  if [ -d "${dest}/skills" ]; then
    while IFS= read -r -d '' dest_skill; do
      local basename_file
      basename_file=$(basename "${dest_skill}")

      local in_system_skill=0
      local in_user_skill=0
      [ -f "${system_agents}/skills/${basename_file}" ] && in_system_skill=1
      [ -f "${user_agents}/skills/${basename_file}" ] && in_user_skill=1

      if [ "${in_system_skill}" -eq 0 ] && [ "${in_user_skill}" -eq 0 ]; then
        printf '[agent-crew] Preserving non-agent-crew skill in discovery: %s\n' "${basename_file}"
      fi
    done < <(find "${dest}/skills" -maxdepth 1 -name "*.md" -print0 2>/dev/null)
  fi

  # Copy system agents first (idempotent — cp -R overwrites existing files)
  copy_dir_contents "${system_agents}" "${dest}"

  # Merge user agents with conflict detection
  if [ -d "${user_agents}" ]; then
    local conflicts=()
    while IFS= read -r -d '' user_file; do
      local basename_file
      basename_file=$(basename "${user_file}")
      [ "${basename_file}" = "README.md" ] && continue
      if [ -f "${system_agents}/${basename_file}" ]; then
        conflicts+=("${basename_file}")
      fi
    done < <(find "${user_agents}" -maxdepth 1 -name "*.md" -print0 2>/dev/null)

    if [ ${#conflicts[@]} -gt 0 ]; then
      printf '\n[agent-crew] WARNING: Name conflict detected in user agents:\n' >&2
      for c in "${conflicts[@]}"; do
        printf '  conflict: %s exists in both system/agents/ and user/agents/\n' "${c}" >&2
      done
      printf 'Rename the file in user/agents/ to a unique name, then re-run crew:update.\n' >&2
      printf 'User agents with conflicts were NOT copied to discovery path.\n\n' >&2
      # Copy non-conflicting user agents only
      while IFS= read -r -d '' user_file; do
        local basename_file
        basename_file=$(basename "${user_file}")
        [ "${basename_file}" = "README.md" ] && continue
        local is_conflict=0
        for c in "${conflicts[@]}"; do
          [ "${basename_file}" = "${c}" ] && is_conflict=1 && break
        done
        [ "${is_conflict}" -eq 0 ] && diff_copy "${user_file}" "${dest}/$(basename "${user_file}")"
      done < <(find "${user_agents}" -maxdepth 1 -name "*.md" -print0 2>/dev/null)
    else
      # No conflicts — copy all user agents (excluding README.md)
      while IFS= read -r -d '' user_file; do
        local basename_file
        basename_file=$(basename "${user_file}")
        [ "${basename_file}" = "README.md" ] && continue
        diff_copy "${user_file}" "${dest}/${basename_file}"
      done < <(find "${user_agents}" -maxdepth 1 -name "*.md" -print0 2>/dev/null)
    fi
  fi
}

# Sync system skills from source to system/skills/ destination, enforcing that
# only skills present in the source remain. Files in system/skills/ that are not
# in source are removed to prevent stale skills accumulating over updates.
#
# Classification rules:
#   - Skills in the remote repo source  → system layer (copied from source)
#   - Skills NOT in remote repo source  → user layer   (should not be in system)
#
# Arguments:
#   $1  source_skills  — e.g. core/agents/skills/ from the repo
#   $2  system_skills  — e.g. ~/.agent-crew/system/skills/
sync_system_skills() {
  local source_skills="$1"
  local system_skills="$2"

  [ -d "${source_skills}" ] || return 0
  mkdir -p "${system_skills}"

  # Copy all source skills into system (update existing, add new)
  cp "${source_skills}/"*.md "${system_skills}/" 2>/dev/null || true

  # Remove stale system skills: those not in source
  while IFS= read -r -d '' system_file; do
    local basename_file
    basename_file=$(basename "${system_file}")

    if [ ! -f "${source_skills}/${basename_file}" ]; then
      printf '[agent-crew] Removing stale system skill: %s (not in source)\n' "${basename_file}"
      rm -f "${system_file}"
    fi
  done < <(find "${system_skills}" -maxdepth 1 -name "*.md" -print0 2>/dev/null)

  find "${system_skills}" -name ".DS_Store" -delete 2>/dev/null || true
}

# Merge system and user skills into the discovery destination.
#
# Policy: if the same filename exists in both system/skills/ and user/skills/,
# the user skill wins — the user copy is placed after the system copy, so it
# overwrites the system version in the discovery path.
#
# Stale cleanup: any .md file in dest that is not present in system/skills/ AND
# not present in user/skills/ is removed, preventing old removed skills from
# lingering in the discovery path across updates.
#
# Arguments:
#   $1  system_skills  — e.g. ~/.agent-crew/system/skills/
#   $2  user_skills    — e.g. ~/.agent-crew/user/skills/
#   $3  dest           — e.g. ~/.agent-crew/skills/  (the unified discovery path)
merge_skills_to_discovery() {
  local system_skills="$1"
  local user_skills="$2"
  local dest="$3"

  mkdir -p "${dest}"

  # Remove stale skills from dest: files not in system OR user
  while IFS= read -r -d '' dest_file; do
    local basename_file
    basename_file=$(basename "${dest_file}")

    local in_system=0
    local in_user=0
    [ -f "${system_skills}/${basename_file}" ] && in_system=1
    [ -f "${user_skills}/${basename_file}" ] && in_user=1

    if [ "${in_system}" -eq 0 ] && [ "${in_user}" -eq 0 ]; then
      printf '[agent-crew] Removing stale skill from discovery: %s\n' "${basename_file}"
      rm -f "${dest_file}"
    fi
  done < <(find "${dest}" -maxdepth 1 -name "*.md" -print0 2>/dev/null)

  # Copy system skills first (idempotent — cp overwrites existing files)
  if [ -d "${system_skills}" ]; then
    while IFS= read -r -d '' system_file; do
      cp "${system_file}" "${dest}/"
    done < <(find "${system_skills}" -maxdepth 1 -name "*.md" -print0 2>/dev/null)
  fi

  # User skills overwrite system skills with the same name (user wins)
  if [ -d "${user_skills}" ]; then
    local overrides=()
    while IFS= read -r -d '' user_file; do
      local basename_file
      basename_file=$(basename "${user_file}")
      if [ -f "${system_skills}/${basename_file}" ]; then
        overrides+=("${basename_file}")
      fi
      cp "${user_file}" "${dest}/"
    done < <(find "${user_skills}" -maxdepth 1 -name "*.md" -print0 2>/dev/null)

    if [ ${#overrides[@]} -gt 0 ]; then
      printf '\n[agent-crew] INFO: User skills overriding system skills (user wins):\n'
      printf '  user/skills files are not overwritten by system updates; edit the user file or run crew update --reconcile-skills to compare.\n'
      for o in "${overrides[@]}"; do
        printf '  override: %s (user/skills/ takes precedence over system/skills/)\n' "${o}"
      done
    fi
  fi
}

merge_agent_crew_section() {
  local src="$1" dest="$2"
  local start="<!-- agent-crew-start -->"
  local end="<!-- agent-crew-end -->"
  [ -f "${src}" ] || return 0

  python3 - "$src" "$dest" "$start" "$end" <<'PYEOF'
import re
import sys
from pathlib import Path

src = Path(sys.argv[1])
dest = Path(sys.argv[2])
start = sys.argv[3]
end = sys.argv[4]
src_content = src.read_text().strip()
if start in src_content and end in src_content:
    new_section = f"{src_content}\n"
else:
    new_section = f"{start}\n{src_content}\n{end}\n"

content = dest.read_text() if dest.exists() else ""
pattern = re.escape(start) + r".*" + re.escape(end)
if re.search(pattern, content, re.DOTALL):
    content = re.sub(pattern, new_section.rstrip("\n"), content, count=1, flags=re.DOTALL)
else:
    content = content.rstrip("\n")
    content = f"{content}\n\n{new_section}" if content else new_section

dest.parent.mkdir(parents=True, exist_ok=True)
dest.write_text(content)
PYEOF
}
