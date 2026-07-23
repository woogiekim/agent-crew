#!/usr/bin/env python3
"""Remove blocking global Codex hooks when project hooks are active.

Inputs:
  --global-hooks PATH   Codex global hooks.json, usually ~/.codex/hooks.json.
  --project-hooks PATH  Project-local hooks.json, usually .codex/hooks.json.
  --agent-crew-home PATH  agent-crew install root, usually ~/.agent-crew.

Outputs:
  JSON or quiet text summary. The script removes hook commands that point at
  known agent-crew managed scripts under {agent_crew_home}/hooks/. It also
  removes known Orca Codex global hooks because they can time out independently
  of project-local agent-crew hooks and can remain visible in lifecycle events
  such as Stop after a project-local update.

Exit codes:
  0 - completed or skipped safely.
  2 - malformed arguments or an unexpected write failure.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


MANAGED_HOOKS = {
    "agent-diff-post.sh",
    "agent-diff-pre.sh",
    "auto-issue-report.sh",
    "auto-route.sh",
    "context-guard.sh",
    "direct-edit-guard.sh",
    "guard-dangerous-commands.sh",
    "mnemos-capture-guard.sh",
    "normalize-task-guard.sh",
    "post-tool-use-dispatcher.sh",
    "route-directive-guard.sh",
    "supervisor-progress-guard.sh",
    "tool-event-recorder.sh",
    "tracker-mutation-guard.sh",
    "verify-rules.sh",
}

ORCA_CODEX_HOOK = "/.orca/agent-hooks/codex-hook.sh"


def _same_path(a: Path, b: Path) -> bool:
    try:
        return a.expanduser().resolve() == b.expanduser().resolve()
    except OSError:
        return a.expanduser().absolute() == b.expanduser().absolute()


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _is_managed_hook(entry: Any, agent_crew_home: Path) -> bool:
    if not isinstance(entry, dict):
        return False

    command = entry.get("command")
    if not isinstance(command, str):
        return False

    unquoted = command.replace("'", "").replace('"', "")
    hook_root = agent_crew_home.expanduser() / "hooks"
    return any(str(hook_root / basename) in unquoted for basename in MANAGED_HOOKS)


def _is_known_blocking_global_hook(entry: Any, event_name: str) -> bool:
    del event_name
    if not isinstance(entry, dict):
        return False

    command = entry.get("command")
    return isinstance(command, str) and ORCA_CODEX_HOOK in command


def _prune_hook_blocks(blocks: Any, agent_crew_home: Path, event_name: str) -> tuple[list[Any], int]:
    if not isinstance(blocks, list):
        return blocks, 0

    pruned_blocks: list[Any] = []
    removed = 0
    for block in blocks:
        if not isinstance(block, dict) or not isinstance(block.get("hooks"), list):
            pruned_blocks.append(block)
            continue

        hooks = []
        for hook in block["hooks"]:
            if _is_managed_hook(hook, agent_crew_home) or _is_known_blocking_global_hook(
                hook,
                event_name,
            ):
                removed += 1
            else:
                hooks.append(hook)

        if hooks:
            updated = dict(block)
            updated["hooks"] = hooks
            pruned_blocks.append(updated)

    return pruned_blocks, removed


def prune(global_hooks: Path, project_hooks: Path, agent_crew_home: Path) -> dict[str, Any]:
    global_hooks = global_hooks.expanduser()
    project_hooks = project_hooks.expanduser()
    agent_crew_home = agent_crew_home.expanduser()

    if _same_path(global_hooks, project_hooks):
        return {"changed": False, "removed": 0, "reason": "same_path"}
    if not global_hooks.exists():
        return {"changed": False, "removed": 0, "reason": "global_missing"}
    if not project_hooks.exists():
        return {"changed": False, "removed": 0, "reason": "project_hooks_missing"}

    payload = _read_json(global_hooks)
    if payload is None:
        return {"changed": False, "removed": 0, "reason": "global_malformed"}

    hooks = payload.get("hooks")
    if not isinstance(hooks, dict):
        return {"changed": False, "removed": 0, "reason": "no_hooks_object"}

    updated_hooks: dict[str, Any] = {}
    removed_total = 0
    for event_name, blocks in hooks.items():
        pruned_blocks, removed = _prune_hook_blocks(blocks, agent_crew_home, event_name)
        removed_total += removed
        if isinstance(pruned_blocks, list) and not pruned_blocks:
            continue
        updated_hooks[event_name] = pruned_blocks

    if removed_total == 0:
        return {"changed": False, "removed": 0, "reason": "no_managed_hooks"}

    updated = dict(payload)
    if updated_hooks:
        updated["hooks"] = updated_hooks
    else:
        updated.pop("hooks", None)

    try:
        global_hooks.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"failed to write {global_hooks}: {exc}") from exc

    return {"changed": True, "removed": removed_total, "reason": "pruned"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--global-hooks", required=True)
    parser.add_argument("--project-hooks", required=True)
    parser.add_argument("--agent-crew-home", required=True)
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)

    try:
        result = prune(Path(args.global_hooks), Path(args.project_hooks), Path(args.agent_crew_home))
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    elif result["changed"]:
        print(
            "pruned managed Codex global hooks: "
            f"removed={result['removed']} path={Path(args.global_hooks).expanduser()}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
