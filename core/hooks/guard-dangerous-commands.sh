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
    ("destructive-delete", r"\brm\s+-[A-Za-z]*(?:r[A-Za-z]*f|f[A-Za-z]*r)[A-Za-z]*\s+/(?:\s|$)"),
    ("destructive-delete", r"\brm\s+-[A-Za-z]*(?:r[A-Za-z]*f|f[A-Za-z]*r)[A-Za-z]*\s+~(?:\s|$|/)"),
    ("destructive-delete", r"\brm\s+-[A-Za-z]*(?:r[A-Za-z]*f|f[A-Za-z]*r)[A-Za-z]*\s+[\"']?\$\{?HOME\}?[\"']?(?:\s|$|/)"),
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

def normalize_command(value):
    return " ".join(str(value or "").split())

def load_approval(kind, command):
    try:
        data = json.loads(approval_file.read_text(encoding="utf-8"))
    except Exception:
        return (False, "missing_or_invalid_approval")

    if not isinstance(data, dict) or data.get("approved") is not True:
        return (False, "approval_not_true")

    approved_kind = data.get("kind")
    if approved_kind and approved_kind != kind:
        return (False, "approval_kind_mismatch")

    if normalize_command(data.get("command")) != normalize_command(command):
        return (False, "approval_command_mismatch")

    expires_at = data.get("expires_at")
    if not expires_at:
        return (False, "approval_missing_expiry")
    try:
        expiry = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
        if expiry <= datetime.now(timezone.utc):
            return (False, "approval_expired")
    except Exception:
        return (False, "approval_invalid_expiry")

    return (True, "approval_matched")

def consume_approval():
    try:
        approval_file.unlink()
    except FileNotFoundError:
        pass
    except Exception:
        pass

for kind, pattern in DANGEROUS_PATTERNS:
    if re.search(pattern, command):
        approved, approval_reason = load_approval(kind, command)
        audit({
            "decision": "allow" if approved else "block",
            "kind": kind,
            "pattern": pattern,
            "command": command,
            "tool_name": tool_name,
            "approved": approved,
            "approval_reason": approval_reason,
            "approval_file": str(approval_file) if approval_file.exists() else "",
        })
        if approved:
            consume_approval()
            sys.exit(0)
        block_output = {
            "decision": "block",
            "reason": (
                f"[agent-crew] Dangerous command pattern detected.\n\n"
                f"Kind: {kind}\n"
                f"Matched pattern: {pattern}\n"
                f"Command: {command}\n\n"
                "Deterministic approval is required before running this command. "
                f"Write a command-bound JSON approval to {approval_file} only from an approved orchestrator path."
            )
        }
        print(json.dumps(block_output), file=sys.stderr)
        sys.exit(2)

sys.exit(0)
PYEOF
