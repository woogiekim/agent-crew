#!/bin/bash
# auto-route.sh - adapt explicit agent-crew command invocations to host context.

PAYLOAD_FILE="$(mktemp "${TMPDIR:-/tmp}/agent-crew-auto-route.XXXXXX")"
trap 'rm -f "${PAYLOAD_FILE}"' EXIT
HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
. "${HOOK_DIR}/read-hook-input.sh"
read_agent_crew_hook_input >"${PAYLOAD_FILE}" || true

python3 - "$PAYLOAD_FILE" <<'PYEOF'
import json
import re
import sys
import os
from pathlib import Path

raw_input = ""
if len(sys.argv) > 1:
    try:
        raw_input = Path(sys.argv[1]).read_text(encoding="utf-8")
    except Exception:
        sys.exit(0)

def _env_flag(name):
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


if _env_flag("AGENT_CREW_AUTO_ROUTE_DISABLED") or _env_flag("AGENT_CREW_HOST_BRIDGE_ACTIVE"):
    sys.exit(0)

try:
    data = json.loads(raw_input)
    prompt = data.get("prompt", "")
except Exception:
    sys.exit(0)

def _routing_view(text: str, limit: int = 65536) -> str:
    value = str(text)
    if len(value) <= limit:
        return value
    half = limit // 2
    return (
        value[:half]
        + "\n...[agent-crew auto-route omitted middle for hook classification]...\n"
        + value[-half:]
    )

prompt = _routing_view(prompt)

if prompt.startswith("/"):
    sys.exit(0)

if not prompt.strip():
    sys.exit(0)

COMMAND_PAT = (
    r"^\s*(?:[-*]\s*)?(?P<command>\$?(?:crew|ac):(?P<intent>"
    r"setup|run|status|cost|agent-maker|agent|smm|sessions|interact|"
    r"sync-instructions|telemetry|update|evolve|parity-check|relay"
    r"))(?:\s+(?P<args>.*))?$"
)
command_match = re.match(COMMAND_PAT, prompt, re.IGNORECASE | re.DOTALL)
if command_match:
    command = command_match.group("command").lower()
    intent = command_match.group("intent").lower()
    args = (command_match.group("args") or "").strip()

    command_file_by_intent = {
        "setup": "setup.md",
        "run": "run.md",
        "status": "status.md",
        "cost": "cost.md",
        "agent-maker": "agent-maker.md",
        "agent": "agent.md",
        "smm": "smm.md",
        "sessions": "sessions.md",
        "interact": "interact.md",
        "sync-instructions": "sync-instructions.md",
        "telemetry": "telemetry.md",
        "update": "update.md",
        "evolve": "evolve.md",
        "parity-check": "parity-check.md",
        "relay": "relay.md",
    }
    command_file = command_file_by_intent.get(intent, "run.md")

    if intent == "run":
        args_note = (
            f"Command arguments detected: {args}"
            if args
            else "No command arguments were provided. Follow Step 1 of the command definition and ask for the task description through the host structured input UI."
        )
        intent_rules = """- Follow the command definition step-by-step, including mandatory requirements collection.
- Delegate execution to supervisor as defined by the command.
- Do NOT replace the workflow with "standard verification", CI, linting, or a direct shell command."""
    elif intent == "setup":
        args_note = "No task description is needed. Initialize the current project exactly as the setup command defines."
        intent_rules = """- Follow the setup command definition step-by-step.
- Do NOT inspect repository build files, Gradle/Kotlin configuration, package manifests, or CI files before executing setup.
- Run the host adapter setup flow and initialize agent-crew state as defined by the command."""
    else:
        args_note = (
            f"Command arguments detected: {args}"
            if args
            else "No command arguments were provided."
        )
        intent_rules = """- Follow the referenced command definition step-by-step.
- Do NOT substitute a host-default action or generic project inspection."""

    wrapper_note = ""
    if command.startswith("$crew:"):
        wrapper_note = f"""
Codex wrapper invocation:
  Load Skill("{command[1:]}") before executing the mapped workflow intent.
  Treat text after {command} as command arguments, not as a request to review the wrapper itself.
"""

    directive = f"""[agent-crew] COMMAND — explicit {command} invocation detected.

The user is invoking the agent-crew workflow command. Do NOT reinterpret this as
a request to inspect the repository, run generic verification, CI, linting, or
any host-default task.

Immediate action:
  Execute the workflow defined in ~/.agent-crew/commands/{command_file}.
{wrapper_note}

{args_note}

Execution rules:
- Treat `{command}` as a command invocation, not natural language.
{intent_rules}"""

    output = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": directive,
        }
    }

    print(json.dumps(output, ensure_ascii=True))
    sys.exit(0)

# Ordinary natural-language input must not cross the execution boundary from a
# lifecycle hook. The hook only adapts explicit agent-crew commands; choosing
# crew:agent vs crew:run belongs to the user's command, not hidden routing.
sys.exit(0)

PYEOF
