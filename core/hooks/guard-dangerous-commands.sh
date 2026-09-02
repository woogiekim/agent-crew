#!/bin/bash
# Block dangerous shell commands before execution.
# PreToolUse hook: receives JSON via stdin with tool_input.command.
#
# Exit codes:
#   0 — allow
#   2 — block; host should cancel the tool call and surface the reason

HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
. "${HOOK_DIR}/hook-timing.sh"
agent_crew_hook_timing_start "guard-dangerous-commands"
trap 'agent_crew_hook_timing_finish "$?"' EXIT

python3 -S - "${HOOK_DIR}/../scripts" 3<&0 <<'PYEOF'
import json
import os
import re
import shlex
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from hook_input import MAX_BYTES, read_available_fd
from mutation_scope import (
    active_read_only_task_dirs,
    configured_project_root as mutation_scope_project_root,
)

try:
    max_bytes = int(os.environ.get("AGENT_CREW_HOOK_INPUT_MAX_BYTES", str(MAX_BYTES)))
except ValueError:
    max_bytes = MAX_BYTES
if max_bytes <= 0:
    max_bytes = MAX_BYTES

# stdin carries this Python program; fd 3 preserves the host hook payload.
raw_input = read_available_fd(3, max_bytes=max_bytes).decode("utf-8", errors="replace")

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
        "read-only-git-mutation",
        "read-only-memory-mutation",
        "read-only-filesystem-mutation",
        "read-only-external-mutation",
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

def is_under_path(path, prefix):
    try:
        target = Path(path).expanduser().resolve(strict=False)
        base = Path(prefix).expanduser().resolve(strict=False)
        return target == base or base in target.parents
    except Exception:
        return False

def task_state_target_allowed(raw_target, read_only_tasks):
    target = str(raw_target or "").strip().strip("'\"")
    if not target or target == "/dev/null":
        return target == "/dev/null"

    candidates = []
    for task_dir in read_only_tasks:
        task_path = Path(task_dir).expanduser().resolve(strict=False)
        expanded = target
        replacements = {
            "${AGENT_CREW_TASK_DIR}": str(task_path),
            "$AGENT_CREW_TASK_DIR": str(task_path),
            "${TASKS_DIR}": str(task_path.parent),
            "$TASKS_DIR": str(task_path.parent),
            "${TASK_DIR}": str(task_path),
            "$TASK_DIR": str(task_path),
            "${STATE_DIR}": str(task_path.parent.parent),
            "$STATE_DIR": str(task_path.parent.parent),
            "${TASK_ID}": task_path.name,
            "$TASK_ID": task_path.name,
        }
        for token, value in replacements.items():
            expanded = expanded.replace(token, value)
        candidates.append((task_path, expanded))

    for task_path, expanded in candidates:
        if is_under_path(expanded, task_path):
            return True
        resolved = Path(expanded).expanduser().resolve(strict=False)
        if resolved in (
            task_path.parent / f"active.{task_path.name}",
            task_path.parent / "active",
        ):
            return True
    return False

def unwrap_command_argv(argv):
    index = 0
    assignment = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

    while index < len(argv) and assignment.match(argv[index]):
        index += 1

    if index < len(argv) and Path(argv[index]).name == "env":
        index += 1
        while index < len(argv):
            value = argv[index]
            if value == "--":
                index += 1
                break
            if value in {"-u", "--unset", "-C", "--chdir", "-a", "--argv0"}:
                index += 2
                continue
            if value in {"-S", "--split-string"}:
                if index + 1 >= len(argv):
                    return []
                try:
                    split_values = shlex.split(argv[index + 1])
                except Exception:
                    return []
                return unwrap_command_argv(split_values + argv[index + 2:])
            if value.startswith("-S") and len(value) > 2:
                try:
                    split_values = shlex.split(value[2:])
                except Exception:
                    return []
                return unwrap_command_argv(split_values + argv[index + 1:])
            if value.startswith("--split-string="):
                try:
                    split_values = shlex.split(value.split("=", 1)[1])
                except Exception:
                    return []
                return unwrap_command_argv(split_values + argv[index + 1:])
            if (
                value.startswith(("--unset=", "--chdir=", "--argv0="))
                or value.startswith("-")
                or assignment.match(value)
            ):
                index += 1
                continue
            break

    return argv[index:]

