#!/usr/bin/env python3
"""Check Claude adapter asset and hook performance budgets."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


DEFAULT_AGENT_CREW_KB = 4096
DEFAULT_AGENTS_KB = 2048
DEFAULT_FILE_COUNT = 400
DEFAULT_LARGEST_AGENT_KB = 96
DEFAULT_HOOK_TIMEOUT_SECONDS = 75


def dir_stats(path: Path) -> dict[str, Any]:
    files = [p for p in path.rglob("*") if p.is_file()] if path.is_dir() else []
    total_bytes = sum(p.stat().st_size for p in files)
    largest = max(files, key=lambda p: p.stat().st_size, default=None)
    return {
        "path": str(path),
        "exists": path.is_dir(),
        "files": len(files),
        "bytes": total_bytes,
        "kilobytes": round(total_bytes / 1024, 1),
        "largest_file": str(largest) if largest else "",
        "largest_file_kilobytes": round(largest.stat().st_size / 1024, 1) if largest else 0,
    }


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def iter_hook_entries(settings: dict[str, Any]) -> list[dict[str, Any]]:
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return []

    entries: list[dict[str, Any]] = []
    for event_name, blocks in hooks.items():
        if not isinstance(blocks, list):
            continue
        for block in blocks:
            if not isinstance(block, dict):
                continue
            matcher = str(block.get("matcher") or "")
            for hook in block.get("hooks") or []:
                if not isinstance(hook, dict):
                    continue
                command = str(hook.get("command") or "")
                if "agent-crew" not in command:
                    continue
                timeout = hook.get("timeout")
                entries.append({
                    "event": event_name,
                    "matcher": matcher,
                    "command": command,
                    "timeout_seconds": int(timeout) if isinstance(timeout, int) else 0,
                })
    return entries


def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    claude_dir = Path(args.claude_dir).expanduser()
    agent_crew = dir_stats(claude_dir / "agent-crew")
    agents = dir_stats(claude_dir / "agents")
    settings = load_json(claude_dir / "settings.json")
    hook_entries = iter_hook_entries(settings)
    hook_timeout_total = sum(entry["timeout_seconds"] for entry in hook_entries)

    checks = [
        {
            "name": "agent_crew_size",
            "passed": agent_crew["kilobytes"] <= args.agent_crew_kb,
            "detail": f"{agent_crew['kilobytes']}KB <= {args.agent_crew_kb}KB",
        },
        {
            "name": "agents_size",
            "passed": agents["kilobytes"] <= args.agents_kb,
            "detail": f"{agents['kilobytes']}KB <= {args.agents_kb}KB",
        },
        {
            "name": "file_count",
            "passed": agent_crew["files"] + agents["files"] <= args.file_count,
            "detail": f"{agent_crew['files'] + agents['files']} <= {args.file_count}",
        },
        {
            "name": "largest_agent",
            "passed": agents["largest_file_kilobytes"] <= args.largest_agent_kb,
            "detail": f"{agents['largest_file_kilobytes']}KB <= {args.largest_agent_kb}KB",
        },
        {
            "name": "hook_timeout_total",
            "passed": hook_timeout_total <= args.hook_timeout_seconds,
            "detail": f"{hook_timeout_total}s <= {args.hook_timeout_seconds}s",
        },
    ]
    passed = all(check["passed"] for check in checks)
    return {
        "schema_version": 1,
        "status": "pass" if passed else "warn",
        "claude_dir": str(claude_dir),
        "budgets": {
            "agent_crew_kb": args.agent_crew_kb,
            "agents_kb": args.agents_kb,
            "file_count": args.file_count,
            "largest_agent_kb": args.largest_agent_kb,
            "hook_timeout_seconds": args.hook_timeout_seconds,
        },
        "agent_crew": agent_crew,
        "agents": agents,
        "hooks": {
            "count": len(hook_entries),
            "timeout_seconds_total": hook_timeout_total,
            "entries": hook_entries,
        },
        "checks": checks,
        "summary": (
            f"agent-crew={agent_crew['kilobytes']}KB, agents={agents['kilobytes']}KB, "
            f"files={agent_crew['files'] + agents['files']}, "
            f"hook_timeout_total={hook_timeout_total}s"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claude-dir", default=os.environ.get("CLAUDE_DIR", str(Path.home() / ".claude")))
    parser.add_argument("--agent-crew-kb", type=int, default=int(os.environ.get("AGENT_CREW_CLAUDE_AGENT_CREW_BUDGET_KB", DEFAULT_AGENT_CREW_KB)))
    parser.add_argument("--agents-kb", type=int, default=int(os.environ.get("AGENT_CREW_CLAUDE_AGENTS_BUDGET_KB", DEFAULT_AGENTS_KB)))
    parser.add_argument("--file-count", type=int, default=int(os.environ.get("AGENT_CREW_CLAUDE_FILE_COUNT_BUDGET", DEFAULT_FILE_COUNT)))
    parser.add_argument("--largest-agent-kb", type=int, default=int(os.environ.get("AGENT_CREW_CLAUDE_LARGEST_AGENT_BUDGET_KB", DEFAULT_LARGEST_AGENT_KB)))
    parser.add_argument("--hook-timeout-seconds", type=int, default=int(os.environ.get("AGENT_CREW_CLAUDE_HOOK_TIMEOUT_BUDGET_SECONDS", DEFAULT_HOOK_TIMEOUT_SECONDS)))
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()

    payload = evaluate(args)
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(("PASS" if payload["status"] == "pass" else "WARN") + f": claude performance budgets - {payload['summary']}")
        for check in payload["checks"]:
            if not check["passed"]:
                print(f"- {check['name']}: {check['detail']}")
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
