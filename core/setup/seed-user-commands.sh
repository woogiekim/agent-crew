#!/usr/bin/env bash
# seed-user-commands.sh — provenance-tracked seeding for shipped user commands.
#
# Why this exists
#   `core/user/commands/*.md` is a seed layer: the framework ships a starting
#   copy, the user owns the installed file. The original `copy-if-absent` rule
#   kept the second half of that promise but broke the first — once a file
#   existed, no source improvement ever reached the machine again, even when
#   the installed copy was still byte-identical to what the framework itself
#   had written.
#
#   The missing piece was provenance. This script records the sha256 of every
#   file it writes into `<manifest>`. On a later run the installed file is
#   classified as:
#
#     absent        → seed it, record the hash
#     pristine      → its hash still matches what we wrote (or it already
#                     equals the current source). Framework-owned content, so
#                     refresh it and record the new hash.
#     user-owned    → its hash matches neither the manifest nor the source.
#                     The user edited it. NEVER written. Divergence is
#                     reported so the operator can hand-merge.
#
#   A file with no manifest entry whose content differs from the source is
#   treated as user-owned. That is deliberately conservative: installs made
#   before this manifest existed are assumed to be the user's, so the first
#   run after upgrading can only advise, never overwrite.
#
# Usage:
#   seed-user-commands.sh <source-user-commands-dir> <user-commands-dir> [manifest]
#
#   manifest defaults to
#     ${AGENT_CREW_HOME}/system/seed-manifest/commands.json
#
# Exit codes:
#   0 — success (regardless of how many files were seeded, refreshed, or kept)
#
# Idempotency:
#   With an unchanged source tree, a second run writes nothing — not the
#   command files and not the manifest.
#
# Policy:
#   - NEVER overwrites a user-edited file.
#   - NEVER deletes anything from the user layer.
#
# See also:
#   core/setup/seed-skill-templates.sh — the copy-if-absent precedent
#   core/commands/update.md            — asset category contract

set -u

AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
TAG="${AGENT_CREW_SEED_TAG:-crew:update}"

SOURCE_DIR="${1:-}"
DEST_DIR="${2:-${AGENT_CREW_HOME}/user/commands}"
MANIFEST="${3:-${AGENT_CREW_HOME}/system/seed-manifest/commands.json}"

if [ -z "${SOURCE_DIR}" ] || [ ! -d "${SOURCE_DIR}" ]; then
  exit 0
fi

mkdir -p "${DEST_DIR}" "$(dirname "${MANIFEST}")"

python3 - "${SOURCE_DIR}" "${DEST_DIR}" "${MANIFEST}" "${TAG}" <<'PYEOF'
import hashlib
import json
import shutil
import sys
from pathlib import Path

source_dir = Path(sys.argv[1])
dest_dir = Path(sys.argv[2])
manifest_path = Path(sys.argv[3])
tag = sys.argv[4]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


try:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        manifest = {}
except Exception:
    manifest = {}

seeded = refreshed = preserved = diverged = 0
updated = dict(manifest)

for source in sorted(source_dir.glob("*.md")):
    name = source.name
    if name == "README.md":
        continue

    installed = dest_dir / name
    source_hash = sha256(source)

    if not installed.is_file():
        shutil.copyfile(source, installed)
        updated[name] = source_hash
        print(f"[{tag}] seeded user command: {name}")
        seeded += 1
        continue

    installed_hash = sha256(installed)
    recorded = manifest.get(name)

    if installed_hash == source_hash:
        # Already current. Adopt it as framework-written so a later source
        # change can refresh it.
        updated[name] = source_hash
        preserved += 1
        continue

    if recorded == installed_hash:
        shutil.copyfile(source, installed)
        updated[name] = source_hash
        print(f"[{tag}] refreshed pristine user command: {name}")
        refreshed += 1
        continue

    print(
        f"[{tag}] user command {name} diverged from source; "
        f"crew:update will not overwrite it — compare {installed} against {source}"
    )
    diverged += 1

content = json.dumps(updated, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
if not manifest_path.exists() or manifest_path.read_text(encoding="utf-8") != content:
    manifest_path.write_text(content, encoding="utf-8")

print(
    f"[{tag}] user commands: seeded={seeded} refreshed={refreshed} "
    f"current={preserved} diverged={diverged}"
)
PYEOF

exit 0
