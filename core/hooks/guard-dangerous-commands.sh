#!/bin/bash
# Block dangerous shell commands before execution.
# PreToolUse hook: receives JSON via stdin with tool_input.command.

INPUT=$(cat)

python3 - "$INPUT" <<'PYEOF'
import json
import re
import sys

raw_input = sys.argv[1] if len(sys.argv) > 1 else ""

try:
    data = json.loads(raw_input)
except Exception:
    sys.exit(0)

tool_name = data.get("tool_name", "")
tool_input = data.get("tool_input", {})

if tool_name != "Bash":
    sys.exit(0)

command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
if not command:
    sys.exit(0)

DANGEROUS_PATTERNS = [
    r"rm\s+-rf\s+/",
    r"rm\s+-rf\s+~",
    r"rm\s+-rf\s+\$HOME",
    r":\(\)\s*\{.*:\|:.*\}",
    r"\bmkfs\b",
    r"\bdd\b.*\bif=",
    r">\s*/dev/sd",
]

for pattern in DANGEROUS_PATTERNS:
    if re.search(pattern, command):
        block_output = {
            "decision": "block",
            "reason": (
                f"[agent-crew] Dangerous command pattern detected.\n\n"
                f"Matched pattern: {pattern}\n"
                f"Command: {command}\n\n"
                "Explicit user approval is required before running this command."
            )
        }
        print(json.dumps(block_output))
        sys.exit(0)

sys.exit(0)
PYEOF