def task_local_state_mutation(command_text, read_only_tasks):
    redirection_pattern = (
        r"(?<![0-9])>{1,2}\s*(\"[^\"]+\"|'[^']+'|[^\s;&|]+)"
    )
    redirection_targets = []
    for match in re.finditer(redirection_pattern, command_text):
        redirection_targets.append(match.group(1))
    if redirection_targets and not all(
            task_state_target_allowed(target, read_only_tasks)
            for target in redirection_targets
    ):
        return False

    command_without_redirections = re.sub(redirection_pattern, "", command_text)
    if re.search(r"[;&|]", command_without_redirections):
        return False
    try:
        argv = unwrap_command_argv(shlex.split(command_without_redirections))
    except Exception:
        return False
    if not argv:
        return bool(redirection_targets)

    command_name = Path(argv[0]).name
    operands = [value for value in argv[1:] if not value.startswith("-")]
    if command_name in {"mkdir", "rm", "rmdir", "touch", "truncate"}:
        return bool(operands) and all(
            task_state_target_allowed(value, read_only_tasks) for value in operands
        )
    if command_name == "mv":
        return len(operands) >= 2 and all(
            task_state_target_allowed(value, read_only_tasks) for value in operands
        )
    if command_name in {"cp", "install"}:
        return bool(operands) and task_state_target_allowed(
            operands[-1], read_only_tasks
        )
    return bool(redirection_targets)

def read_only_git_inspection(command_text):
    if re.search(r"[;&|]", command_text):
        return False
    try:
        argv = unwrap_command_argv(shlex.split(command_text))
    except Exception:
        return False
    if not argv or Path(argv[0]).name != "git":
        return False

    index = 1
    while index < len(argv):
        value = argv[index]
        if value in {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}:
            index += 2
            continue
        if value.startswith(("--git-dir=", "--work-tree=", "--namespace=")):
            index += 1
            continue
        break
    if index >= len(argv):
        return False

    subcommand = argv[index]
    arguments = argv[index + 1:]
    if subcommand == "branch":
        return not arguments or arguments[0] in {
            "--all",
            "--contains",
            "--format",
            "--list",
            "--merged",
            "--no-contains",
            "--no-merged",
            "--points-at",
            "--remotes",
            "--show-current",
            "--sort",
            "-a",
            "-l",
            "-r",
        } or arguments[0].startswith(("--format=", "--sort="))
    if subcommand == "tag":
        return not arguments or arguments[0] in {
            "--contains",
            "--list",
            "--no-contains",
            "--points-at",
            "-l",
        }
    if subcommand == "stash":
        return bool(arguments) and arguments[0] in {"list", "show"}
    return False

def shell_command_segments(command_text):
    try:
        lexer = shlex.shlex(
            command_text,
            posix=True,
            punctuation_chars=";&|",
        )
        lexer.whitespace_split = True
        lexer.commenters = ""
        tokens = list(lexer)
    except Exception:
        return []

    segments = []
    current = []
    for token in tokens:
        if token and all(character in ";&|" for character in token):
            if current:
                segments.append(current)
                current = []
            continue
        current.append(token)
    if current:
        segments.append(current)
    return segments

def external_command_argv(argv):
    values = unwrap_command_argv(argv)
    while values and Path(values[0]).name in {"command", "nohup", "time"}:
        values = values[1:]
        while values and values[0].startswith("-"):
            values = values[1:]
    return values

