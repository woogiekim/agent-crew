#!/bin/bash
# tracker-mutation-guard.sh
# PreToolUse hook for external tracker mutation tools.
#
# Guards issue #180: after an issuer workflow blocks, the host must not call
# Plane MCP mutation tools directly unless current-session fallback evidence
# proves the issuer dispatcher loaded an adapter contract and validated the
# outgoing payload before mutation. Project-specific tracker rules belong in
# runtime adapter evidence, not in this framework hook.

HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
. "${HOOK_DIR}/read-hook-input.sh"
INPUT="$(read_agent_crew_hook_input || true)"
. "${HOOK_DIR}/hook-timing.sh"
agent_crew_hook_timing_start "tracker-mutation-guard"
trap 'agent_crew_hook_timing_finish "$?"' EXIT

python3 - "$INPUT" "${HOOK_DIR}/../scripts" <<'PYEOF'
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

raw_input = sys.argv[1] if len(sys.argv) > 1 else ""
sys.path.insert(0, sys.argv[2])
from mutation_scope import task_mutation_scope

MUTATING_PLANE_TOOLS = {
    "mcp__plane__create_work_item",
    "mcp__plane__update_work_item",
    "mcp__plane__delete_work_item",
    "mcp__plane__create_intake_work_item",
    "mcp__plane__create_label",
    "mcp__plane__create_work_item_comment",
    "mcp__plane.create_work_item",
    "mcp__plane.update_work_item",
    "mcp__plane.delete_work_item",
    "mcp__plane.create_intake_work_item",
    "mcp__plane.create_label",
    "mcp__plane.create_work_item_comment",
}
VALIDATION_FILES = (
    "tracker-fallback-validation.json",
    "issuer-fallback-validation.json",
)
APPROVAL_FILES = (
    "tracker-mutation-approval.json",
    "issuer-tracker-mutation-approval.json",
)
FINISHED_RESULT_RE = re.compile(
    r"^(?:\*\*)?status:\*{0,2}\s+\*{0,2}(completed|cancelled)\*{0,2}\s*$",
    re.IGNORECASE,
)


def block_with_reason(reason: str) -> None:
    print(json.dumps({"decision": "block", "reason": reason}), file=sys.stderr, flush=True)
    sys.exit(2)


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def current_project_path() -> Path:
    raw = os.environ.get("PROJECT_ROOT", "").strip()
    try:
        return Path(raw or os.getcwd()).expanduser().resolve()
    except Exception:
        return Path(raw or os.getcwd()).expanduser()


