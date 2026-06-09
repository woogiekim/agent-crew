#!/bin/bash
# tracker-mutation-guard.sh
# PreToolUse hook for external tracker mutation tools.
#
# Guards issue #180: after an issuer workflow blocks, the host must not call
# Plane MCP mutation tools directly unless current-session fallback evidence
# proves the issuer dispatcher loaded an adapter contract and validated the
# outgoing payload before mutation. Project-specific tracker rules belong in
# runtime adapter evidence, not in this framework hook.

INPUT=$(cat)

python3 - "$INPUT" <<'PYEOF'
import json
import os
import sys
from pathlib import Path
from typing import Any

raw_input = sys.argv[1] if len(sys.argv) > 1 else ""

MUTATING_PLANE_TOOLS = {
    "mcp__plane__create_work_item",
    "mcp__plane__update_work_item",
    "mcp__plane__delete_work_item",
    "mcp__plane__create_intake_work_item",
    "mcp__plane.create_work_item",
    "mcp__plane.update_work_item",
    "mcp__plane.delete_work_item",
    "mcp__plane.create_intake_work_item",
}
VALIDATION_FILES = (
    "tracker-fallback-validation.json",
    "issuer-fallback-validation.json",
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

    home = Path(os.environ.get("AGENT_CREW_HOME", str(Path.home() / ".agent-crew"))).expanduser()
    state_root = home / "state"
    if state_root.is_dir():
        for marker in state_root.glob("*/tasks/active.*"):
            task_id = marker.name.removeprefix("active.")
            if task_id:
                candidates.append(marker.parent / task_id)

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

if os.environ.get("AGENT_CREW_TRACKER_MUTATION_GUARD_DISABLED", "").strip() == "1":
    sys.exit(0)

contract_result = None
for candidate in task_dir_candidates(tool_input):
    candidate_result = has_tracker_fallback_contract(candidate)
    if candidate_result[0]:
        contract_result = candidate_result
        break
    if contract_result is None:
        contract_result = candidate_result

if contract_result is None:
    block_with_reason(
        "[agent-crew] Plane tracker mutation blocked - missing tracker fallback contract. "
        "Use crew:run issuer workflow or provide AGENT_CREW_TASK_DIR with issuer specialist "
        "dispatch evidence and tracker fallback validation before calling Plane MCP mutation tools."
    )

contract_ok, contract_reason = contract_result
if not contract_ok:
    block_with_reason(
        "[agent-crew] Plane tracker mutation blocked - tracker fallback contract is incomplete: "
        f"{contract_reason}. Use crew:run issuer workflow or complete the current-session "
        "tracker fallback validation evidence first."
    )

sys.exit(0)
PYEOF
