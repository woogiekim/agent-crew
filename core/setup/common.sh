#!/usr/bin/env bash
set -euo pipefail

copy_dir_contents() {
  local src="$1" dest="$2"
  [ -d "${src}" ] || return 0
  mkdir -p "${dest}"
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
  cp "${source_agents}/"*.md "${system_agents}/" 2>/dev/null || true
  if [ -d "${source_agents}/skills" ]; then
    cp "${source_agents}/skills/"*.md "${system_agents}/skills/" 2>/dev/null || true
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
  local skipped=0

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
      # Repo agent or system exception: already handled by sync_system_agents
      skipped=$((skipped + 1))
    else
      # Non-repo, non-exception: belongs in user/agents/
      if [ ! -f "${user_agents}/${basename_file}" ]; then
        mkdir -p "${user_agents}"
        cp "${legacy_file}" "${user_agents}/${basename_file}"
        printf '[agent-crew] Migrated %s → user/agents/\n' "${basename_file}"
        migrated=$((migrated + 1))
      else
        printf '[agent-crew] Skipping %s — already present in user/agents/\n' "${basename_file}"
        skipped=$((skipped + 1))
      fi
    fi
  done < <(find "${legacy_agents}" -maxdepth 1 -name "*.md" -print0 2>/dev/null)

  if [ "${migrated}" -gt 0 ] || [ "${skipped}" -gt 0 ]; then
    printf '[agent-crew] Legacy agents migration: %d moved to user/agents/, %d already classified\n' \
      "${migrated}" "${skipped}"
  fi

  # Remove the legacy directory if it only contains auto-migrated or already-handled files
  # (caller may also do this explicitly after verifying)
  local remaining_md
  remaining_md=$(find "${legacy_agents}" -maxdepth 1 -name "*.md" 2>/dev/null | wc -l | tr -d ' ')
  if [ "${remaining_md}" -eq 0 ]; then
    rm -rf "${legacy_agents}"
    printf '[agent-crew] Removed empty legacy agents directory: %s\n' "${legacy_agents}"
  else
    printf '[agent-crew] NOTE: Legacy agents directory still has %d .md files — review manually:\n' "${remaining_md}"
    find "${legacy_agents}" -maxdepth 1 -name "*.md" 2>/dev/null | while IFS= read -r f; do
      printf '  %s\n' "${f}"
    done
    printf 'Move non-system files to user/agents/, then delete %s\n' "${legacy_agents}"
  fi
}

# Merge system and user agents into the discovery destination (~/.claude/agents/).
#
# Policy (Option B): if the same filename exists in both system/agents/ and
# user/agents/, emit a warning and skip copying that file from user/. The
# system copy is always placed first; only non-conflicting user agents follow.
#
# Stale cleanup: any .md file in dest that is not present in system/agents/ AND
# not present in user/agents/ is removed, preventing old removed agents from
# lingering in the discovery path across updates. Stale .md files in the
# dest/skills/ subdirectory (not present in system/agents/skills/) are also
# removed.
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

  # Remove stale skills from dest/skills/: files not in system/agents/skills/
  if [ -d "${dest}/skills" ]; then
    while IFS= read -r -d '' dest_skill; do
      local basename_file
      basename_file=$(basename "${dest_skill}")
      if [ ! -f "${system_agents}/skills/${basename_file}" ]; then
        printf '[agent-crew] Removing stale agent skill from discovery: %s\n' "${basename_file}"
        rm -f "${dest_skill}"
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
        [ "${is_conflict}" -eq 0 ] && cp "${user_file}" "${dest}/"
      done < <(find "${user_agents}" -maxdepth 1 -name "*.md" -print0 2>/dev/null)
    else
      # No conflicts — copy all user agents (excluding README.md)
      while IFS= read -r -d '' user_file; do
        local basename_file
        basename_file=$(basename "${user_file}")
        [ "${basename_file}" = "README.md" ] && continue
        cp "${user_file}" "${dest}/"
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
