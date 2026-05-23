#!/usr/bin/env python3
"""Validate AGENT_CREW_HOST_BRIDGE_COMMAND configuration end-to-end.

This helper checks:
  - whether a bridge command exists in env or stdin arg,
  - whether it is parseable by shell-style tokenization,
  - and whether the executable target is discoverable and executable.

Inputs:
  - optional CLI arg: --command (raw command string to check)
  - optional CLI env var: --env-var (defaults to AGENT_CREW_HOST_BRIDGE_COMMAND)
  - optional --json to emit structured output

Exit codes:
  0 — command is configured and executable
  1 — soft notice (missing/disabled external command; internal handoff still works)
  2 — hard invalid configuration (parse failure, missing executable, non-executable)
"""

from __future__ import annotations

import argparse
import os
import shlex
import shutil
from pathlib import Path
import json
import sys


def _resolve_executable(raw: str):
    """Return (resolved_path, reason, status_key)."""
    # Accepts tokenized executable tokens like /usr/bin/bridge or bridge.
    executable = raw
    if not executable:
        return "", "external bridge command is not set; internal handoff fallback is available.", "missing"

    if "/" in executable:
        path = Path(executable).expanduser()
        if path.is_absolute():
            candidate = path
        else:
            candidate = path.resolve()
        if not candidate.exists():
            return str(candidate), "bridge executable is not found.", "not_found"
        if not candidate.is_file():
            return str(candidate), "bridge executable target is not a file.", "not_file"
        if not os.access(candidate, os.X_OK):
            return str(candidate), "bridge executable is not runnable (no execute permission).", "not_executable"
        return str(candidate), f"bridge executable is available: {candidate}", "ready"

    location = shutil.which(executable)
    if location is None:
        return "", f"bridge executable is not in PATH: {executable}", "not_found"
    return location, f"bridge executable is available: {location}", "ready"


def inspect_bridge_command(command: str) -> dict:
    """Return a structured status payload for diagnostics."""
    payload: dict[str, object] = {
        "schema_version": 1,
        "env_var": "AGENT_CREW_HOST_BRIDGE_COMMAND",
        "command_raw": command,
        "command_argv": [],
        "command_head": "",
        "executable": "",
        "status": "unknown",
        "ready": False,
        "reason": "",
    }

    if not command.strip():
        payload["status"] = "missing"
        payload["reason"] = "external bridge command is not set; internal handoff fallback is available."
        return payload

    try:
        argv = shlex.split(command)
    except ValueError as exc:
        payload["status"] = "parse_error"
        payload["reason"] = f"AGENT_CREW_HOST_BRIDGE_COMMAND is not parseable ({exc})."
        return payload

    if not argv:
        payload["status"] = "empty"
        payload["reason"] = "AGENT_CREW_HOST_BRIDGE_COMMAND split produced no tokens."
        return payload

    executable = argv[0]
    resolved, reason, status = _resolve_executable(executable)
    payload["command_argv"] = argv
    payload["command_head"] = executable
    payload["executable"] = resolved
    payload["status"] = status
    payload["reason"] = reason
    payload["ready"] = status == "ready"
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--command", default=None, help="bridge command to validate directly")
    parser.add_argument("--env-var", default="AGENT_CREW_HOST_BRIDGE_COMMAND", help="environment variable to read when --command is omitted")
    parser.add_argument("--json", action="store_true", help="emit JSON payload")
    args = parser.parse_args()

    command = args.command
    if command is None:
        command = os.environ.get(args.env_var, "").strip()

    result = inspect_bridge_command(command)
    result["env_var"] = args.env_var

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        label = "READY" if result["ready"] else "NOT READY"
        print(f"{label}: {result['status']}")
        print(f"ENV: {result['env_var']}")
        print(f"RAW: {result['command_raw']!r}")
        if result["command_argv"]:
            print(f"ARGV: {result['command_argv']}")
        if result["executable"]:
            print(f"EXEC: {result['executable']}")
        print(f"REASON: {result['reason']}")

    if result["ready"]:
        return 0
    if result["status"] in ("missing", "empty"):
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
