#!/bin/bash
# Warn when delegated-agent prompts appear to inline large file contents.

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

if tool_name not in ("Agent", "spawn_agent"):
    sys.exit(0)

prompt = ""
if isinstance(tool_input, dict):
    prompt = (
        tool_input.get("prompt")
        or tool_input.get("message")
        or tool_input.get("description")
        or ""
    )

if not prompt:
    sys.exit(0)

warnings = []
prompt_len = len(prompt)

if prompt_len > 2000:
    warnings.append(
        f"[context-guard] Agent prompt is {prompt_len} characters. "
        "Check whether file contents are being inlined."
    )

code_blocks = re.findall(r"```[\s\S]{500,}?```", prompt)
if code_blocks:
    warnings.append(
        f"[context-guard] Detected {len(code_blocks)} code block(s) over 500 characters. "
        "Prefer passing file paths and letting the agent read files directly."
    )

if warnings:
    print("\n".join(warnings), file=sys.stderr)

sys.exit(0)
PYEOF
