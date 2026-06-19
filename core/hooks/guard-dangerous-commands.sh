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
        "commit-specialist",
    ) and not runs_shell_evaluator(value):
        return mask_quoted_strings(value)
    return value

def block_with_reason(block_output):
    print(json.dumps(block_output), file=sys.stderr, flush=True)
    sys.exit(2)

def is_git_commit_command(value):
    haystack = command_haystack("commit-specialist", value)
    return bool(re.search(r"(^|[;&|]\s*)(?:env\s+[^;&|\n]*\s+)?git\s+commit\b", haystack))

def normalize_agent_name(value):
    raw = str(value or "").strip().strip("`'\"")
    if not raw:
        return ""

    name = Path(raw).name
    for suffix in (".md", ".toml"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    return name.lower()

def split_specialist_values(value):
    cleaned = str(value or "").strip().strip("[]")
    parts = re.split(r"[,|]", cleaned)
    return [
        part.strip().strip("'\"`")
        for part in parts
        if part.strip().strip("'\"`")
    ]

def configured_project_root():
    value = os.environ.get("AGENT_CREW_PROJECT_ROOT", "").strip()
    if value:
        return Path(value).expanduser()
    if isinstance(tool_input, dict):
        cwd = str(tool_input.get("cwd") or "").strip()
        if cwd:
            return Path(cwd).expanduser()
    return Path.cwd()

COMMIT_MESSAGE_CAPABILITY = "vcs.commit.message.compose"
COMPLETED_CAPABILITY_STATES = {"completed", "succeeded", "success", "passed", "approved", "done"}
LEGACY_AGENT_CAPABILITIES = {
    "git-committer": [COMMIT_MESSAGE_CAPABILITY],
}

def legacy_commit_capability_provider_paths():
    candidates = []
    project_root = configured_project_root()
    candidates.extend([
        project_root / ".agent-crew" / "agents" / "git-committer.md",
        project_root / ".codex" / "agents" / "git-committer.toml",
    ])

    agent_crew_home = Path(home).expanduser()
    candidates.extend([
        agent_crew_home / "user" / "agents" / "git-committer.md",
        agent_crew_home / "system" / "agents" / "git-committer.md",
        agent_crew_home / "agents" / "git-committer.md",
    ])

    return [str(path) for path in candidates if path.is_file()]

def merge_handler_maps(target, source):
    for capability, selected in source.items():
        target.setdefault(capability, [])
        for handler in selected:
            normalized = normalize_agent_name(handler)
            if normalized and normalized not in target[capability]:
                target[capability].append(normalized)
    return target

def selected_user_agent_values_from_json(payload):
    if not isinstance(payload, dict):
        return []

    values = []
    for key in ("selected_user_agent", "selected_user_agents"):
        value = payload.get(key)
        if value is None:
            continue
        items = value if isinstance(value, list) else [value]
        for item in items:
            values.extend(split_specialist_values(item))
    return values

def legacy_agent_handlers(values):
    handlers = {}
    for agent in values:
        normalized = normalize_agent_name(agent)
        for capability in LEGACY_AGENT_CAPABILITIES.get(normalized, []):
            handlers.setdefault(capability, [])
            if normalized not in handlers[capability]:
                handlers[capability].append(normalized)
    return handlers

def selected_handlers_from_json(payload):
    if not isinstance(payload, dict):
        return {}

    handlers = {}
    raw = payload.get("selected_handlers") or payload.get("selected_handler") or []
    if isinstance(raw, dict):
        raw = [
            {"capability": capability, "handler": handler}
            for capability, handler in raw.items()
        ]
    if not isinstance(raw, list):
        raw = [raw]

    for item in raw:
        capability = ""
        handler_values = []
        if isinstance(item, dict):
            capability = str(item.get("capability") or "").strip()
            handler = item.get("handler") or item.get("handlers") or []
            handler_values = handler if isinstance(handler, list) else [handler]
        else:
            text = str(item or "").strip()
            if "=" in text:
                capability, handler = text.split("=", 1)
                capability = capability.strip()
                handler_values = split_specialist_values(handler)
        if not capability:
            continue
        handlers.setdefault(capability, [])
        for value in handler_values:
            normalized = normalize_agent_name(value)
            if normalized and normalized not in handlers[capability]:
                handlers[capability].append(normalized)
    merge_handler_maps(handlers, legacy_agent_handlers(selected_user_agent_values_from_json(payload)))
    return handlers

def completed_handlers_from_value(value, default_completed=False):
    completed = {}
    if value is None:
        return completed
    if isinstance(value, dict):
        if "capability" in value or any(k in value for k in ("handler_results", "capability_results", "completed_handlers")):
            for key in ("handler_results", "capability_results"):
                if key in value:
                    merge_handler_maps(
                        completed,
                        completed_handlers_from_value(value.get(key), default_completed=False),
                    )
            if "completed_handlers" in value:
                merge_handler_maps(
                    completed,
                    completed_handlers_from_value(value.get("completed_handlers"), default_completed=True),
                )
            capability = str(value.get("capability") or "").strip()
            state = str(value.get("state") or "").strip().lower()
            handler = value.get("handler") or value.get("handlers") or []
            handler_values = handler if isinstance(handler, list) else [handler]
            handlers = [normalize_agent_name(item) for item in handler_values if normalize_agent_name(item)]
            if capability and handlers and (default_completed or state in COMPLETED_CAPABILITY_STATES):
                merge_handler_maps(completed, {capability: handlers})
            return completed
        if default_completed:
            return selected_handlers_from_json({"selected_handlers": value})
        return completed
    if isinstance(value, list):
        for item in value:
            merge_handler_maps(completed, completed_handlers_from_value(item, default_completed=default_completed))
        return completed
    if default_completed:
        return selected_handlers_from_json({"selected_handlers": value})
    return completed

def capability_completion_satisfies(task_dir, capability):
    context_dir = Path(task_dir) / "context"
    candidates = [
        context_dir / "handler-results.json",
        context_dir / "capability-results.json",
    ]
    capabilities_dir = context_dir / "capabilities"
    if capabilities_dir.is_dir():
        candidates.extend(sorted(capabilities_dir.glob("*.json")))

    for path in candidates:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        handlers = {}
        try:
            handlers = completed_handlers_from_value(json.loads(text))
        except Exception:
            handlers = {}
        if not handlers:
            for line in text.splitlines():
                match = re.match(
                    r"\s*[-*]?\s*(?:completed_handler|completed_handlers|handler_result|capability_result)\s*[:=]\s*(.+)",
                    line,
                    re.I,
                )
                if match:
                    merge_handler_maps(
                        handlers,
                        completed_handlers_from_value(match.group(1), default_completed=True),
                    )
        if handlers.get(capability):
            return True
    return False

def specialist_dispatch_satisfies_capability(task_dir, capability):
    context_dir = Path(task_dir) / "context"
    for path in (
        context_dir / "specialist-dispatch.json",
        context_dir / "specialist-dispatch.md",
    ):
        if not path.is_file():
            continue

        text = path.read_text(encoding="utf-8", errors="replace")
        if path.suffix == ".json":
            try:
                payload = json.loads(text)
                values = selected_user_agent_values_from_json(payload)
                handlers = selected_handlers_from_json(payload)
            except Exception:
                values = []
                handlers = {}
        else:
            values = []
            handlers = {}
            for line in text.splitlines():
                match = re.match(r"\s*[-*]?\s*selected_user_agents?\s*[:=]\s*(.+)", line, re.I)
                if match:
                    values.extend(split_specialist_values(match.group(1)))
                    continue
                match = re.match(r"\s*[-*]?\s*selected_handlers?\s*[:=]\s*(.+)", line, re.I)
                if match:
                    parsed = selected_handlers_from_json({"selected_handlers": match.group(1)})
                    for parsed_capability, selected in parsed.items():
                        handlers.setdefault(parsed_capability, [])
                        for handler in selected:
                            if handler not in handlers[parsed_capability]:
                                handlers[parsed_capability].append(handler)
            merge_handler_maps(handlers, legacy_agent_handlers(values))

        if handlers.get(capability):
            return True
    return False

def enforce_commit_specialist_dispatch():
    if not is_git_commit_command(command):
        return

    task_dir = os.environ.get("AGENT_CREW_TASK_DIR", "").strip()
    if not task_dir or not Path(task_dir).is_dir():
        return

    available_paths = legacy_commit_capability_provider_paths()
    if not available_paths:
        return

    if specialist_dispatch_satisfies_capability(task_dir, COMMIT_MESSAGE_CAPABILITY):
        if capability_completion_satisfies(task_dir, COMMIT_MESSAGE_CAPABILITY):
            return

        audit({
            "decision": "block",
            "kind": "commit-specialist",
            "pattern": "git commit requires commit capability completion",
            "command": command,
            "tool_name": tool_name,
            "approved": False,
            "approval_reason": "missing_commit_capability_completion",
            "approval_source": "capability-completion",
            "approval_file": "",
        })
        block_with_reason({
            "decision": "block",
            "reason": (
                "[agent-crew] Commit capability completion required.\n\n"
                "Kind: commit-specialist\n"
                f"Command: {command}\n"
                "Reason: a commit message capability handler was selected, but the current task context "
                f"does not record completed {COMMIT_MESSAGE_CAPABILITY} handler evidence before "
                "a raw git history mutation.\n"
                f"Next: record handler_results in {task_dir}/context/handler-results.json or "
                f"{task_dir}/context/capabilities/{COMMIT_MESSAGE_CAPABILITY}.json with "
                "state=completed and the selected handler id before running git commit or git commit --amend."
            ),
        })

    audit({
        "decision": "block",
        "kind": "commit-specialist",
        "pattern": "git commit requires commit message capability dispatch",
        "command": command,
        "tool_name": tool_name,
        "approved": False,
        "approval_reason": "missing_commit_capability_dispatch",
        "approval_source": "specialist-dispatch",
        "approval_file": "",
    })
    block_with_reason({
        "decision": "block",
        "reason": (
            "[agent-crew] Commit specialist dispatch required.\n\n"
            "Kind: commit-specialist\n"
            f"Command: {command}\n"
            "Reason: a commit message capability provider is available, but the current task context "
            f"does not record the {COMMIT_MESSAGE_CAPABILITY} capability handler "
            "before a git history mutation.\n"
            f"Next: record selected_handlers capability={COMMIT_MESSAGE_CAPABILITY} handler=<selected-handler> in "
            f"{task_dir}/context/specialist-dispatch.md before running git commit "
            "or git commit --amend."
        ),
    })

enforce_commit_specialist_dispatch()

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
