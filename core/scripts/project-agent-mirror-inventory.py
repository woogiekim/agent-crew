#!/usr/bin/env python3
"""Inventory legacy project agent mirrors and emit a deletion-free cleanup manifest."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path


SYSTEM_MARKERS = (
    "This is a Codex adapter bootstrap for the agent-crew system agent.",
    "Agent-crew system agent:",
)
USER_MARKER = "# This is a Codex adapter bootstrap for an agent-crew user agent."
SKIP_DIRECTORIES = {
    ".git",
    ".gradle",
    ".idea",
    ".next",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "out",
    "target",
}
QUARANTINE_ACTIONS = {
    "quarantine_after_global",
    "quarantine_duplicate",
    "quarantine_managed",
    "quarantine_stale_managed",
}


class GitTracker:
    def __init__(self) -> None:
        self.directory_roots: dict[Path, Path | None] = {}
        self.tracked_by_root: dict[Path, set[str] | None] = {}

    def status(self, path: Path) -> bool | None:
        directory = path.parent
        if directory not in self.directory_roots:
            try:
                result = subprocess.run(
                    ["git", "-C", str(directory), "rev-parse", "--show-toplevel"],
                    capture_output=True,
                    check=False,
                    text=True,
                )
            except OSError:
                return None
            self.directory_roots[directory] = (
                Path(result.stdout.strip()) if result.returncode == 0 else None
            )

        root = self.directory_roots[directory]
        if root is None:
            return False
        if root not in self.tracked_by_root:
            try:
                result = subprocess.run(
                    ["git", "-C", str(root), "ls-files", "-z"],
                    capture_output=True,
                    check=False,
                )
            except OSError:
                self.tracked_by_root[root] = None
            else:
                if result.returncode != 0:
                    self.tracked_by_root[root] = None
                else:
                    self.tracked_by_root[root] = set(
                        result.stdout.decode("utf-8", errors="surrogateescape").split("\0")
                    )

        tracked = self.tracked_by_root[root]
        if tracked is None:
            return None
        try:
            relative = str(path.relative_to(root))
        except ValueError:
            return None
        return relative in tracked


def parse_agent_name(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if match:
        for line in match.group(1).splitlines():
            key_value = re.match(r"^(\w[\w_-]*):\s*(.*)", line)
            if key_value and key_value.group(1) == "name":
                return key_value.group(2).strip().strip("\"'") or path.stem
    return path.stem


def codex_agent_name(name: str) -> str:
    return re.sub(r"[^\w-]", "-", name.lower()).strip("-") or "unknown"


def without_user_marker(content: bytes) -> bytes:
    marker = (USER_MARKER + "\n").encode()
    return content[len(marker) :] if content.startswith(marker) else content


def markdown_sources(agent_crew_home: Path, claude_dir: Path) -> dict[str, list[tuple[Path, bytes]]]:
    sources: dict[str, list[tuple[Path, bytes]]] = defaultdict(list)
    for directory in (
        agent_crew_home / "system" / "agents",
        agent_crew_home / "user" / "agents",
        claude_dir / "agents",
    ):
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.md")):
            if path.name.lower() == "readme.md":
                continue
            sources[path.name].append((path, path.read_bytes()))
    return sources


def source_codex_names(directory: Path) -> set[str]:
    if not directory.is_dir():
        return set()
    names = set()
    for path in sorted(directory.glob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        names.add(codex_agent_name(parse_agent_name(path)) + ".toml")
    return names


def classify_codex(
    path: Path,
    codex_home: Path,
    known_system_names: set[str],
    known_user_names: set[str],
) -> tuple[str, str, str | None]:
    content = path.read_bytes()
    text = content.decode("utf-8", errors="replace")
    global_path = codex_home / "agents" / path.name
    global_content = global_path.read_bytes() if global_path.is_file() else None
    system_managed = any(marker in text for marker in SYSTEM_MARKERS)
    user_managed = text.startswith(USER_MARKER + "\n")

    if system_managed:
        if global_content is None:
            if path.name in known_system_names:
                return "block_missing_global", "current system agent has no global replacement", None
            return "quarantine_stale_managed", "managed system agent was removed from the current source", None
        return "quarantine_managed", "agent-crew system marker and global replacement found", str(global_path)

    if user_managed:
        if global_content is None:
            return "block_missing_global", "managed user agent has no global replacement", None
        return "quarantine_after_global", "managed user agent has a global replacement", str(global_path)

    if global_content is not None:
        if content == global_content or content == without_user_marker(global_content):
            return "quarantine_after_global", "project TOML duplicates the global agent", str(global_path)
        return "preserve_project_override", "same-name global agent exists but project content differs", str(global_path)

    if path.name in known_user_names:
        return "block_missing_global", "user agent source exists but global Codex TOML is missing", None

    return "preserve_project_override", "unmarked project-owned Codex agent", None


def classify_markdown(
    path: Path,
    kind: str,
    sources: dict[str, list[tuple[Path, bytes]]],
) -> tuple[str, str, str | None]:
    content = path.read_bytes()
    candidates = sources.get(path.name, [])
    for source_path, source_content in candidates:
        if content == source_content:
            action = "quarantine_duplicate" if kind == "legacy-agent-crew" else "quarantine_after_global"
            return action, "project Markdown duplicates a global source", str(source_path)

    if candidates:
        return "review_modified_or_stale", "same-name global source exists but content differs", None
    if kind == "legacy-agent-crew":
        return "preserve_legacy_custom", "legacy directory contains a custom agent name", None
    return "preserve_project_override", "project-owned Claude agent", None


def scan(
    roots: list[Path],
    agent_crew_home: Path,
    codex_home: Path,
    claude_dir: Path,
) -> list[dict[str, object]]:
    sources = markdown_sources(agent_crew_home, claude_dir)
    known_system_names = source_codex_names(agent_crew_home / "system" / "agents")
    known_user_names = source_codex_names(agent_crew_home / "user" / "agents")
    git_tracker = GitTracker()
    entries: list[dict[str, object]] = []

    for root in roots:
        if not root.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [name for name in dirnames if name not in SKIP_DIRECTORIES]
            directory = Path(dirpath)
            directory_text = str(directory)
            kind = None
            suffix = None
            if directory_text.endswith("/.codex/agents"):
                kind, suffix = "codex", ".toml"
            elif directory_text.endswith("/.claude/agents"):
                kind, suffix = "claude", ".md"
            elif directory_text.endswith("/.agent-crew/agents"):
                kind, suffix = "legacy-agent-crew", ".md"
            if kind is None:
                continue

            dirnames[:] = []
            for filename in sorted(filenames):
                path = directory / filename
                if path.suffix != suffix or not path.is_file():
                    continue
                if kind == "codex":
                    action, reason, replacement = classify_codex(
                        path,
                        codex_home,
                        known_system_names,
                        known_user_names,
                    )
                else:
                    action, reason, replacement = classify_markdown(path, kind, sources)
                candidate_action = None
                if action in QUARANTINE_ACTIONS:
                    tracked = git_tracker.status(path)
                    if tracked is True:
                        candidate_action = action
                        action = "preserve_tracked"
                        reason = "Git tracked file; cleanup requires a repository-scoped change"
                    elif tracked is None:
                        candidate_action = action
                        action = "preserve_git_unknown"
                        reason = "Git tracking status could not be verified"
                entry: dict[str, object] = {
                    "action": action,
                    "kind": kind,
                    "path": str(path),
                    "reason": reason,
                }
                if replacement:
                    entry["replacement"] = replacement
                if candidate_action:
                    entry["candidate_action"] = candidate_action
                entries.append(entry)

    return sorted(entries, key=lambda entry: str(entry["path"]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", action="append", required=True)
    parser.add_argument("--agent-crew-home", default=str(Path.home() / ".agent-crew"))
    parser.add_argument("--codex-home", default=str(Path.home() / ".codex"))
    parser.add_argument("--claude-dir", default=str(Path.home() / ".claude"))
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    roots = [Path(value).expanduser().resolve() for value in args.root]
    entries = scan(
        roots,
        Path(args.agent_crew_home).expanduser(),
        Path(args.codex_home).expanduser(),
        Path(args.claude_dir).expanduser(),
    )
    summary = Counter(str(entry["action"]) for entry in entries)
    payload = {
        "entries": entries,
        "mode": "dry-run",
        "roots": [str(root) for root in roots],
        "summary": dict(sorted(summary.items())),
        "total": len(entries),
        "version": 1,
    }
    output = Path(args.output).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"DRY_RUN: project agent mirror inventory wrote {len(entries)} entries to {output}")
    for action, count in sorted(summary.items()):
        print(f"{action}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
