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
pattern = re.escape(start) + r".*?" + re.escape(end)
if re.search(pattern, content, re.DOTALL):
    content = re.sub(pattern, new_section.rstrip("\n"), content, flags=re.DOTALL)
else:
    content = content.rstrip("\n")
    content = f"{content}\n\n{new_section}" if content else new_section

dest.parent.mkdir(parents=True, exist_ok=True)
dest.write_text(content)
PYEOF
}