def curl_request_mutates(arguments):
    method = ""
    sends_data = False
    uploads_content = False
    index = 0
    while index < len(arguments):
        value = arguments[index]
        lowered = value.lower()

        if value == "-X" or lowered == "--request":
            if index + 1 < len(arguments):
                method = arguments[index + 1].upper()
                index += 2
                continue
        elif value.startswith("-X") and len(value) > 2:
            method = value[2:].upper()
        elif lowered.startswith("--request="):
            method = value.split("=", 1)[1].upper()
        elif value == "-G" or lowered == "--get":
            method = "GET"
        elif value == "-I" or lowered == "--head":
            method = "HEAD"
        elif (
            value == "-d"
            or (value.startswith("-d") and len(value) > 2)
            or lowered == "--data"
            or lowered.startswith("--data=")
            or lowered.startswith("--data-")
            or lowered == "--json"
            or lowered.startswith("--json=")
        ):
            sends_data = True
        elif (
            value == "-F"
            or (value.startswith("-F") and len(value) > 2)
            or value == "-T"
            or (value.startswith("-T") and len(value) > 2)
            or lowered == "--form"
            or lowered.startswith("--form=")
            or lowered.startswith("--form-")
            or lowered == "--upload-file"
            or lowered.startswith("--upload-file=")
        ):
            uploads_content = True
        index += 1

    if method in {"POST", "PUT", "PATCH", "DELETE"}:
        return True
    if uploads_content:
        return True
    return sends_data and method not in {"GET", "HEAD"}

def github_cli_request_mutates(command_name, arguments):
    action_words = {
        "approve",
        "close",
        "comment",
        "create",
        "delete",
        "edit",
        "merge",
        "reopen",
        "review",
    }
    for value in arguments:
        action = value.lstrip("-").split("=", 1)[0].lower()
        if action in action_words:
            return True

    if command_name == "gh":
        pairs = zip(arguments, arguments[1:])
        if any(
            first.lower() == "workflow" and second.lower() == "run"
            for first, second in pairs
        ):
            return True

    try:
        api_index = next(
            index for index, value in enumerate(arguments) if value.lower() == "api"
        )
    except StopIteration:
        return False

    method = ""
    fields = False
    api_arguments = arguments[api_index + 1:]
    index = 0
    while index < len(api_arguments):
        value = api_arguments[index]
        lowered = value.lower()
        if value == "-X" or lowered == "--method":
            if index + 1 < len(api_arguments):
                method = api_arguments[index + 1].upper()
                index += 2
                continue
        elif value.startswith("-X") and len(value) > 2:
            method = value[2:].upper()
        elif lowered.startswith("--method="):
            method = value.split("=", 1)[1].upper()
        elif (
            value in {"-f", "-F"}
            or (value.startswith(("-f", "-F")) and len(value) > 2)
            or lowered in {"--field", "--raw-field", "--input"}
            or lowered.startswith(("--field=", "--raw-field=", "--input="))
        ):
            fields = True
        index += 1

    if method in {"POST", "PUT", "PATCH", "DELETE"}:
        return True
    return fields and method not in {"GET", "HEAD"}

def shell_substitution_bodies(command_text):
    bodies = []
    quote = ""
    index = 0
    while index < len(command_text):
        character = command_text[index]
        if quote == "'":
            if character == "'":
                quote = ""
            index += 1
            continue
        if character == "\\":
            index += 2
            continue
        if character == "'" and not quote:
            quote = "'"
            index += 1
            continue
        if character == '"':
            quote = "" if quote == '"' else '"'
            index += 1
            continue
        if character == "`":
            end = index + 1
            while end < len(command_text):
                if command_text[end] == "\\":
                    end += 2
                    continue
                if command_text[end] == "`":
                    bodies.append(command_text[index + 1:end])
                    index = end + 1
                    break
                end += 1
            else:
                bodies.append(command_text[index + 1:])
                break
            continue
        substitution_prefix = ""
        if command_text.startswith("$(", index):
            substitution_prefix = "$("
        elif not quote and command_text.startswith(("<(", ">("), index):
            substitution_prefix = command_text[index:index + 2]
        if substitution_prefix:
            depth = 1
            end = index + 2
            nested_quote = ""
            while end < len(command_text):
                nested_character = command_text[end]
                if nested_quote == "'":
                    if nested_character == "'":
                        nested_quote = ""
                    end += 1
                    continue
                if nested_character == "\\":
                    end += 2
                    continue
                if nested_character == "'" and not nested_quote:
                    nested_quote = "'"
                    end += 1
                    continue
                if nested_character == '"':
                    nested_quote = "" if nested_quote == '"' else '"'
                    end += 1
                    continue
                if not nested_quote and nested_character == "(":
                    depth += 1
                elif not nested_quote and nested_character == ")":
                    depth -= 1
                    if depth == 0:
                        bodies.append(command_text[index + 2:end])
                        index = end + 1
                        break
                end += 1
            else:
                bodies.append(command_text[index + 2:])
                break
            continue
        index += 1
    return bodies

