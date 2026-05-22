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
from datetime import datetime, timedelta, timezone
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

FORBIDDEN_PATTERNS = [
    ("force-push", r"\bgit\s+push\b(?=[^;&|\n]*\s(?:--force(?:-with-lease)?|-f)\b)"),
    ("sudo", r"(^|[;&|]\s*)sudo(?:\s|$)"),
    ("credential-access", r"(^|[;&|]\s*)gh\s+auth\s+token\b"),
    ("credential-access", r"(^|[;&|]\s*)security\s+find-(?:generic|internet)-password\b"),
    ("credential-access", r"(^|[;&|]\s*)op\s+item\s+get\b"),
    ("credential-access", r"(^|[;&|]\s*)pass\s+show\b"),
    ("credential-access", r"(^|[;&|]\s*)(?:cat|less|sed|awk|grep|rg)\b[^;&|\n]*(?:~/)?(?:\.ssh/|\.git-credentials|\.aws/credentials|\.config/gh/hosts\.yml|id_rsa|id_ed25519)"),
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
consumed_approval_file = Path(home) / "approvals" / "dangerous-commands.consumed"

def normalize_command(value):
    return " ".join(str(value or "").split())

def validate_approval_data(data, kind, command):
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

def validate_consumed_approval(data, kind, command):
    valid, reason = validate_approval_data(data, kind, command)
    if not valid:
        return (False, reason)

    try:
        uses_remaining = int(data.get("duplicate_uses_remaining", 0))
    except Exception:
        return (False, "consumed_approval_invalid_uses")
    if uses_remaining <= 0:
        return (False, "consumed_approval_exhausted")

    grace_until = data.get("duplicate_grace_until")
    if not grace_until:
        return (False, "consumed_approval_missing_grace")
    try:
        grace_expiry = datetime.fromisoformat(str(grace_until).replace("Z", "+00:00"))
        if grace_expiry <= datetime.now(timezone.utc):
            return (False, "consumed_approval_grace_expired")
    except Exception:
        return (False, "consumed_approval_invalid_grace")

    return (True, "approval_duplicate_matched")

def load_approval(kind, command):
    try:
        data = json.loads(approval_file.read_text(encoding="utf-8"))
        valid, reason = validate_approval_data(data, kind, command)
        if valid:
            return (True, reason, data, "fresh")
        return (False, reason, None, "fresh")
    except Exception:
        pass

    try:
        data = json.loads(consumed_approval_file.read_text(encoding="utf-8"))
        valid, reason = validate_consumed_approval(data, kind, command)
        if valid:
            return (True, reason, data, "consumed")
        return (False, reason, None, "consumed")
    except Exception:
        return (False, "missing_or_invalid_approval", None, "missing")

def consume_approval(data, source):
    if source == "fresh":
        consumed = dict(data or {})
        consumed["duplicate_uses_remaining"] = 1
        consumed["duplicate_grace_until"] = (
            datetime.now(timezone.utc) + timedelta(seconds=10)
        ).isoformat()
        try:
            consumed_approval_file.parent.mkdir(parents=True, exist_ok=True)
            consumed_approval_file.write_text(
                json.dumps(consumed, ensure_ascii=False, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        except Exception:
            pass

        try:
            approval_file.unlink()
        except FileNotFoundError:
            pass
        except Exception:
            pass
        return

    if source == "consumed":
        consumed = dict(data or {})
        try:
            consumed["duplicate_uses_remaining"] = int(
                consumed.get("duplicate_uses_remaining", 0)
            ) - 1
        except Exception:
            consumed["duplicate_uses_remaining"] = 0

        if consumed["duplicate_uses_remaining"] <= 0:
            try:
                consumed_approval_file.unlink()
            except FileNotFoundError:
                pass
            except Exception:
                pass
            return

        try:
            consumed_approval_file.write_text(
                json.dumps(consumed, ensure_ascii=False, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        except Exception:
            pass
        return

    try:
        approval_file.unlink()
    except FileNotFoundError:
        pass
    except Exception:
        pass

def mask_quoted_strings(value):
    """Replace shell-quoted payload text with spaces before simple command scans.

    The hook guards command execution, not documentation or JSON data being
    written by the orchestrator. Without this, a safe approval-marker write that
    contains {"command":"git push ..."} is blocked before the actual guarded
    command can consume that marker.
    """
    out = []
    quote = None
    escaped = False
    for ch in value:
        if quote:
            if escaped:
                out.append(" ")
                escaped = False
                continue
            if quote == '"' and ch == "\\":
                out.append(" ")
                escaped = True
                continue
            if ch == quote:
                out.append(ch)
                quote = None
            else:
                out.append(" ")
            continue

        if ch in ("'", '"'):
            out.append(ch)
            quote = ch
        else:
            out.append(ch)
    return "".join(out)

def runs_shell_evaluator(value):
    """Return true when quoted text may itself be executed by a shell."""
    return bool(
        re.search(r"(^|[;&|]\s*)(?:env\s+[^;&|]*\s+)?(?:bash|sh|zsh)\s+-[A-Za-z]*c[A-Za-z]*(?:\s|$)", value)
        or re.search(r"(^|[;&|]\s*)eval(?:\s|$)", value)
    )

def command_haystack(kind, value):
    if kind in (
        "push",
        "merge",
        "deploy",
        "force-push",
        "sudo",
        "credential-access",
    ) and not runs_shell_evaluator(value):
        return mask_quoted_strings(value)
    return value

def block_with_reason(block_output):
    print(json.dumps(block_output), file=sys.stderr, flush=True)
    sys.exit(2)

for kind, pattern in FORBIDDEN_PATTERNS:
    haystack = command_haystack(kind, command)
    if re.search(pattern, haystack):
        audit({
            "decision": "block",
            "kind": kind,
            "pattern": pattern,
            "command": command,
            "tool_name": tool_name,
            "approved": False,
            "approval_reason": "forbidden_command",
            "approval_source": "policy",
            "approval_file": "",
        })
        block_output = {
            "decision": "block",
            "reason": (
                f"[agent-crew] Forbidden command pattern detected.\n\n"
                f"Kind: {kind}\n"
                f"Matched pattern: {pattern}\n"
                f"Command: {command}\n\n"
                "This command is denied by policy and cannot be approved with "
                "a dangerous-command marker."
            )
        }
        block_with_reason(block_output)

for kind, pattern in DANGEROUS_PATTERNS:
    haystack = command_haystack(kind, command)
    if re.search(pattern, haystack):
        approved, approval_reason, approval_data, approval_source = load_approval(kind, command)
        audit({
            "decision": "allow" if approved else "block",
            "kind": kind,
            "pattern": pattern,
            "command": command,
            "tool_name": tool_name,
            "approved": approved,
            "approval_reason": approval_reason,
            "approval_source": approval_source,
            "approval_file": str(approval_file) if approval_file.exists() else "",
        })
        if approved:
            consume_approval(approval_data, approval_source)
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
        block_with_reason(block_output)

sys.exit(0)
PYEOF
