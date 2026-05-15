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

# Merge system and user agents into the discovery destination (~/.claude/agents/).
#
# Policy (Option B): if the same filename exists in both system/agents/ and
# user/agents/, emit a warning and skip copying that file from user/. The
# system copy is always placed first; only non-conflicting user agents follow.
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

  # Copy system agents first (idempotent — cp -R overwrites existing files)
  copy_dir_contents "${system_agents}" "${dest}"

  # Merge user agents with conflict detection
  if [ -d "${user_agents}" ]; then
    local conflicts=()
    while IFS= read -r -d '' user_file; do
      local basename_file
      basename_file=$(basename "${user_file}")
      if [ -f "${dest}/${basename_file}" ]; then
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
        local is_conflict=0
        for c in "${conflicts[@]}"; do
          [ "${basename_file}" = "${c}" ] && is_conflict=1 && break
        done
        [ "${is_conflict}" -eq 0 ] && cp "${user_file}" "${dest}/"
      done < <(find "${user_agents}" -maxdepth 1 -name "*.md" -print0 2>/dev/null)
    else
      # No conflicts — copy all user agents
      copy_dir_contents "${user_agents}" "${dest}"
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
new_section = f"{start}\n{src.read_text()}\n{end}\n"

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