def read_only_external_mutation(command_text, depth=0):
    if depth > 4:
        return bool(re.search(r"\b(?:curl|gh|glab)\b", command_text, re.I))

    for nested_command in shell_substitution_bodies(command_text):
        if read_only_external_mutation(nested_command, depth + 1):
            return True

    for segment in shell_command_segments(command_text):
        argv = external_command_argv(segment)
        if not argv:
            continue

        command_name = Path(argv[0]).name
        if command_name in {"bash", "sh", "zsh"}:
            for index, value in enumerate(argv[1:], start=1):
                if value.startswith("-") and "c" in value[1:] and index + 1 < len(argv):
                    if read_only_external_mutation(argv[index + 1], depth + 1):
                        return True
                    break
            continue
        if command_name == "eval":
            if read_only_external_mutation(" ".join(argv[1:]), depth + 1):
                return True
            continue
        if command_name == "curl" and curl_request_mutates(argv[1:]):
            return True
        if command_name in {"gh", "glab"} and github_cli_request_mutates(
            command_name,
            argv[1:],
        ):
            return True
    return False

def enforce_read_only_mutation_scope():
    task_dir = os.environ.get("AGENT_CREW_TASK_DIR", "").strip()
    project_root = mutation_scope_project_root(tool_input)
    read_only_tasks = active_read_only_task_dirs(
        home,
        project_root,
        explicit_task_dir=task_dir or None,
        script_roots=[Path(sys.argv[1])],
    )
    if not read_only_tasks:
        return

    patterns = [
        (
            "read-only-git-mutation",
            r"\bgit\b[^;&|\n]*\b(?:add|am|apply|bisect|branch|checkout|cherry-pick|clean|clone|commit|fetch|init|merge|mv|pull|push|rebase|reset|restore|revert|rm|stash|submodule|switch|tag|worktree)\b",
        ),
        (
            "read-only-memory-mutation",
            r"\bmnemos\s+(?:capture|delete|gc)\b",
        ),
        (
            "read-only-external-mutation",
            r"\b(?:curl|gh|glab)\b",
        ),
        (
            "read-only-filesystem-mutation",
            r"\b(?:apply_patch|chmod|chown|cp|install|ln|mkdir|mv|patch|rm|rmdir|rsync|sed\s+-[^\s]*i|tee|touch|truncate)\b|(?<![0-9])>{1,2}\s*(?!/dev/null\b)",
        ),
    ]
    for kind, pattern in patterns:
        if kind == "read-only-external-mutation":
            if not read_only_external_mutation(command):
                continue
        else:
            haystack = command_haystack(kind, command)
            if not re.search(pattern, haystack, re.I):
                continue
        if kind == "read-only-git-mutation" and read_only_git_inspection(command):
            continue
        if kind == "read-only-filesystem-mutation" and task_local_state_mutation(
            command,
            read_only_tasks,
        ):
            continue
        audit({
            "decision": "block",
            "kind": kind,
            "pattern": pattern,
            "command": command,
            "tool_name": tool_name,
            "approved": False,
            "approval_reason": "read_only_execution_contract",
            "approval_source": "mutation-scope",
            "approval_file": "",
        })
        block_with_reason({
            "decision": "block",
            "reason": (
                "[agent-crew] Read-only execution mutation blocked.\n\n"
                f"Kind: {kind}\n"
                f"Command: {command}\n"
                "Reason: mutation_scope=read_only permits task-local state only; "
                "an approval marker cannot widen the bound execution scope."
            ),
        })

enforce_read_only_mutation_scope()

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
