#!/usr/bin/env bash
# update-diff.sh — snapshot helper for `crew:update`.
#
# Produces a deterministic, sorted list of SHA256 file hashes for every
# regular file under a target directory. Used by the crew:update skill to
# capture a pre-update and post-update fingerprint of the install location
# so the resulting diff (post-snapshot lines absent or different vs the
# pre-snapshot) yields the "updated files" report.
#
# Usage:
#   update-diff.sh <target-dir>            # print snapshot to stdout
#   update-diff.sh diff <before> <after>   # print updated / unchanged summary
#
# Pure tooling helper. Never modifies the target directory. Never touches
# state files. Safe to invoke from any context.

set -euo pipefail

snapshot() {
  local target="$1"
  [ -d "${target}" ] || return 0

  # Stable, deterministic ordering. Use `find -print0 | sort -z` so paths
  # with spaces or special chars do not break the diff comparison.
  if command -v shasum >/dev/null 2>&1; then
    HASH_CMD="shasum -a 256"
  elif command -v sha256sum >/dev/null 2>&1; then
    HASH_CMD="sha256sum"
  else
    printf 'update-diff: no sha256 tool available (shasum or sha256sum required)\n' >&2
    return 1
  fi

  # Output format: "<hash>  <relative_path>" — relative to target so two
  # snapshots taken from the same target compare cleanly even if the
  # absolute path changes.
  (
    cd "${target}"
    find . -type f \
      ! -path './.git/*' \
      ! -name '.DS_Store' \
      -print0 \
    | LC_ALL=C sort -z \
    | xargs -0 ${HASH_CMD} 2>/dev/null
  )
}

diff_snapshots() {
  local before="$1" after="$2"
  [ -f "${before}" ] || { printf 'update-diff: before snapshot missing: %s\n' "${before}" >&2; return 1; }
  [ -f "${after}" ]  || { printf 'update-diff: after snapshot missing: %s\n' "${after}" >&2; return 1; }

  python3 - "${before}" "${after}" <<'PYEOF'
import sys
from pathlib import Path

def load(path):
    out = {}
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        # Format: "<hash>  <relative_path>" — split on first run of whitespace.
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        out[parts[1]] = parts[0]
    return out

before = load(sys.argv[1])
after = load(sys.argv[2])

paths = sorted(set(before) | set(after))
updated, added, removed, unchanged = [], [], [], 0
for p in paths:
    b = before.get(p)
    a = after.get(p)
    if b is None and a is not None:
        added.append(p)
    elif a is None and b is not None:
        removed.append(p)
    elif a != b:
        updated.append(p)
    else:
        unchanged += 1

total = len(paths)
print(f"total: {total}")
print(f"updated: {len(updated)}")
print(f"added: {len(added)}")
print(f"removed: {len(removed)}")
print(f"unchanged: {unchanged}")

def head(items, limit=20):
    return items[:limit]

if updated:
    print("--- updated files ---")
    for p in head(updated):
        print(f"  ~ {p}")
    if len(updated) > 20:
        print(f"  ... and {len(updated) - 20} more")
if added:
    print("--- added files ---")
    for p in head(added):
        print(f"  + {p}")
    if len(added) > 20:
        print(f"  ... and {len(added) - 20} more")
if removed:
    print("--- removed files ---")
    for p in head(removed):
        print(f"  - {p}")
    if len(removed) > 20:
        print(f"  ... and {len(removed) - 20} more")
PYEOF
}

case "${1:-}" in
  diff)
    shift
    diff_snapshots "$@"
    ;;
  "")
    printf 'usage: update-diff.sh <target-dir>\n       update-diff.sh diff <before-snapshot> <after-snapshot>\n' >&2
    exit 2
    ;;
  *)
    snapshot "$1"
    ;;
esac