def is_same_or_child(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
    except Exception:
        return str(path) == str(parent)


def task_is_finished(task_dir: Path) -> bool:
    result = read_text(task_dir / "result.md")
    for line in result.splitlines():
        if FINISHED_RESULT_RE.match(line.strip()):
            return True
    return False


def marker_is_live(marker: Path, task_dir: Path) -> bool:
    if task_is_finished(task_dir):
        return False
    return marker.is_file()


def active_marker_project_root(task_dir: Path) -> Optional[Path]:
    register = load_json(task_dir / "register.json")
    if not isinstance(register, dict):
        return None

    raw_project_root = str(register.get("project_root") or "").strip()
    if not raw_project_root:
        return None

    try:
        return Path(raw_project_root).expanduser().resolve()
    except Exception:
        return Path(raw_project_root).expanduser()


def active_marker_match_depth(task_dir: Path) -> int:
    project_root = active_marker_project_root(task_dir)
    if project_root is None:
        return -1

    current_path = current_project_path()
    if current_path != project_root and not is_same_or_child(current_path, project_root):
        return -1

    return len(project_root.parts)


def task_dir_candidates(tool_input: dict[str, Any]) -> list[Path]:
    candidates: list[Path] = []
    for key in ("AGENT_CREW_TASK_DIR", "TASK_DIR"):
        raw = os.environ.get(key, "").strip()
        if raw:
            candidates.append(Path(raw).expanduser())
    for key in ("task_dir", "TASK_DIR"):
        raw = str(tool_input.get(key) or "").strip()
        if raw:
            candidates.append(Path(raw).expanduser())

    if candidates:
        seen: set[str] = set()
        unique: list[Path] = []
        for candidate in candidates:
            resolved = str(candidate)
            if resolved not in seen:
                seen.add(resolved)
                unique.append(candidate)
        return unique

    home = Path(os.environ.get("AGENT_CREW_HOME", str(Path.home() / ".agent-crew"))).expanduser()
    state_root = home / "state"
    if state_root.is_dir():
        active_matches: list[tuple[int, Path]] = []
        for marker in state_root.glob("*/tasks/active.*"):
            task_id = marker.name.removeprefix("active.")
            task_dir = marker.parent / task_id if task_id else None
            if not task_dir or not marker_is_live(marker, task_dir):
                continue
            depth = active_marker_match_depth(task_dir)
            if depth >= 0:
                active_matches.append((depth, task_dir))
        if active_matches:
            closest_depth = max(depth for depth, _ in active_matches)
            for _, task_dir in sorted(
                (item for item in active_matches if item[0] == closest_depth),
                key=lambda item: str(item[1]),
            ):
                candidates.append(task_dir)

    seen: set[str] = set()
    unique: list[Path] = []
    for candidate in candidates:
        resolved = str(candidate)
        if resolved not in seen:
            seen.add(resolved)
            unique.append(candidate)
    return unique


def has_issuer_dispatch(context_dir: Path) -> bool:
    text = read_text(context_dir / "specialist-dispatch.md").lower()
    if not text:
        return False

    return (
        "issuer" in text
        and (
            "selected_agent" in text
            or "specialist_agent" in text
            or "dispatcher" in text
        )
    )


def tracker_validation(context_dir: Path):
    for name in VALIDATION_FILES:
        payload = load_json(context_dir / name)
        if isinstance(payload, dict):
            return name, payload
    return "", None


def bool_field(payload: dict[str, Any], name: str) -> bool:
    return payload.get(name) is True


def canonical_tool_input(tool_input: dict[str, Any]) -> str:
    return json.dumps(
        tool_input,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def tool_input_sha256(tool_input: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_tool_input(tool_input).encode("utf-8")).hexdigest()


def mutation_action(tool_name: str) -> str:
    return tool_name.replace("mcp__plane__", "").replace("mcp__plane.", "")


def payload_summary(tool_input: dict[str, Any]) -> str:
    safe_keys = (
        "workspace_slug",
        "project_id",
        "project_identifier",
        "work_item_id",
        "issue_identifier",
        "title",
        "state_id",
        "priority",
    )
    summary = {
        key: tool_input.get(key)
        for key in safe_keys
        if key in tool_input and tool_input.get(key) not in (None, "")
    }
    if not summary:
        summary = {"payload_keys": sorted(tool_input.keys())}
    return json.dumps(summary, ensure_ascii=False, sort_keys=True)


def approval_request_reason(
    *,
    tool_name: str,
    tool_input: dict[str, Any],
    missing_evidence: str,
    candidate_task_dirs: list[Path],
) -> str:
    digest = tool_input_sha256(tool_input)
    approval_path = "${TASK_DIR}/context/tracker-mutation-approval.json"
    candidate_summary = json.dumps(
        [str(candidate) for candidate in candidate_task_dirs],
        ensure_ascii=False,
    )
    return (
        "[agent-crew] Plane tracker mutation approval_required.\n\n"
        f"blocked_tool: {tool_name}\n"
        f"mutation_action: {mutation_action(tool_name)}\n"
        f"mutation_payload_summary: {payload_summary(tool_input)}\n"
        f"missing_evidence: {missing_evidence}\n"
        f"candidate_task_dirs: {candidate_summary}\n"
        "external_side_effect: Plane work item, label, comment, or intake mutation can change an external tracker.\n"
        "approval_scope: single exact tool call only; tool_name and canonical tool_input_sha256 must match this blocked call.\n"
        f"tool_input_sha256: {digest}\n"
        f"approval_record: write {approval_path} with schema_version=agent-crew.tracker-mutation-approval.v1, "
        "approved=true, tool_name, tool_input_sha256, scope=single_tool_payload, approved_by=user, expires_at.\n"
        "approve: create that task/request-context approval record, then retry the same MCP call.\n"
        "reject: do not create approval evidence; no Plane mutation will be executed.\n"
        "note: the guard prevents automatic external mutation; it is not a final user-approval denial."
    )


def tracker_approval(context_dir: Path):
    for name in APPROVAL_FILES:
        path = context_dir / name
        payload = load_json(path)
        if isinstance(payload, dict):
            return name, path, payload
    return "", None, None


def consumed_approval_path(path: Path) -> Path:
    if path.name.endswith(".json"):
        return path.with_name(path.name[:-5] + ".consumed.json")
    return path.with_name(path.name + ".consumed")


def parse_expiry(value: Any):
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None


def validate_tracker_approval(
    task_dir: Path,
    *,
    tool_name: str,
    tool_input: dict[str, Any],
) -> tuple[bool, str, Optional[Path]]:
    context_dir = task_dir / "context"
    approval_name, approval_path, approval = tracker_approval(context_dir)
    if approval is None:
        return False, "missing tracker mutation user approval evidence", None

    if approval.get("schema_version") != "agent-crew.tracker-mutation-approval.v1":
        return False, f"approval schema mismatch in {approval_name}", None

    if approval.get("approved") is not True:
        return False, f"approval_not_true in {approval_name}", None

    if str(approval.get("scope") or "") != "single_tool_payload":
        return False, f"approval scope mismatch in {approval_name}", None

    approved_tool = str(approval.get("tool_name") or "").strip()
    if approved_tool != tool_name:
        return False, f"approval tool mismatch in {approval_name}", None

    expected_hash = tool_input_sha256(tool_input)
    approved_hash = str(approval.get("tool_input_sha256") or "").strip()
    if approved_hash != expected_hash:
        return False, f"approval payload mismatch in {approval_name}", None

    expiry = parse_expiry(approval.get("expires_at"))
    if expiry is None:
        return False, f"approval missing or invalid expiry in {approval_name}", None
    if expiry <= datetime.now(timezone.utc):
        return False, f"approval expired in {approval_name}", None

    approver = str(approval.get("approved_by") or "").strip().lower()
    if approver not in {"user", "operator"}:
        return False, f"approval must be user/operator-owned in {approval_name}", None

    return True, "", approval_path


def consume_tracker_approval(approval_path: Path) -> tuple[bool, str]:
    consumed_path = consumed_approval_path(approval_path)
    try:
        os.replace(approval_path, consumed_path)
    except Exception as exc:
        return False, f"approval consume failed: {exc}"

    payload = load_json(consumed_path)
    if isinstance(payload, dict):
        payload["consumed_at"] = datetime.now(timezone.utc).isoformat()
        payload["approval_consumed"] = True
        try:
            consumed_path.write_text(
                json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        except Exception:
            pass

    return True, ""


def has_tracker_fallback_contract(task_dir: Path) -> tuple[bool, str]:
    context_dir = task_dir / "context"
    if not context_dir.is_dir():
        return False, "missing task context directory"

    if not has_issuer_dispatch(context_dir):
        return False, "missing issuer specialist dispatch evidence"

    validation_name, validation = tracker_validation(context_dir)
    if validation is None:
        return False, "missing tracker fallback validation evidence"

    if validation.get("status") != "passed":
        return False, f"tracker fallback validation did not pass in {validation_name}"

    issuer_evidence = str(validation.get("agent") or validation.get("validated_by") or "").strip().lower()
    if issuer_evidence != "issuer":
        return False, f"tracker fallback validation in {validation_name} was not produced by issuer"

    if not bool_field(validation, "adapter_contract_loaded"):
        return False, f"adapter contract validation is missing in {validation_name}"

    if not bool_field(validation, "payload_validated"):
        return False, f"payload validation is missing in {validation_name}"

    return True, ""


try:
    data = json.loads(raw_input)
except Exception:
    sys.exit(0)

tool_name = str(data.get("tool_name") or "")
tool_input_raw = data.get("tool_input") or {}
tool_input = tool_input_raw if isinstance(tool_input_raw, dict) else {}

if tool_name not in MUTATING_PLANE_TOOLS:
    sys.exit(0)

candidate_dirs = task_dir_candidates(tool_input)
read_only_candidates = [
    candidate
    for candidate in candidate_dirs
    if task_mutation_scope(candidate) == "read_only"
]
if read_only_candidates:
    block_with_reason(
        "[agent-crew] Tracker mutation blocked — mutation_scope=read_only.\n\n"
        f"Blocked tool: {tool_name}\n"
        "Task-local state is the only permitted write surface. Existing "
        "tracker validation or approval evidence cannot widen this execution "
        "contract; start a new explicitly writable task instead."
    )

if os.environ.get("AGENT_CREW_TRACKER_MUTATION_GUARD_DISABLED", "").strip() == "1":
    sys.exit(0)

contract_failures: list[str] = []
approval_failures: list[str] = []

for candidate in candidate_dirs:
    candidate_result = has_tracker_fallback_contract(candidate)
    contract_ok, contract_reason = candidate_result
    if not contract_ok:
        contract_failures.append(f"{candidate}: {contract_reason}")
        continue

    approval_ok, approval_reason, approval_path = validate_tracker_approval(
        candidate,
        tool_name=tool_name,
        tool_input=tool_input,
    )
    if not approval_ok:
        approval_failures.append(f"{candidate}: {approval_reason}")
        continue

    consume_ok, consume_reason = consume_tracker_approval(approval_path)
    if not consume_ok:
        block_with_reason(
            approval_request_reason(
                tool_name=tool_name,
                tool_input=tool_input,
                missing_evidence=consume_reason,
                candidate_task_dirs=candidate_dirs,
            )
        )

    sys.exit(0)

if not candidate_dirs:
    missing_evidence = (
        "missing tracker fallback contract and task/request context. "
        "No AGENT_CREW_TASK_DIR/TASK_DIR or matching active task context was found."
    )
elif approval_failures:
    missing_evidence = "no candidate has matching tracker mutation user approval evidence: " + "; ".join(approval_failures)
else:
    missing_evidence = "tracker fallback contract is incomplete for all candidates: " + "; ".join(contract_failures)

block_with_reason(
    approval_request_reason(
        tool_name=tool_name,
        tool_input=tool_input,
        missing_evidence=missing_evidence,
        candidate_task_dirs=candidate_dirs,
    )
)

PYEOF
