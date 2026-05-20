#!/bin/bash
# Block dangerous shell commands before execution.
# PreToolUse hook: receives JSON via stdin with tool_input.command.
#
# Exit codes:
#   0 — allow
#   2 — block; host should cancel the tool call and surface the reason

INPUT=$(cat)

python3 - "$INPUT" <<'PYEOF'
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

raw_input = sys.argv[1] if len(sys.argv) > 1 else ""

try:
    data = json.loads(raw_input)
except Exception:
    sys.exit(0)

tool_name = data.get("tool_name", "")
tool_input = data.get("tool_input", {})

if tool_name not in ("Bash", "shell", "exec_command"):
    sys.exit(0)

command = ""
if isinstance(tool_input, dict):
    command = tool_input.get("command") or tool_input.get("cmd") or ""
if not command:
    sys.exit(0)

DANGEROUS_PATTERNS = [
    ("destructive-delete", r"rm\s+-rf\s+/"),
    ("destructive-delete", r"rm\s+-rf\s+~"),
    ("destructive-delete", r"rm\s+-rf\s+\$HOME"),
    ("fork-bomb", r":\(\)\s*\{.*:\|:.*\}"),
    ("disk-format", r"\bmkfs\b"),
    ("raw-disk-write", r"\bdd\b.*\bif="),
    ("raw-disk-write", r">\s*/dev/sd"),
    ("push", r"\bgit\s+push\b"),
    ("merge", r"\bgit\s+merge\b"),
    ("deploy", r"(^|[;&|]\s*)(./)?deploy(\.sh)?\b"),
    ("deploy", r"\b(npm|pnpm|yarn)\s+run\s+deploy\b"),
]

def audit(event):
    home = os.environ.get("AGENT_CREW_HOME") or os.path.join(os.path.expanduser("~"), ".agent-crew")
    path = os.path.join(home, "audit", "dangerous-commands.jsonl")
    event = dict(event)
    event.setdefault("ts", datetime.now(timezone.utc).isoformat())
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    except Exception:
        pass

home = os.environ.get("AGENT_CREW_HOME") or os.path.join(os.path.expanduser("~"), ".agent-crew")
approval_file = Path(home) / "approvals" / "dangerous-commands.approved"

def file_approved():
    try:
        content = approval_file.read_text(encoding="utf-8").strip()
    except Exception:
        return False
    return content == "APPROVED"

approved = os.environ.get("AGENT_CREW_APPROVED_DANGEROUS") == "1" or file_approved()

for kind, pattern in DANGEROUS_PATTERNS:
    if re.search(pattern, command):
        audit({
            "decision": "allow" if approved else "block",
            "kind": kind,
            "pattern": pattern,
            "command": command,
            "tool_name": tool_name,
            "approved": approved,
            "approval_file": str(approval_file) if approval_file.exists() else "",
        })
        if approved:
            sys.exit(0)
        block_output = {
            "decision": "block",
            "reason": (
                f"[agent-crew] Dangerous command pattern detected.\n\n"
                f"Kind: {kind}\n"
                f"Matched pattern: {pattern}\n"
                f"Command: {command}\n\n"
                "Deterministic approval is required before running this command. "
                f"Write APPROVED to {approval_file} only from an approved orchestrator path."
            )
        }
        print(json.dumps(block_output))
        sys.exit(2)

sys.exit(0)
PYEOF
