#!/usr/bin/env python3
"""Generate path-scoped Git blob fingerprints for legacy project mirrors."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path


EXACT_DESTINATIONS = {
    "adapters/generic/invocation.md": (".agent-crew/invocation.md",),
    "adapters/codex/invocation.md": (".codex/invocation.md",),
    "adapters/codex/template/README.md": (".codex/README.md",),
    "adapters/codex/template/config.toml": (".codex/config.toml",),
}
PREFIX_DESTINATIONS = (
    (
        "core/agents/skills/",
        (".agent-crew/agents/skills/", ".agent-crew/skills/"),
    ),
    ("core/agents/", (".agent-crew/agents/", ".claude/agents/")),
    ("core/commands/", (".agent-crew/commands/",)),
    ("core/hooks/", (".agent-crew/hooks/", ".codex/hooks/")),
    ("adapters/codex/template/agents/", (".codex/agents/",)),
)
HISTORY_PATHS = (
    "core/agents",
    "core/commands",
    "core/hooks",
    "adapters/generic/invocation.md",
    "adapters/codex/invocation.md",
    "adapters/codex/template/README.md",
    "adapters/codex/template/config.toml",
    "adapters/codex/template/agents",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def destinations(source_path: str) -> tuple[str, ...]:
    exact = EXACT_DESTINATIONS.get(source_path)
    if exact is not None:
        return exact
    for prefix, destination_prefixes in PREFIX_DESTINATIONS:
        if source_path.startswith(prefix):
            suffix = source_path[len(prefix) :]
            return tuple(value + suffix for value in destination_prefixes)
    return ()


def historical_blobs(source_root: Path) -> dict[str, list[str]]:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(source_root),
            "log",
            "--all",
            "--pretty=format:",
            "--raw",
            "--no-renames",
            "--no-abbrev",
            "--",
            *HISTORY_PATHS,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git history lookup failed")

    mapped: dict[str, set[str]] = defaultdict(set)
    for line in result.stdout.splitlines():
        if not line.startswith(":") or "\t" not in line:
            continue
        metadata, source_path = line.split("\t", 1)
        fields = metadata.split()
        if len(fields) < 5:
            continue
        blob_sha = fields[3]
        if blob_sha == "0" * 40:
            continue
        for destination in destinations(source_path):
            mapped[destination].add(blob_sha)
    return {
        path: sorted(fingerprints)
        for path, fingerprints in sorted(mapped.items())
        if fingerprints
    }


def atomic_write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def main() -> int:
    args = parse_args()
    source_root = Path(args.source_root).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    paths = historical_blobs(source_root)
    atomic_write(
        output,
        {
            "version": 1,
            "algorithm": "git-blob-sha1",
            "paths": paths,
        },
    )
    print(
        f"project_asset_fingerprints: paths={len(paths)} "
        f"fingerprints={sum(len(values) for values in paths.values())} output={output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
